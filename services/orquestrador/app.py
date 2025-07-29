from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Annotated
import os
import logging
from datetime import datetime
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text, JSON
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
import uuid
import json
import asyncio
import httpx

from shared.models import (
    ReserveCreditCommand, ReleaseCreditCommand,
    ReserveVehicleCommand, ReleaseVehicleCommand,
    GeneratePaymentCodeCommand, ProcessPaymentCommand, RefundPaymentCommand,
    CreditReservedEvent, CreditReservationFailedEvent, CreditReleasedEvent,
    VehicleReservedEvent, VehicleReservationFailedEvent, VehicleReleasedEvent,
    PaymentCodeGeneratedEvent, PaymentCodeGenerationFailedEvent,
    PaymentProcessedEvent, PaymentFailedEvent,
    PaymentRefundedEvent, PaymentRefundFailedEvent
)

from google.cloud import pubsub_v1

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

COMMAND_TOPICS = {
    "credit.reserve": f"projects/{PROJECT_ID}/topics/commands.credit.reserve",
    "credit.release": f"projects/{PROJECT_ID}/topics/commands.credit.release",
    "vehicle.reserve": f"projects/{PROJECT_ID}/topics/commands.vehicle.reserve",
    "vehicle.release": f"projects/{PROJECT_ID}/topics/commands.vehicle.release",
    "payment.generate_code": f"projects/{PROJECT_ID}/topics/commands.payment.generate_code",
    "payment.process": f"projects/{PROJECT_ID}/topics/commands.payment.process",
    "payment.refund": f"projects/{PROJECT_ID}/topics/commands.payment.refund",
}

EVENT_TOPICS = {
    "credit.reserved": f"projects/{PROJECT_ID}/topics/events.credit.reserved",
    "credit.reservation_failed": f"projects/{PROJECT_ID}/topics/events.credit.reservation_failed",
    "credit.released": f"projects/{PROJECT_ID}/topics/events.credit.released",
    "vehicle.reserved": f"projects/{PROJECT_ID}/topics/events.vehicle.reserved",
    "vehicle.reservation_failed": f"projects/{PROJECT_ID}/topics/events.vehicle.reservation_failed",
    "vehicle.released": f"projects/{PROJECT_ID}/topics/events.vehicle.released",
    "payment.code_generated": f"projects/{PROJECT_ID}/topics/events.payment.code_generated",
    "payment.code_generation_failed": f"projects/{PROJECT_ID}/topics/events.payment.code_generation_failed",
    "payment.processed": f"projects/{PROJECT_ID}/topics/events.payment.processed",
    "payment.failed": f"projects/{PROJECT_ID}/topics/events.payment.failed",
    "payment.refunded": f"projects/{PROJECT_ID}/topics/events.payment.refunded",
    "payment.refund_failed": f"projects/{PROJECT_ID}/topics/events.payment.refund_failed",
}

EVENT_SUBSCRIPTIONS = {
    "credit.reserved": f"projects/{PROJECT_ID}/subscriptions/orquestrador-credit-reserved-sub",
    "credit.reservation_failed": f"projects/{PROJECT_ID}/subscriptions/orquestrador-credit-reservation-failed-sub",
    "credit.released": f"projects/{PROJECT_ID}/subscriptions/orquestrador-credit-released-sub",
    "vehicle.reserved": f"projects/{PROJECT_ID}/subscriptions/orquestrador-vehicle-reserved-sub",
    "vehicle.reservation_failed": f"projects/{PROJECT_ID}/subscriptions/orquestrador-vehicle-reservation-failed-sub",
    "vehicle.released": f"projects/{PROJECT_ID}/subscriptions/orquestrador-vehicle-released-sub",
    "payment.code_generated": f"projects/{PROJECT_ID}/subscriptions/orquestrador-payment-code-generated-sub",
    "payment.code_generation_failed": f"projects/{PROJECT_ID}/subscriptions/orquestrador-payment-code-generation-failed-sub",
    "payment.processed": f"projects/{PROJECT_ID}/subscriptions/orquestrador-payment-processed-sub",
    "payment.failed": f"projects/{PROJECT_ID}/subscriptions/orquestrador-payment-failed-sub",
    "payment.refunded": f"projects/{PROJECT_ID}/subscriptions/orquestrador-payment-refunded-sub",
    "payment.refund_failed": f"projects/{PROJECT_ID}/subscriptions/orquestrador-payment-refund-failed-sub",
}


class SagaStateDB(Base):
    __tablename__ = "saga_states"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, unique=True, index=True)
    customer_id = Column(Integer, nullable=True)
    vehicle_id = Column(Integer, nullable=True)
    amount = Column(Float, nullable=True)
    status = Column(String)
    current_step = Column(String, nullable=True)
    context = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class PurchaseRequest(BaseModel):
    customer_id: int
    vehicle_id: int
    amount: float


class SagaStateResponse(BaseModel):
    transaction_id: str
    customer_id: Optional[int]
    vehicle_id: Optional[int]
    amount: Optional[float]
    status: str
    current_step: Optional[str]
    context: dict
    created_at: datetime
    updated_at: datetime


class PurchaseResponse(BaseModel):
    message: str
    transaction_id: str
    saga_status: str


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    logger.info("Creating database tables for Saga Orchestrator Service...")
    Base.metadata.create_all(bind=engine)
    logger.info("Saga Orchestrator Service database tables created.")


app = FastAPI(
    title="Saga Orchestrator Service API",
    description="API para orquestração de transações SAGA",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    create_tables()
    asyncio.create_task(subscribe_to_all_events())


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
        service='orquestrador',
        timestamp=datetime.now(),
        version='1.0.0'
    )


async def publish_command(topic_path: str, command_data: BaseModel, transaction_id: str):
    try:
        data = command_data.model_dump_json().encode("utf-8")
        future = publisher.publish(
            topic_path, data, transaction_id=transaction_id)
        await asyncio.wrap_future(future)
        logger.info(
            f"Published command to {topic_path}: {command_data.model_dump_json()}")
    except Exception as e:
        logger.error(f"Error publishing command to {topic_path}: {e}")


async def handle_credit_reserved_event(message):
    db = SessionLocal()
    try:
        event = CreditReservedEvent.model_validate_json(message.data)
        logger.info(f"Received CreditReservedEvent: {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.info(
                f"Saga {event.transaction_id}: Credit Reserved. Next step: Reserve Vehicle.")
            saga_state.status = "IN_PROGRESS"
            saga_state.current_step = "VEHICLE_RESERVATION"
            db.add(saga_state)
            db.commit()
            await publish_command(
                COMMAND_TOPICS["vehicle.reserve"],
                ReserveVehicleCommand(
                    transaction_id=event.transaction_id, vehicle_id=saga_state.vehicle_id),
                event.transaction_id
            )
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for CreditReservedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling CreditReservedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_credit_reservation_failed_event(message):
    db = SessionLocal()
    try:
        event = CreditReservationFailedEvent.model_validate_json(message.data)
        logger.warning(
            f"Received CreditReservationFailedEvent: {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.error(
                f"Saga {event.transaction_id}: Credit Reservation Failed. Status: FAILED.")
            saga_state.status = "FAILED"
            saga_state.current_step = "CREDIT_RESERVATION_FAILED"
            saga_state.context["error"] = event.reason
            db.add(saga_state)
            db.commit()
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for CreditReservationFailedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling CreditReservationFailedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_credit_released_event(message):
    db = SessionLocal()
    try:
        event = CreditReleasedEvent.model_validate_json(message.data)
        logger.info(
            f"Received CreditReleasedEvent (compensation): {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.info(
                f"Saga {event.transaction_id}: Credit Released (compensation completed).")
            if saga_state.status == "COMPENSATING" and saga_state.current_step == "CREDIT_RELEASE":
                saga_state.status = "FAILED_COMPENSATED"
                saga_state.current_step = "COMPENSATION_COMPLETE"
                db.add(saga_state)
                db.commit()
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for CreditReleasedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling CreditReleasedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_vehicle_reserved_event(message):
    db = SessionLocal()
    try:
        event = VehicleReservedEvent.model_validate_json(message.data)
        logger.info(
            f"Received VehicleReservedEvent: {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.info(
                f"Saga {event.transaction_id}: Vehicle Reserved. Next step: Generate Payment Code.")
            saga_state.status = "IN_PROGRESS"
            saga_state.current_step = "PAYMENT_CODE_GENERATION"
            db.add(saga_state)
            db.commit()
            await publish_command(
                COMMAND_TOPICS["payment.generate_code"],
                GeneratePaymentCodeCommand(
                    transaction_id=event.transaction_id,
                    customer_id=saga_state.customer_id,
                    vehicle_id=saga_state.vehicle_id,
                    amount=saga_state.amount
                ),
                event.transaction_id
            )
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for VehicleReservedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling VehicleReservedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_vehicle_reservation_failed_event(message):
    db = SessionLocal()
    try:
        event = VehicleReservationFailedEvent.model_validate_json(message.data)
        logger.warning(
            f"Received VehicleReservationFailedEvent: {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.error(
                f"Saga {event.transaction_id}: Vehicle Reservation Failed. Initiating compensation (release credit).")
            saga_state.status = "COMPENSATING"
            saga_state.current_step = "CREDIT_RELEASE"
            saga_state.context["error"] = event.reason
            db.add(saga_state)
            db.commit()
            await publish_command(
                COMMAND_TOPICS["credit.release"],
                ReleaseCreditCommand(
                    transaction_id=event.transaction_id,
                    customer_id=saga_state.customer_id,
                    amount=saga_state.amount
                ),
                event.transaction_id
            )
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for VehicleReservationFailedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling VehicleReservationFailedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_vehicle_released_event(message):
    db = SessionLocal()
    try:
        event = VehicleReleasedEvent.model_validate_json(message.data)
        logger.info(
            f"Received VehicleReleasedEvent (compensation): {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.info(
                f"Saga {event.transaction_id}: Vehicle Released (compensation completed).")
            if saga_state.status == "COMPENSATING" and saga_state.current_step == "VEHICLE_RELEASE":
                saga_state.current_step = "CREDIT_RELEASE"
                db.add(saga_state)
                db.commit()
                await publish_command(
                    COMMAND_TOPICS["credit.release"],
                    ReleaseCreditCommand(
                        transaction_id=event.transaction_id,
                        customer_id=saga_state.customer_id,
                        amount=saga_state.amount
                    ),
                    event.transaction_id
                )
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for VehicleReleasedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling VehicleReleasedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_payment_code_generated_event(message):
    db = SessionLocal()
    try:
        event = PaymentCodeGeneratedEvent.model_validate_json(message.data)
        logger.info(
            f"Received PaymentCodeGeneratedEvent: {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.info(
                f"Saga {event.transaction_id}: Payment Code Generated. Next step: Process Payment.")
            saga_state.status = "IN_PROGRESS"
            saga_state.current_step = "PAYMENT_PROCESSING"
            saga_state.context["payment_code"] = event.payment_code
            db.add(saga_state)
            db.commit()
            await publish_command(
                COMMAND_TOPICS["payment.process"],
                ProcessPaymentCommand(
                    transaction_id=event.transaction_id,
                    payment_code=event.payment_code,
                    payment_method="pix"
                ),
                event.transaction_id
            )
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for PaymentCodeGeneratedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling PaymentCodeGeneratedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_payment_code_generation_failed_event(message):
    db = SessionLocal()
    try:
        event = PaymentCodeGenerationFailedEvent.model_validate_json(
            message.data)
        logger.warning(
            f"Received PaymentCodeGenerationFailedEvent: {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.error(
                f"Saga {event.transaction_id}: Payment Code Generation Failed. Initiating compensation (release vehicle, release credit).")
            saga_state.status = "COMPENSATING"
            saga_state.current_step = "VEHICLE_RELEASE"
            saga_state.context["error"] = event.reason
            db.add(saga_state)
            db.commit()
            await publish_command(
                COMMAND_TOPICS["vehicle.release"],
                ReleaseVehicleCommand(
                    transaction_id=event.transaction_id, vehicle_id=saga_state.vehicle_id),
                event.transaction_id
            )
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for PaymentCodeGenerationFailedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling PaymentCodeGenerationFailedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_payment_processed_event(message):
    db = SessionLocal()
    try:
        event = PaymentProcessedEvent.model_validate_json(message.data)
        logger.info(
            f"Received PaymentProcessedEvent: {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.info(
                f"Saga {event.transaction_id}: Payment Processed. Final step: Mark Vehicle as Sold.")
            saga_state.status = "IN_PROGRESS"
            saga_state.current_step = "MARK_VEHICLE_AS_SOLD"
            saga_state.context["payment_id"] = event.payment_id
            db.add(saga_state)
            db.commit()

            vehicle_service_url = f"http://veiculo-service:8080/vehicles/{saga_state.vehicle_id}/mark_as_sold"
            async with httpx.AsyncClient() as client:
                response = await client.patch(vehicle_service_url)
                response.raise_for_status()
                logger.info(
                    f"Vehicle {saga_state.vehicle_id} marked as sold via HTTP PATCH.")

            saga_state.status = "COMPLETED"
            saga_state.current_step = "SAGA_COMPLETE"
            db.add(saga_state)
            db.commit()
            logger.info(
                f"Saga {event.transaction_id}: COMPLETED successfully!")
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for PaymentProcessedEvent: {e} - Data: {message.data}")
        message.ack()
    except httpx.HTTPStatusError as e:
        logger.error(
            f"HTTP error marking vehicle as sold for saga {event.transaction_id}: {e}")
        saga_state.status = "FAILED_REQUIRES_MANUAL_INTERVENTION"
        saga_state.current_step = "MARK_VEHICLE_AS_SOLD_FAILED"
        saga_state.context["error"] = f"Failed to mark vehicle as sold: {e}"
        db.add(saga_state)
        db.commit()
        message.ack()
    except Exception as e:
        logger.error(f"Error handling PaymentProcessedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_payment_failed_event(message):
    db = SessionLocal()
    try:
        event = PaymentFailedEvent.model_validate_json(message.data)
        logger.warning(
            f"Received PaymentFailedEvent: {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.error(
                f"Saga {event.transaction_id}: Payment Failed. Initiating compensation (release vehicle, release credit).")
            saga_state.status = "COMPENSATING"
            saga_state.current_step = "VEHICLE_RELEASE"
            saga_state.context["error"] = event.reason
            db.add(saga_state)
            db.commit()
            await publish_command(
                COMMAND_TOPICS["vehicle.release"],
                ReleaseVehicleCommand(
                    transaction_id=event.transaction_id, vehicle_id=saga_state.vehicle_id),
                event.transaction_id
            )
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for PaymentFailedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling PaymentFailedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_payment_refunded_event(message):
    db = SessionLocal()
    try:
        event = PaymentRefundedEvent.model_validate_json(message.data)
        logger.info(
            f"Received PaymentRefundedEvent (compensation): {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.info(
                f"Saga {event.transaction_id}: Payment Refunded (compensation completed).")
            if saga_state.status == "COMPENSATING" and saga_state.current_step == "PAYMENT_REFUND":
                saga_state.status = "FAILED_COMPENSATED"
                saga_state.current_step = "COMPENSATION_COMPLETE"
                db.add(saga_state)
                db.commit()
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for PaymentRefundedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling PaymentRefundedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_payment_refund_failed_event(message):
    db = SessionLocal()
    try:
        event = PaymentRefundFailedEvent.model_validate_json(message.data)
        logger.error(
            f"Received PaymentRefundFailedEvent: {event.model_dump_json()}")
        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()
        if saga_state:
            logger.critical(
                f"Saga {event.transaction_id}: Payment Refund FAILED. MANUAL INTERVENTION REQUIRED! Reason: {event.reason}")
            saga_state.status = "FAILED_REQUIRES_MANUAL_INTERVENTION"
            saga_state.current_step = "PAYMENT_REFUND_FAILED"
            saga_state.context["compensation_error"] = event.reason
            db.add(saga_state)
            db.commit()
        message.ack()
    except ValidationError as e:
        logger.error(
            f"Validation error for PaymentRefundFailedEvent: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling PaymentRefundFailedEvent: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def subscribe_to_all_events():
    loop = asyncio.get_event_loop()
    futures = []

    event_handlers = {
        EVENT_TOPICS["credit.reserved"]: handle_credit_reserved_event,
        EVENT_TOPICS["credit.reservation_failed"]: handle_credit_reservation_failed_event,
        EVENT_TOPICS["credit.released"]: handle_credit_released_event,
        EVENT_TOPICS["vehicle.reserved"]: handle_vehicle_reserved_event,
        EVENT_TOPICS["vehicle.reservation_failed"]: handle_vehicle_reservation_failed_event,
        EVENT_TOPICS["vehicle.released"]: handle_vehicle_released_event,
        EVENT_TOPICS["payment.code_generated"]: handle_payment_code_generated_event,
        EVENT_TOPICS["payment.code_generation_failed"]: handle_payment_code_generation_failed_event,
        EVENT_TOPICS["payment.processed"]: handle_payment_processed_event,
        EVENT_TOPICS["payment.failed"]: handle_payment_failed_event,
        EVENT_TOPICS["payment.refunded"]: handle_payment_refunded_event,
        EVENT_TOPICS["payment.refund_failed"]: handle_payment_refund_failed_event,
    }

    for event_type, topic_path in EVENT_TOPICS.items():
        subscription_path = EVENT_SUBSCRIPTIONS[event_type]
        handler = event_handlers[topic_path]
        try:
            publisher.create_topic(request={"name": topic_path})
            logger.info(f"Topic {topic_path} ensured.")
        except Exception as e:
            if "Resource already exists" not in str(e):
                logger.error(f"Error ensuring topic {topic_path}: {e}")
        try:
            subscriber.create_subscription(
                request={"name": subscription_path, "topic": topic_path})
            logger.info(f"Subscription {subscription_path} ensured.")
        except Exception as e:
            if "Resource already exists" not in str(e):
                logger.error(
                    f"Error ensuring subscription {subscription_path}: {e}")

        logger.info(f"Listening for messages on {subscription_path}")
        future = subscriber.subscribe(
            subscription_path,
            callback=lambda message, h=handler: loop.create_task(h(message))
        )
        futures.append(future)

    logger.info("All Pub/Sub listeners started.")


@app.post("/purchase", response_model=PurchaseResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_purchase_saga(request: PurchaseRequest, db: Annotated[Session, Depends(get_db)]):
    transaction_id = str(uuid.uuid4())
    saga_state = SagaStateDB(
        transaction_id=transaction_id,
        customer_id=request.customer_id,
        vehicle_id=request.vehicle_id,
        amount=request.amount,
        status="STARTED",
        current_step="CREDIT_RESERVATION",
        context={}
    )
    db.add(saga_state)
    db.commit()
    db.refresh(saga_state)
    logger.info(f"Saga {transaction_id} started. Initial state saved.")

    try:
        await publish_command(
            COMMAND_TOPICS["credit.reserve"],
            ReserveCreditCommand(
                transaction_id=transaction_id,
                customer_id=request.customer_id,
                amount=request.amount
            ),
            transaction_id
        )
        logger.info(
            f"Command ReserveCredit for saga {transaction_id} published.")
        return PurchaseResponse(
            message="Purchase saga initiated. Credit reservation pending.",
            transaction_id=transaction_id,
            saga_status="IN_PROGRESS"
        )
    except Exception as e:
        logger.error(
            f"Failed to publish initial ReserveCredit command for saga {transaction_id}: {e}")
        saga_state.status = "FAILED_INITIAL_COMMAND"
        saga_state.context["error"] = f"Failed to publish initial command: {str(e)}"
        db.add(saga_state)
        db.commit()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to initiate purchase saga: {e}"
        )


@app.get("/saga-states/{transaction_id}", response_model=SagaStateResponse)
async def get_saga_state(transaction_id: str, db: Annotated[Session, Depends(get_db)]):
    saga_state = db.query(SagaStateDB).filter(
        SagaStateDB.transaction_id == transaction_id).first()
    if not saga_state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Saga state not found")
    return SagaStateResponse(**saga_state.__dict__)

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
