# ./services/pagamento-service/app.py
from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Annotated
import os
import logging
from datetime import datetime, timedelta
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
import uuid
import random

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

# Topics e Subscriptions
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
    transaction_id = Column(String, index=True)
    customer_id = Column(Integer)
    vehicle_id = Column(Integer)
    amount = Column(Float)
    payment_type = Column(String)
    status = Column(String, default="pending")  # pending, used, expired
    expires_at = Column(DateTime)
    created_at = Column(DateTime, default=datetime.now)


class PaymentDB(Base):
    __tablename__ = "payments"
    id = Column(Integer, primary_key=True, index=True)
    payment_code = Column(String, index=True)
    transaction_id = Column(String, index=True)
    customer_id = Column(Integer)
    vehicle_id = Column(Integer)
    amount = Column(Float)
    payment_type = Column(String)
    payment_method = Column(String)  # pix, credit_card, etc.
    status = Column(String)  # completed, failed, refunded
    processed_at = Column(DateTime, default=datetime.now)
    created_at = Column(DateTime, default=datetime.now)


class PaymentCodeCreate(BaseModel):
    customer_id: int
    vehicle_id: int
    amount: float = Field(..., gt=0)
    payment_type: str


class PaymentCodeResponse(BaseModel):
    id: int
    code: str
    transaction_id: str
    customer_id: int
    vehicle_id: int
    amount: float
    payment_type: str
    status: str
    expires_at: datetime
    created_at: datetime


class PaymentCreate(BaseModel):
    payment_code: str
    payment_method: str = "pix"


class PaymentResponse(BaseModel):
    id: int
    payment_code: str
    transaction_id: str
    customer_id: int
    vehicle_id: int
    amount: float
    payment_type: str
    payment_method: str
    status: str
    processed_at: datetime
    created_at: datetime


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


def generate_payment_code() -> str:
    return f"PAY{random.randint(100000, 999999)}{int(datetime.now().timestamp())}"


async def handle_generate_payment_code_command(message):
    db = SessionLocal()
    try:
        command = GeneratePaymentCodeCommand.model_validate_json(message.data)
        logger.info(
            f"Received GeneratePaymentCodeCommand: {command.model_dump_json()}")

        # Gerar código único
        payment_code = generate_payment_code()
        expires_at = datetime.now() + timedelta(minutes=30)  # Expira em 30 minutos

        # Salvar no banco
        db_payment_code = PaymentCodeDB(
            code=payment_code,
            transaction_id=command.transaction_id,
            customer_id=command.customer_id,
            vehicle_id=command.vehicle_id,
            amount=command.amount,
            payment_type=command.payment_type,
            status="pending",
            expires_at=expires_at
        )
        db.add(db_payment_code)
        db.commit()
        db.refresh(db_payment_code)

        # Publicar evento de sucesso
        await publish_event(
            PAYMENT_CODE_GENERATED_EVENT_TOPIC,
            PaymentCodeGeneratedEvent(
                transaction_id=command.transaction_id,
                payment_code=payment_code,
                customer_id=command.customer_id,
                vehicle_id=command.vehicle_id,
                amount=command.amount,
                payment_type=command.payment_type,
                expires_at=expires_at
            ),
            command.transaction_id
        )
        logger.info(f"Payment code {payment_code} generated successfully.")
        message.ack()

    except ValidationError as e:
        logger.error(
            f"Validation error for GeneratePaymentCodeCommand: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error processing GeneratePaymentCodeCommand: {e}")

        # Publicar evento de falha
        try:
            command = GeneratePaymentCodeCommand.model_validate_json(
                message.data)
            await publish_event(
                PAYMENT_CODE_GENERATION_FAILED_EVENT_TOPIC,
                PaymentCodeGenerationFailedEvent(
                    transaction_id=command.transaction_id,
                    customer_id=command.customer_id,
                    vehicle_id=command.vehicle_id,
                    amount=command.amount,
                    payment_type=command.payment_type,
                    reason=str(e)
                ),
                command.transaction_id
            )
        except Exception as pub_error:
            logger.error(f"Error publishing failure event: {pub_error}")

        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_process_payment_command(message):
    db = SessionLocal()
    try:
        command = ProcessPaymentCommand.model_validate_json(message.data)
        logger.info(
            f"Received ProcessPaymentCommand: {command.model_dump_json()}")

        # Buscar código de pagamento
        payment_code_record = db.query(PaymentCodeDB).filter(
            PaymentCodeDB.code == command.payment_code).first()

        if not payment_code_record:
            await publish_event(
                PAYMENT_FAILED_EVENT_TOPIC,
                PaymentFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_code=command.payment_code,
                    customer_id=0,
                    vehicle_id=0,
                    amount=0.0,
                    payment_type="unknown",
                    reason="Payment code not found"
                ),
                command.transaction_id
            )
            message.ack()
            return

        # Verificar se não expirou
        if datetime.now() > payment_code_record.expires_at:
            await publish_event(
                PAYMENT_FAILED_EVENT_TOPIC,
                PaymentFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_code=command.payment_code,
                    customer_id=payment_code_record.customer_id,
                    vehicle_id=payment_code_record.vehicle_id,
                    amount=payment_code_record.amount,
                    payment_type=payment_code_record.payment_type,
                    reason="Payment code expired"
                ),
                command.transaction_id
            )
            message.ack()
            return

        # Verificar se já foi usado
        if payment_code_record.status != "pending":
            await publish_event(
                PAYMENT_FAILED_EVENT_TOPIC,
                PaymentFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_code=command.payment_code,
                    customer_id=payment_code_record.customer_id,
                    vehicle_id=payment_code_record.vehicle_id,
                    amount=payment_code_record.amount,
                    payment_type=payment_code_record.payment_type,
                    reason=f"Payment code already {payment_code_record.status}"
                ),
                command.transaction_id
            )
            message.ack()
            return

        # Simular processamento de pagamento (sempre sucesso para testes)
        payment_success = True  # Em produção, aqui seria a integração com gateway

        if payment_success:
            # Marcar código como usado
            payment_code_record.status = "used"
            db.add(payment_code_record)

            # Criar registro de pagamento
            payment_record = PaymentDB(
                payment_code=command.payment_code,
                transaction_id=command.transaction_id,
                customer_id=payment_code_record.customer_id,
                vehicle_id=payment_code_record.vehicle_id,
                amount=payment_code_record.amount,
                payment_type=payment_code_record.payment_type,
                payment_method=command.payment_method,
                status="completed"
            )
            db.add(payment_record)
            db.commit()
            db.refresh(payment_record)

            # Publicar evento de sucesso
            await publish_event(
                PAYMENT_PROCESSED_EVENT_TOPIC,
                PaymentProcessedEvent(
                    transaction_id=command.transaction_id,
                    payment_id=str(payment_record.id),
                    payment_code=command.payment_code,
                    customer_id=payment_code_record.customer_id,
                    vehicle_id=payment_code_record.vehicle_id,
                    amount=payment_code_record.amount,
                    payment_type=payment_code_record.payment_type,
                    payment_method=command.payment_method,
                    status="completed"
                ),
                command.transaction_id
            )
            logger.info(f"Payment {payment_record.id} processed successfully.")
        else:
            await publish_event(
                PAYMENT_FAILED_EVENT_TOPIC,
                PaymentFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_code=command.payment_code,
                    customer_id=payment_code_record.customer_id,
                    vehicle_id=payment_code_record.vehicle_id,
                    amount=payment_code_record.amount,
                    payment_type=payment_code_record.payment_type,
                    reason="Payment processing failed"
                ),
                command.transaction_id
            )

        message.ack()

    except ValidationError as e:
        logger.error(
            f"Validation error for ProcessPaymentCommand: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error processing ProcessPaymentCommand: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_refund_payment_command(message):
    db = SessionLocal()
    try:
        command = RefundPaymentCommand.model_validate_json(message.data)
        logger.info(
            f"Received RefundPaymentCommand: {command.model_dump_json()}")

        # Buscar pagamento
        payment_record = db.query(PaymentDB).filter(
            PaymentDB.id == int(command.payment_id)).first()

        if not payment_record:
            await publish_event(
                PAYMENT_REFUND_FAILED_EVENT_TOPIC,
                PaymentRefundFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_id=command.payment_id,
                    reason="Payment not found"
                ),
                command.transaction_id
            )
            message.ack()
            return

        if payment_record.status != "completed":
            await publish_event(
                PAYMENT_REFUND_FAILED_EVENT_TOPIC,
                PaymentRefundFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_id=command.payment_id,
                    reason=f"Cannot refund payment with status: {payment_record.status}"
                ),
                command.transaction_id
            )
            message.ack()
            return

        # Simular reembolso (sempre sucesso para testes)
        refund_success = True

        if refund_success:
            payment_record.status = "refunded"
            db.add(payment_record)
            db.commit()

            await publish_event(
                PAYMENT_REFUNDED_EVENT_TOPIC,
                PaymentRefundedEvent(
                    transaction_id=command.transaction_id,
                    payment_id=command.payment_id,
                    status="refunded"
                ),
                command.transaction_id
            )
            logger.info(f"Payment {command.payment_id} refunded successfully.")
        else:
            await publish_event(
                PAYMENT_REFUND_FAILED_EVENT_TOPIC,
                PaymentRefundFailedEvent(
                    transaction_id=command.transaction_id,
                    payment_id=command.payment_id,
                    reason="Refund processing failed"
                ),
                command.transaction_id
            )

        message.ack()

    except ValidationError as e:
        logger.error(
            f"Validation error for RefundPaymentCommand: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error processing RefundPaymentCommand: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def subscribe_to_payment_commands():
    loop = asyncio.get_event_loop()

    # Criar tópicos e subscriptions
    commands_config = [
        (GENERATE_PAYMENT_CODE_COMMAND_TOPIC, GENERATE_PAYMENT_CODE_SUBSCRIPTION,
         handle_generate_payment_code_command),
        (PROCESS_PAYMENT_COMMAND_TOPIC, PROCESS_PAYMENT_SUBSCRIPTION,
         handle_process_payment_command),
        (REFUND_PAYMENT_COMMAND_TOPIC, REFUND_PAYMENT_SUBSCRIPTION,
         handle_refund_payment_command)
    ]

    for topic, subscription, handler in commands_config:
        try:
            publisher.create_topic(request={"name": topic})
            logger.info(f"Topic {topic} ensured.")
        except Exception as e:
            if "Resource already exists" not in str(e):
                logger.error(f"Error creating topic {topic}: {e}")

        try:
            subscriber.create_subscription(
                request={"name": subscription, "topic": topic})
            logger.info(f"Subscription {subscription} ensured.")
        except Exception as e:
            if "Resource already exists" not in str(e):
                logger.error(
                    f"Error creating subscription {subscription}: {e}")

        logger.info(f"Listening for messages on {subscription}")
        subscriber.subscribe(
            subscription,
            callback=lambda message, h=handler: loop.create_task(h(message))
        )


async def create_payment_code(payment_code: PaymentCodeCreate, db: Annotated[Session, Depends(get_db)]):
    try:
        code = generate_payment_code()
        expires_at = datetime.now() + timedelta(minutes=30)

        db_payment_code = PaymentCodeDB(
            code=code,
            transaction_id=str(uuid.uuid4()),
            customer_id=payment_code.customer_id,
            vehicle_id=payment_code.vehicle_id,
            amount=payment_code.amount,
            payment_type=payment_code.payment_type,
            status="pending",
            expires_at=expires_at
        )
        db.add(db_payment_code)
        db.commit()
        db.refresh(db_payment_code)
        return PaymentCodeResponse(**db_payment_code.__dict__)
    except Exception as e:
        logger.error(f"Error creating payment code: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/payment-codes", response_model=List[PaymentCodeResponse])
async def get_payment_codes(db: Annotated[Session, Depends(get_db)]):
    payment_codes = db.query(PaymentCodeDB).all()
    return [PaymentCodeResponse(**pc.__dict__) for pc in payment_codes]


@app.get("/payment-codes/{code}", response_model=PaymentCodeResponse)
async def get_payment_code(code: str, db: Annotated[Session, Depends(get_db)]):
    payment_code = db.query(PaymentCodeDB).filter(
        PaymentCodeDB.code == code).first()
    if not payment_code:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Payment code not found"
        )
    return PaymentCodeResponse(**payment_code.__dict__)


@app.post("/payments", response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def process_payment(payment: PaymentCreate, db: Annotated[Session, Depends(get_db)]):
    try:
        # Buscar código de pagamento
        payment_code_record = db.query(PaymentCodeDB).filter(
            PaymentCodeDB.code == payment.payment_code).first()

        if not payment_code_record:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment code not found"
            )

        if datetime.now() > payment_code_record.expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment code expired"
            )

        if payment_code_record.status != "pending":
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Payment code already {payment_code_record.status}"
            )

        # Marcar código como usado
        payment_code_record.status = "used"
        db.add(payment_code_record)

        # Criar registro de pagamento
        payment_record = PaymentDB(
            payment_code=payment.payment_code,
            transaction_id=payment_code_record.transaction_id,
            customer_id=payment_code_record.customer_id,
            vehicle_id=payment_code_record.vehicle_id,
            amount=payment_code_record.amount,
            payment_type=payment_code_record.payment_type,
            payment_method=payment.payment_method,
            status="completed"
        )
        db.add(payment_record)
        db.commit()
        db.refresh(payment_record)

        return PaymentResponse(**payment_record.__dict__)
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing payment: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/payments", response_model=List[PaymentResponse])
async def get_payments(db: Annotated[Session, Depends(get_db)]):
    payments = db.query(PaymentDB).all()
    return [PaymentResponse(**p.__dict__) for p in payments]


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
