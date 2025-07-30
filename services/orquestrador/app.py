# ./services/orquestrador/app.py
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
    PaymentRefundedEvent, PaymentRefundFailedEvent,
    CancelPurchaseCommand, PurchaseCancelledEvent, CancellationFailedEvent
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
    "purchase.cancel": f"projects/{PROJECT_ID}/topics/commands.purchase.cancel",
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
    "purchase.cancelled": f"projects/{PROJECT_ID}/topics/events.purchase.cancelled",
    "purchase.cancellation_failed": f"projects/{PROJECT_ID}/topics/events.purchase.cancellation_failed",
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
    "purchase.cancelled": f"projects/{PROJECT_ID}/subscriptions/orquestrador-purchase-cancelled-sub",
    "purchase.cancellation_failed": f"projects/{PROJECT_ID}/subscriptions/orquestrador-purchase-cancellation-failed-sub",
}


class VehicleDB(Base):
    __tablename__ = "vehicles_cache"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String)
    model = Column(String)
    year = Column(Integer)
    color = Column(String)
    price = Column(Float)
    license_plate = Column(String)
    is_reserved = Column(String, default="false")
    is_sold = Column(String, default="false")
    created_at = Column(DateTime, default=datetime.now)


class CustomerDB(Base):
    __tablename__ = "customers_cache"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String)
    email = Column(String)
    phone = Column(String)
    document = Column(String)
    account_balance = Column(Float, default=0.0)
    credit_limit = Column(Float, default=0.0)
    used_credit = Column(Float, default=0.0)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.now)

    @property
    def available_credit(self):
        return max(0, self.credit_limit - self.used_credit)

    def can_purchase(self, amount: float, payment_type: str) -> bool:
        if payment_type == "cash":
            return self.account_balance >= amount
        elif payment_type == "credit":
            return self.available_credit >= amount
        return False


class SagaStateDB(Base):
    __tablename__ = "saga_states"
    id = Column(Integer, primary_key=True, index=True)
    transaction_id = Column(String, unique=True, index=True)
    customer_id = Column(Integer, nullable=True)
    vehicle_id = Column(Integer, nullable=True)
    amount = Column(Float, nullable=True)
    payment_type = Column(String, nullable=True)
    status = Column(String)
    current_step = Column(String, nullable=True)
    context = Column(JSON, default=dict)
    created_at = Column(DateTime, default=datetime.now)
    updated_at = Column(DateTime, default=datetime.now, onupdate=datetime.now)


class PurchaseRequest(BaseModel):
    customer_id: int
    vehicle_id: int
    payment_type: str = Field(..., pattern="^(cash|credit)$")


class SagaStateResponse(BaseModel):
    transaction_id: str
    customer_id: Optional[int]
    vehicle_id: Optional[int]
    amount: Optional[float]
    payment_type: Optional[str]
    status: str
    current_step: Optional[str]
    context: dict
    created_at: datetime
    updated_at: datetime


class PurchaseResponse(BaseModel):
    message: str
    transaction_id: str
    saga_status: str
    vehicle_price: Optional[float] = None
    payment_type: str


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


async def get_vehicle_info(vehicle_id: int) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"http://veiculo-service:8080/vehicles/{vehicle_id}")
            if response.status_code == 200:
                return response.json()
            return None
    except Exception as e:
        logger.error(f"Error fetching vehicle {vehicle_id}: {e}")
        return None


async def get_customer_info(customer_id: int) -> Optional[dict]:
    try:
        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"http://cliente-service:8080/customers/{customer_id}")
            if response.status_code == 200:
                return response.json()
            return None
    except Exception as e:
        logger.error(f"Error fetching customer {customer_id}: {e}")
        return None


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
        logger.info(f"Received CreditReleasedEvent: {event.model_dump_json()}")

        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()

        if saga_state:
            # Verificar se é um cancelamento
            if saga_state.status == "CANCELLING":
                await handle_cancellation_credit_released_event(message)
                return

            # Lógica original para compensação normal
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
                    amount=saga_state.amount,
                    payment_type=saga_state.payment_type
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
                    amount=saga_state.amount,
                    payment_type=saga_state.payment_type
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
            f"Received VehicleReleasedEvent: {event.model_dump_json()}")

        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()

        if saga_state:
            # Verificar se é um cancelamento
            if saga_state.status == "CANCELLING":
                await handle_cancellation_vehicle_released_event(message)
                return

            # Lógica original para compensação normal
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
                        amount=saga_state.amount,
                        payment_type=saga_state.payment_type
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
        # NOVOS - Adicionar estas linhas
        EVENT_TOPICS["purchase.cancelled"]: handle_purchase_cancelled_event,
        EVENT_TOPICS["purchase.cancellation_failed"]: handle_purchase_cancellation_failed_event,
    }

    # Iterar usando as chaves dos EVENT_TOPICS (não EVENT_SUBSCRIPTIONS)
    for topic_path, handler in event_handlers.items():
        # Encontrar a chave correspondente em EVENT_SUBSCRIPTIONS
        event_type = None
        for key, topic in EVENT_TOPICS.items():
            if topic == topic_path:
                event_type = key
                break

        if event_type and event_type in EVENT_SUBSCRIPTIONS:
            subscription_path = EVENT_SUBSCRIPTIONS[event_type]

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
                callback=lambda message, h=handler: loop.create_task(
                    h(message))
            )
            futures.append(future)

    logger.info("All Pub/Sub listeners started.")


@app.post("/purchase", response_model=PurchaseResponse, status_code=status.HTTP_202_ACCEPTED)
async def start_purchase_saga(request: PurchaseRequest, db: Annotated[Session, Depends(get_db)]):
    transaction_id = str(uuid.uuid4())

    # 1. Buscar e validar veículo
    vehicle_info = await get_vehicle_info(request.vehicle_id)
    if not vehicle_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Vehicle not found"
        )

    if vehicle_info.get("is_sold") or vehicle_info.get("is_reserved"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Vehicle is not available for purchase"
        )

    vehicle_price = vehicle_info.get("price")
    if not vehicle_price or vehicle_price <= 0:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid vehicle price"
        )

    # 2. Buscar e validar cliente
    customer_info = await get_customer_info(request.customer_id)
    if not customer_info:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Customer not found"
        )

    # 3. Validar capacidade de pagamento
    if request.payment_type == "cash":
        if customer_info.get("account_balance", 0) < vehicle_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient account balance"
            )
    elif request.payment_type == "credit":
        if customer_info.get("available_credit", 0) < vehicle_price:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient credit limit"
            )

    # 4. Criar estado da SAGA
    saga_state = SagaStateDB(
        transaction_id=transaction_id,
        customer_id=request.customer_id,
        vehicle_id=request.vehicle_id,
        amount=vehicle_price,  # Preço real do veículo
        payment_type=request.payment_type,
        status="STARTED",
        current_step="CREDIT_RESERVATION",
        context={
            "vehicle_info": {
                "brand": vehicle_info.get("brand"),
                "model": vehicle_info.get("model"),
                "year": vehicle_info.get("year"),
                "price": vehicle_price
            },
            "customer_info": {
                "name": customer_info.get("name"),
                "email": customer_info.get("email")
            }
        }
    )
    db.add(saga_state)
    db.commit()
    db.refresh(saga_state)
    logger.info(f"Saga {transaction_id} started. Initial state saved.")

    try:
        # 5. Iniciar SAGA com comando de reserva de crédito
        await publish_command(
            COMMAND_TOPICS["credit.reserve"],
            ReserveCreditCommand(
                transaction_id=transaction_id,
                customer_id=request.customer_id,
                amount=vehicle_price,
                payment_type=request.payment_type
            ),
            transaction_id
        )
        logger.info(
            f"Command ReserveCredit for saga {transaction_id} published.")

        return PurchaseResponse(
            message="Purchase saga initiated. Credit reservation pending.",
            transaction_id=transaction_id,
            saga_status="IN_PROGRESS",
            vehicle_price=vehicle_price,
            payment_type=request.payment_type
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


@app.post("/purchase/{transaction_id}/cancel")
async def cancel_purchase(transaction_id: str, db: Annotated[Session, Depends(get_db)]):
    """Cancela uma compra em andamento."""

    # Buscar estado da SAGA
    saga_state = db.query(SagaStateDB).filter(
        SagaStateDB.transaction_id == transaction_id).first()

    if not saga_state:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Transaction not found"
        )

    # Verificar se pode ser cancelada
    if saga_state.status in ["COMPLETED", "CANCELLED", "FAILED", "FAILED_COMPENSATED"]:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Cannot cancel transaction with status: {saga_state.status}"
        )

    if saga_state.status in ["CANCELLING", "CANCELLATION_REQUESTED"]:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cancellation already in progress"
        )

    # Marcar como cancelamento solicitado
    saga_state.status = "CANCELLATION_REQUESTED"
    saga_state.context["cancellation_reason"] = "Customer requested cancellation"
    saga_state.context["cancellation_requested_at"] = datetime.now(
    ).isoformat()
    db.add(saga_state)
    db.commit()

    # Iniciar processo de cancelamento baseado no step atual
    await initiate_cancellation_process(saga_state, db)

    return {
        "message": "Cancellation initiated",
        "transaction_id": transaction_id,
        "current_step": saga_state.current_step,
        "status": saga_state.status
    }


async def initiate_cancellation_process(saga_state: SagaStateDB, db: Session):
    """Inicia o processo de cancelamento baseado no step atual."""

    current_step = saga_state.current_step
    transaction_id = saga_state.transaction_id

    logger.info(
        f"Initiating cancellation for transaction {transaction_id} at step {current_step}")

    # Salvar o step original para referência
    saga_state.context["original_step"] = current_step

    # Atualizar status para CANCELLING
    saga_state.status = "CANCELLING"
    db.add(saga_state)
    db.commit()

    try:
        if current_step in ["CREDIT_RESERVATION", "STARTED"]:
            # Se ainda está na reserva de crédito ou apenas iniciou, só liberar crédito
            logger.info(
                f"Cancelling at early stage {current_step} - releasing credit only")
            await publish_command(
                COMMAND_TOPICS["credit.release"],
                ReleaseCreditCommand(
                    transaction_id=transaction_id,
                    customer_id=saga_state.customer_id,
                    amount=saga_state.amount,
                    payment_type=saga_state.payment_type
                ),
                transaction_id
            )
            saga_state.current_step = "CANCELLATION_CREDIT_RELEASE"

        elif current_step == "VEHICLE_RESERVATION":
            # Liberar veículo e depois crédito
            logger.info(
                f"Cancelling at vehicle reservation stage - releasing vehicle first")
            await publish_command(
                COMMAND_TOPICS["vehicle.release"],
                ReleaseVehicleCommand(
                    transaction_id=transaction_id,
                    vehicle_id=saga_state.vehicle_id
                ),
                transaction_id
            )
            saga_state.current_step = "CANCELLATION_VEHICLE_RELEASE"

        elif current_step in ["PAYMENT_CODE_GENERATION", "PAYMENT_PROCESSING"]:
            # Liberar veículo, depois crédito
            logger.info(
                f"Cancelling at payment stage {current_step} - releasing vehicle first")
            await publish_command(
                COMMAND_TOPICS["vehicle.release"],
                ReleaseVehicleCommand(
                    transaction_id=transaction_id,
                    vehicle_id=saga_state.vehicle_id
                ),
                transaction_id
            )
            saga_state.current_step = "CANCELLATION_VEHICLE_RELEASE"

        elif current_step == "MARK_VEHICLE_AS_SOLD":
            # Transação já muito avançada, pode ser complexo cancelar
            logger.warning(
                f"Cancelling at advanced stage {current_step} - rejecting cancellation")
            saga_state.status = "CANCELLATION_FAILED"
            saga_state.context["cancellation_error"] = "Transaction too advanced to cancel"
            await publish_event(
                EVENT_TOPICS["purchase.cancellation_failed"],
                CancellationFailedEvent(
                    transaction_id=transaction_id,
                    reason="Transaction too advanced to cancel - vehicle sale process already initiated",
                    current_step=current_step
                ),
                transaction_id
            )
        elif current_step == "SAGA_COMPLETE":
            # Transação já completada
            logger.warning(
                f"Attempting to cancel completed transaction {transaction_id}")
            saga_state.status = "CANCELLATION_FAILED"
            saga_state.context["cancellation_error"] = "Transaction already completed"
            await publish_event(
                EVENT_TOPICS["purchase.cancellation_failed"],
                CancellationFailedEvent(
                    transaction_id=transaction_id,
                    reason="Transaction already completed",
                    current_step=current_step
                ),
                transaction_id
            )
        else:
            # Step desconhecido
            logger.error(f"Unknown step for cancellation: {current_step}")
            saga_state.status = "CANCELLATION_FAILED"
            saga_state.context["cancellation_error"] = f"Unknown step: {current_step}"
            await publish_event(
                EVENT_TOPICS["purchase.cancellation_failed"],
                CancellationFailedEvent(
                    transaction_id=transaction_id,
                    reason=f"Cannot cancel at unknown step: {current_step}",
                    current_step=current_step
                ),
                transaction_id
            )

        db.add(saga_state)
        db.commit()
        logger.info(
            f"Cancellation process initiated for {transaction_id}, new step: {saga_state.current_step}")

    except Exception as e:
        logger.error(
            f"Error initiating cancellation for {transaction_id}: {e}")
        saga_state.status = "CANCELLATION_FAILED"
        saga_state.context["cancellation_error"] = str(e)
        db.add(saga_state)
        db.commit()


async def handle_cancellation_credit_released_event(message):
    """Handler para quando o crédito é liberado durante cancelamento."""
    db = SessionLocal()
    try:
        event = CreditReleasedEvent.model_validate_json(message.data)
        logger.info(
            f"Received CreditReleasedEvent during cancellation: {event.model_dump_json()}")

        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()

        if saga_state and saga_state.status == "CANCELLING":
            logger.info(
                f"Processing credit release for cancellation of {event.transaction_id}, current step: {saga_state.current_step}")

            if saga_state.current_step == "CANCELLATION_CREDIT_RELEASE":
                # Cancelamento completo
                logger.info(
                    f"Finalizing cancellation for {event.transaction_id}")
                saga_state.status = "CANCELLED"
                saga_state.current_step = "CANCELLATION_COMPLETE"

                await publish_event(
                    EVENT_TOPICS["purchase.cancelled"],
                    PurchaseCancelledEvent(
                        transaction_id=event.transaction_id,
                        customer_id=saga_state.customer_id,
                        vehicle_id=saga_state.vehicle_id,
                        cancelled_step=saga_state.context.get(
                            "original_step", "UNKNOWN"),
                        reason=saga_state.context.get(
                            "cancellation_reason", "Customer requested cancellation"),
                        compensation_completed=True
                    ),
                    event.transaction_id
                )
                logger.info(
                    f"Purchase {event.transaction_id} successfully cancelled")
            else:
                logger.warning(
                    f"Received credit released event for cancellation but step is {saga_state.current_step}, not CANCELLATION_CREDIT_RELEASE")

        db.add(saga_state)
        db.commit()
        message.ack()

    except Exception as e:
        logger.error(f"Error handling cancellation credit released: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_cancellation_vehicle_released_event(message):
    """Handler para quando o veículo é liberado durante cancelamento."""
    db = SessionLocal()
    try:
        event = VehicleReleasedEvent.model_validate_json(message.data)
        logger.info(
            f"Received VehicleReleasedEvent during cancellation: {event.model_dump_json()}")

        saga_state = db.query(SagaStateDB).filter(
            SagaStateDB.transaction_id == event.transaction_id).first()

        if saga_state and saga_state.status == "CANCELLING":
            logger.info(
                f"Processing vehicle release for cancellation of {event.transaction_id}, current step: {saga_state.current_step}")

            if saga_state.current_step == "CANCELLATION_VEHICLE_RELEASE":
                # Agora liberar crédito
                logger.info(
                    f"Vehicle released for cancellation {event.transaction_id}, now releasing credit")
                saga_state.current_step = "CANCELLATION_CREDIT_RELEASE"
                db.add(saga_state)
                db.commit()

                await publish_command(
                    COMMAND_TOPICS["credit.release"],
                    ReleaseCreditCommand(
                        transaction_id=event.transaction_id,
                        customer_id=saga_state.customer_id,
                        amount=saga_state.amount,
                        payment_type=saga_state.payment_type
                    ),
                    event.transaction_id
                )
            else:
                logger.warning(
                    f"Received vehicle released event for cancellation but step is {saga_state.current_step}, not CANCELLATION_VEHICLE_RELEASE")

        message.ack()

    except Exception as e:
        logger.error(f"Error handling cancellation vehicle released: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_purchase_cancelled_event(message):
    """Handler para evento de compra cancelada."""
    try:
        event = PurchaseCancelledEvent.model_validate_json(message.data)
        logger.info(
            f"Purchase cancelled successfully: {event.model_dump_json()}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling purchase cancelled event: {e}")
        message.ack()


async def handle_purchase_cancellation_failed_event(message):
    """Handler para evento de falha no cancelamento."""
    try:
        event = CancellationFailedEvent.model_validate_json(message.data)
        logger.error(
            f"Purchase cancellation failed: {event.model_dump_json()}")
        message.ack()
    except Exception as e:
        logger.error(f"Error handling purchase cancellation failed event: {e}")
        message.ack()

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
