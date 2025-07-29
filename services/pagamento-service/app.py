from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Annotated
import os
import logging
from datetime import datetime, timedelta
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
import uuid

from google.cloud import pubsub_v1
import json
import asyncio
from shared.models import (
    GeneratePaymentCodeCommand, ProcessPaymentCommand, RefundPaymentCommand,
    PaymentCodeGeneratedEvent, PaymentCodeGenerationFailedEvent,
    PaymentProcessedEvent, PaymentFailedEvent,
    PaymentRefundedEvent, PaymentRefundFailedEvent
)

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

DB_HOST = os.getenv("DB_HOST", "db")
DB_USER = os.getenv("DB_USER", "user")
DB_PASSWORD = os.getenv("DB_PASSWORD", "password")
DB_NAME = os.getenv("DB_NAME", "main_db")
DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    DATABASE_URL = f"postgresql://{DB_USER}:{DB_PASSWORD}@{DB_HOST}:5432/{DB_NAME}?sslmode=require"

logger.info(f"Connecting to database host: {DB_HOST}")

engine = create_engine(DATABASE_URL)
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)
Base = declarative_base()

PROJECT_ID = os.getenv("PROJECT_ID", "saga-project")
PUBSUB_EMULATOR_HOST = os.getenv("PUBSUB_EMULATOR_HOST")

if PUBSUB_EMULATOR_HOST:
    os.environ["PUBSUB_EMULATOR_HOST"] = PUBSUB_EMULATOR_HOST
    logger.info(f"Using Pub/Sub emulator at {PUBSUB_EMULATOR_HOST}")
else:
    logger.info("Using Google Cloud Pub/Sub service (not emulator).")

publisher = pubsub_v1.PublisherClient()
subscriber = pubsub_v1.SubscriberClient()

GENERATE_PAYMENT_CODE_COMMAND_TOPIC = f"projects/{PROJECT_ID}/topics/commands.payment.generate_code"
PROCESS_PAYMENT_COMMAND_TOPIC = f"projects/{PROJECT_ID}/topics/commands.payment.process"
REFUND_PAYMENT_COMMAND_TOPIC = f"projects/{PROJECT_ID}/topics/commands.payment.refund"

GENERATE_PAYMENT_CODE_SUBSCRIPTION = f"projects/{PROJECT_ID}/subscriptions/pagamento-service-generate-code-sub"
PROCESS_PAYMENT_SUBSCRIPTION = f"projects/{PROJECT_ID}/subscriptions/pagamento-service-process-payment-sub"
REFUND_PAYMENT_SUBSCRIPTION = f"projects/{PROJECT_ID}/subscriptions/pagamento-service-refund-payment-sub"

PAYMENT_CODE_GENERATED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.payment.code_generated"
PAYMENT_CODE_GENERATION_FAILED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.payment.code_generation_failed"
PAYMENT_PROCESSED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.payment.processed"
PAYMENT_FAILED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.payment.failed"
PAYMENT_REFUNDED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.payment.refunded"
PAYMENT_REFUND_FAILED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.payment.refund_failed"


class PaymentCodeDB(Base):
    __tablename__ = "payment_codes"
    id = Column(Integer, primary_key=True, index=True)
    code = Column(String, unique=True, index=True)
    transaction_id = Column(String, unique=True, index=True)
    customer_id = Column(Integer)
    vehicle_id = Column(Integer)
    amount = Column(Float)
    expires_at = Column(DateTime)
    is_used = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)


class PaymentDB(Base):
    __tablename__ = "payments"
    id = Column(String, primary_key=True, default=lambda: str(
        uuid.uuid4()))
    transaction_id = Column(String, unique=True, index=True)
    payment_code_id = Column(Integer, unique=True)
    customer_id = Column(Integer)
    vehicle_id = Column(Integer)
    amount = Column(Float)
    payment_method = Column(String)
    status = Column(String, default="pending")
    processed_at = Column(DateTime, default=datetime.now)


class PaymentCodeResponse(BaseModel):
    id: int
    code: str
    transaction_id: str
    customer_id: int
    vehicle_id: int
    amount: float
    expires_at: datetime
    is_used: bool
    created_at: datetime


class PaymentRequest(BaseModel):
    payment_code: str
    payment_method: str = Field(..., pattern="^(pix|card|bank_transfer)$",
                                description="Valid methods: pix, card, bank_transfer")


class PaymentResponse(BaseModel):
    id: str
    transaction_id: str
    payment_code_id: int
    customer_id: int
    vehicle_id: int
    amount: float
    payment_method: str
    status: str
    processed_at: datetime


class PaymentsResponse(BaseModel):
    payments: List[PaymentResponse]
    total: int
    timestamp: datetime


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    logger.info("Creating database tables for Payment Service...")
    Base.metadata.create_all(bind=engine)
    logger.info("Payment Service database tables created.")


app = FastAPI(
    title="Payment Service API",
    description="API para gerenciamento de pagamentos",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    create_tables()
    asyncio.create_task(subscribe_to_payment_commands())


@app.on_event("shutdown")
async def shutdown_event():
    subscriber.close()


class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: datetime
    version: str


@app.get('/health', response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check(db: Annotated[Session, Depends(get_db)]):
    try:
        db.execute(text("SELECT 1"))
        db_status = "connected"
    except Exception as e:
        db_status = f"disconnected ({str(e)})"
        logger.error(f"Database connection error: {e}")
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail=f"Service unhealthy: Database connection failed. {str(e)}"
        )
    return HealthResponse(
        status='healthy' if db_status == "connected" else 'unhealthy',
        service='payment-service',
        timestamp=datetime.now(),
        version='1.0.0'
    )


async def publish_event(topic_path: str, event_data: BaseModel, transaction_id: str):
    try:
        data = event_data.model_dump_json().encode("utf-8")
        future = publisher.publish(
            topic_path, data, transaction_id=transaction_id)
        await asyncio.wrap_future(future)
        logger.info(
            f"Published to {topic_path}: {event_data.model_dump_json()}")
    except Exception as e:
        logger.error(f"Error publishing to {topic_path}: {e}")


async def handle_generate_payment_code_command(message):
    db = SessionLocal()
    try:
        command = GeneratePaymentCodeCommand.model_validate_json(message.data)
        logger.info(
            f"Received GeneratePaymentCodeCommand: {command.model_dump_json()}")

        existing_code = db.query(PaymentCodeDB).filter(
            PaymentCodeDB.transaction_id == command.transaction_id).first()
        if existing_code:
            logger.warning(
                f"Payment code already exists for transaction_id {command.transaction_id}. Returning existing.")
            await publish_event(
                PAYMENT_CODE_GENERATED_EVENT_TOPIC,
                PaymentCodeGeneratedEvent(
                    transaction_id=existing_code.transaction_id,
                    payment_code=existing_code.code,
                    customer_id=existing_code.customer_id,
                    vehicle_id=existing_code.vehicle_id,
                    amount=existing_code.amount,
                    expires_at=existing_code.expires_at
                ),
                command.transaction_id
            )
            message.ack()
            return

        payment_code = str(uuid.uuid4()).replace(
            '-', '')[:10].upper()

        expires_at = datetime.now() + timedelta(minutes=30)

        db_payment_code = PaymentCodeDB(
            code=payment_code,
            transaction_id=command.transaction_id,
            customer_id=command.customer_id,
            vehicle_id=command.vehicle_id,
            amount=command.amount,
            expires_at=expires_at
        )
        db.add(db_payment_code)
        db.commit()
        db.refresh(db_payment_code)

        await publish_event(
            PAYMENT_CODE_GENERATED_EVENT_TOPIC,
            PaymentCodeGeneratedEvent(
                transaction_id=db_payment_code.transaction_id,
                payment_code=db_payment_code.code,
                customer_id=db_payment_code.customer_id,
                vehicle_id=db_payment_code.vehicle_id,
                amount=db_payment_code.amount,
                expires_at=db_payment_code.expires_at
            ),
            command.transaction_id
        )
        logger.info(
            f"Payment code {payment_code} generated for transaction {command.transaction_id}")
        message.ack()

    except ValidationError as e:
        logger.error(
            f"Validation error for GeneratePaymentCodeCommand: {e} - Data: {message.data}")
        message.ack()
    except IntegrityError:
        db.rollback()
        await publish_event(
            PAYMENT_CODE_GENERATION_FAILED_EVENT_TOPIC,
            PaymentCodeGenerationFailedEvent(
                transaction_id=command.transaction_id,
                customer_id=command.customer_id,
                vehicle_id=command.vehicle_id,
                amount=command.amount,
                reason="Duplicate transaction ID or code."
            ),
            command.transaction_id
        )
        message.ack()
    except Exception as e:
        logger.error(f"Error processing GeneratePaymentCodeCommand: {e}")
        db.rollback()
        await publish_event(
            PAYMENT_CODE_GENERATION_FAILED_EVENT_TOPIC,
            PaymentCodeGenerationFailedEvent(
                transaction_id=command.transaction_id,
                customer_id=command.customer_id,
                vehicle_id=command.vehicle_id,
                amount=command.amount,
                reason=f"Internal error: {str(e)}"
            ),
            command.transaction_id
        )
        message.ack()
    finally:
        db.close()


async def handle_process_payment_command(message):
    db = SessionLocal()
    try:
        command = ProcessPaymentCommand.model_validate_json(message.data)
        logger.info(
            f"Received ProcessPaymentCommand: {command.model_dump_json()}")

        payment_code_obj = db.query(PaymentCodeDB).filter(
            PaymentCodeDB.code == command.payment_code).first()

        if not payment_code_obj:
            await publish_event(
                PAYMENT_FAILED_EVENT_TOPIC,
                PaymentFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_code=command.payment_code,
                    customer_id=0,
                    vehicle_id=0,
                    amount=0.0,
                    reason="Payment code not found"
                ),
                command.transaction_id
            )
            message.ack()
            return

        if payment_code_obj.is_used:
            await publish_event(
                PAYMENT_FAILED_EVENT_TOPIC,
                PaymentFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_code=command.payment_code,
                    customer_id=payment_code_obj.customer_id,
                    vehicle_id=payment_code_obj.vehicle_id,
                    amount=payment_code_obj.amount,
                    reason="Payment code already used"
                ),
                command.transaction_id
            )
            message.ack()
            return

        if datetime.now() > payment_code_obj.expires_at:
            await publish_event(
                PAYMENT_FAILED_EVENT_TOPIC,
                PaymentFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_code=command.payment_code,
                    customer_id=payment_code_obj.customer_id,
                    vehicle_id=payment_code_obj.vehicle_id,
                    amount=payment_code_obj.amount,
                    reason="Payment code expired"
                ),
                command.transaction_id
            )
            message.ack()
            return

        existing_payment = db.query(PaymentDB).filter(
            PaymentDB.transaction_id == command.transaction_id).first()
        if existing_payment:
            logger.warning(
                f"Payment already processed for transaction {command.transaction_id}. Returning existing status.")
            if existing_payment.status == "completed":
                await publish_event(
                    PAYMENT_PROCESSED_EVENT_TOPIC,
                    PaymentProcessedEvent(
                        transaction_id=existing_payment.transaction_id,
                        payment_id=existing_payment.id,
                        payment_code=command.payment_code,
                        customer_id=existing_payment.customer_id,
                        vehicle_id=existing_payment.vehicle_id,
                        amount=existing_payment.amount,
                        payment_method=existing_payment.payment_method,
                        status=existing_payment.status
                    ),
                    command.transaction_id
                )
            else:
                await publish_event(
                    PAYMENT_FAILED_EVENT_TOPIC,
                    PaymentFailedEvent(
                        transaction_id=existing_payment.transaction_id,
                        payment_code=command.payment_code,
                        customer_id=existing_payment.customer_id,
                        vehicle_id=existing_payment.vehicle_id,
                        amount=existing_payment.amount,
                        reason=f"Payment already exists with status: {existing_payment.status}"
                    ),
                    command.transaction_id
                )
            message.ack()
            return

        payment_successful = True

        if payment_successful:
            payment_code_obj.is_used = True
            db.add(payment_code_obj)

            db_payment = PaymentDB(
                transaction_id=command.transaction_id,
                payment_code_id=payment_code_obj.id,
                customer_id=payment_code_obj.customer_id,
                vehicle_id=payment_code_obj.vehicle_id,
                amount=payment_code_obj.amount,
                payment_method=command.payment_method,
                status="completed"
            )
            db.add(db_payment)
            db.commit()
            db.refresh(db_payment)

            await publish_event(
                PAYMENT_PROCESSED_EVENT_TOPIC,
                PaymentProcessedEvent(
                    transaction_id=db_payment.transaction_id,
                    payment_id=db_payment.id,
                    payment_code=command.payment_code,
                    customer_id=db_payment.customer_id,
                    vehicle_id=db_payment.vehicle_id,
                    amount=db_payment.amount,
                    payment_method=db_payment.payment_method,
                    status=db_payment.status
                ),
                command.transaction_id
            )
            logger.info(
                f"Payment {db_payment.id} processed successfully for transaction {command.transaction_id}")
        else:
            db_payment = PaymentDB(
                transaction_id=command.transaction_id,
                payment_code_id=payment_code_obj.id,
                customer_id=payment_code_obj.customer_id,
                vehicle_id=payment_code_obj.vehicle_id,
                amount=payment_code_obj.amount,
                payment_method=command.payment_method,
                status="failed"
            )
            db.add(db_payment)
            db.commit()
            db.refresh(db_payment)

            await publish_event(
                PAYMENT_FAILED_EVENT_TOPIC,
                PaymentFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_code=command.payment_code,
                    customer_id=payment_code_obj.customer_id,
                    vehicle_id=payment_code_obj.vehicle_id,
                    amount=payment_code_obj.amount,
                    reason="Payment processing failed (simulated)"
                ),
                command.transaction_id
            )
            logger.warning(
                f"Payment for transaction {command.transaction_id} failed (simulated).")

        message.ack()

    except ValidationError as e:
        logger.error(
            f"Validation error for ProcessPaymentCommand: {e} - Data: {message.data}")
        message.ack()
    except IntegrityError:
        db.rollback()
        await publish_event(
            PAYMENT_FAILED_EVENT_TOPIC,
            PaymentFailedEvent(
                transaction_id=command.transaction_id,
                payment_code=command.payment_code,
                customer_id=payment_code_obj.customer_id if payment_code_obj else 0,
                vehicle_id=payment_code_obj.vehicle_id if payment_code_obj else 0,
                amount=payment_code_obj.amount if payment_code_obj else 0.0,
                reason="Payment already recorded or duplicate entry."
            ),
            command.transaction_id
        )
        message.ack()
    except Exception as e:
        logger.error(f"Error processing ProcessPaymentCommand: {e}")
        db.rollback()
        await publish_event(
            PAYMENT_FAILED_EVENT_TOPIC,
            PaymentFailedEvent(
                transaction_id=command.transaction_id,
                payment_code=command.payment_code,
                customer_id=payment_code_obj.customer_id if payment_code_obj else 0,
                vehicle_id=payment_code_obj.vehicle_id if payment_code_obj else 0,
                amount=payment_code_obj.amount if payment_code_obj else 0.0,
                reason=f"Internal error: {str(e)}"
            ),
            command.transaction_id
        )
        message.ack()
    finally:
        db.close()


async def handle_refund_payment_command(message):
    db = SessionLocal()
    try:
        command = RefundPaymentCommand.model_validate_json(message.data)
        logger.info(
            f"Received RefundPaymentCommand: {command.model_dump_json()}")

        payment = db.query(PaymentDB).filter(
            PaymentDB.transaction_id == command.transaction_id).first()

        if not payment:
            await publish_event(
                PAYMENT_REFUND_FAILED_EVENT_TOPIC,
                PaymentRefundFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_id=command.payment_id,
                    reason="Payment not found for transaction ID"
                ),
                command.transaction_id
            )
            message.ack()
            return

        if payment.status == "refunded":
            logger.info(
                f"Payment {payment.id} already refunded for transaction {command.transaction_id}")
            await publish_event(
                PAYMENT_REFUNDED_EVENT_TOPIC,
                PaymentRefundedEvent(
                    transaction_id=command.transaction_id,
                    payment_id=payment.id,
                    status="refunded"
                ),
                command.transaction_id
            )
            message.ack()
            return

        if payment.status == "failed":
            logger.warning(
                f"Cannot refund a failed payment {payment.id} for transaction {command.transaction_id}")
            await publish_event(
                PAYMENT_REFUND_FAILED_EVENT_TOPIC,
                PaymentRefundFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_id=payment.id,
                    reason="Cannot refund a failed payment"
                ),
                command.transaction_id
            )
            message.ack()
            return

        payment.status = "refunded"
        db.add(payment)
        db.commit()
        db.refresh(payment)

        await publish_event(
            PAYMENT_REFUNDED_EVENT_TOPIC,
            PaymentRefundedEvent(
                transaction_id=command.transaction_id,
                payment_id=payment.id,
                status=payment.status
            ),
            command.transaction_id
        )
        logger.info(
            f"Payment {payment.id} refunded successfully for transaction {command.transaction_id}")
        message.ack()

    except ValidationError as e:
        logger.error(
            f"Validation error for RefundPaymentCommand: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error processing RefundPaymentCommand: {e}")
        db.rollback()
        await publish_event(
            PAYMENT_REFUND_FAILED_EVENT_TOPIC,
            PaymentRefundFailedEvent(
                transaction_id=command.transaction_id,
                payment_id=command.payment_id,
                reason=f"Internal error: {str(e)}"
            ),
            command.transaction_id
        )
        message.ack()
    finally:
        db.close()


async def subscribe_to_payment_commands():
    loop = asyncio.get_event_loop()

    for topic, sub in [
        (GENERATE_PAYMENT_CODE_COMMAND_TOPIC, GENERATE_PAYMENT_CODE_SUBSCRIPTION),
        (PROCESS_PAYMENT_COMMAND_TOPIC, PROCESS_PAYMENT_SUBSCRIPTION),
        (REFUND_PAYMENT_COMMAND_TOPIC, REFUND_PAYMENT_SUBSCRIPTION)
    ]:
        try:
            publisher.create_topic(request={"name": topic})
            logger.info(f"Topic {topic} ensured.")
        except Exception as e:
            if "Resource already exists" not in str(e):
                logger.error(f"Error creating topic {topic}: {e}")
        try:
            subscriber.create_subscription(
                request={"name": sub, "topic": topic})
            logger.info(f"Subscription {sub} ensured.")
        except Exception as e:
            if "Resource already exists" not in str(e):
                logger.error(f"Error creating subscription {sub}: {e}")

    logger.info(
        f"Listening for messages on {GENERATE_PAYMENT_CODE_SUBSCRIPTION}")
    streaming_pull_future_generate = subscriber.subscribe(
        GENERATE_PAYMENT_CODE_SUBSCRIPTION,
        callback=lambda message: loop.create_task(
            handle_generate_payment_code_command(message))
    )

    logger.info(f"Listening for messages on {PROCESS_PAYMENT_SUBSCRIPTION}")
    streaming_pull_future_process = subscriber.subscribe(
        PROCESS_PAYMENT_SUBSCRIPTION,
        callback=lambda message: loop.create_task(
            handle_process_payment_command(message))
    )

    logger.info(f"Listening for messages on {REFUND_PAYMENT_SUBSCRIPTION}")
    streaming_pull_future_refund = subscriber.subscribe(
        REFUND_PAYMENT_SUBSCRIPTION,
        callback=lambda message: loop.create_task(
            handle_refund_payment_command(message))
    )


@app.post("/payment-codes", response_model=PaymentCodeResponse, status_code=status.HTTP_201_CREATED)
async def create_payment_code(
    customer_id: int, vehicle_id: int, amount: float, db: Annotated[Session, Depends(get_db)]
):
    try:
        payment_code = str(uuid.uuid4()).replace('-', '')[:10].upper()
        expires_at = datetime.now() + timedelta(minutes=30)

        db_payment_code = PaymentCodeDB(
            code=payment_code,
            transaction_id=f"direct-{uuid.uuid4()}",
            customer_id=customer_id,
            vehicle_id=vehicle_id,
            amount=amount,
            expires_at=expires_at
        )
        db.add(db_payment_code)
        db.commit()
        db.refresh(db_payment_code)
        return db_payment_code
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Could not generate unique payment code or transaction ID."
        )
    except Exception as e:
        logger.error(f"Error creating payment code: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/payment-codes", response_model=List[PaymentCodeResponse])
async def get_payment_codes(db: Annotated[Session, Depends(get_db)]):
    return db.query(PaymentCodeDB).all()


@app.get("/payment-codes/{code}", response_model=PaymentCodeResponse)
async def get_payment_code_by_code(code: str, db: Annotated[Session, Depends(get_db)]):
    payment_code = db.query(PaymentCodeDB).filter(
        PaymentCodeDB.code == code).first()
    if not payment_code:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND,
                            detail="Payment code not found")
    return payment_code


@app.get("/payments", response_model=PaymentsResponse)
async def get_payments(db: Annotated[Session, Depends(get_db)]):
    payments = db.query(PaymentDB).all()
    return PaymentsResponse(payments=payments, total=len(payments), timestamp=datetime.now())


@app.get("/payments/{payment_id}", response_model=PaymentResponse)
async def get_payment(payment_id: str, db: Annotated[Session, Depends(get_db)]):
    payment = db.query(PaymentDB).filter(PaymentDB.id == payment_id).first()
    if not payment:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Payment not found")
    return payment


if __name__ == '__main__':
    port = int(os.environ.get('PORT', 8080))
    debug_mode = os.environ.get('DEBUG', '1') == '1'

    uvicorn.run(
        "app:app",
        host='0.0.0.0',
        port=port,
        reload=debug_mode,
        log_level="info"
    )
