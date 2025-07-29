from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Annotated
import os
import logging
from datetime import datetime
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError
from google.cloud import pubsub_v1
import json
import asyncio
from shared.models import (
    ReserveCreditCommand, ReleaseCreditCommand,
    CreditReservedEvent, CreditReservationFailedEvent, CreditReleasedEvent
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

RESERVE_CREDIT_COMMAND_TOPIC = f"projects/{PROJECT_ID}/topics/commands.credit.reserve"
RELEASE_CREDIT_COMMAND_TOPIC = f"projects/{PROJECT_ID}/topics/commands.credit.release"
RESERVE_CREDIT_SUBSCRIPTION = f"projects/{PROJECT_ID}/subscriptions/cliente-service-reserve-credit-sub"
RELEASE_CREDIT_SUBSCRIPTION = f"projects/{PROJECT_ID}/subscriptions/cliente-service-release-credit-sub"
CREDIT_RESERVED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.credit.reserved"
CREDIT_RESERVATION_FAILED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.credit.reservation_failed"
CREDIT_RELEASED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.credit.released"


class CustomerDB(Base):
    __tablename__ = "customers"
    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    document = Column(String, unique=True, index=True)
    credit_limit = Column(Float)
    available_credit = Column(Float, nullable=False, default=0.0)
    status = Column(String, default="active")
    created_at = Column(DateTime, default=datetime.now)


class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=3, max_length=100)
    email: str = Field(..., max_length=100)
    phone: str = Field(..., min_length=10, max_length=20)
    document: str = Field(..., min_length=11, max_length=11)
    credit_limit: float = Field(..., ge=0.0)


class CustomerResponse(BaseModel):
    id: int
    name: str
    email: str
    phone: str
    document: str
    credit_limit: float
    available_credit: float
    status: str
    created_at: datetime

    @classmethod
    def from_orm_masked_document(cls, obj: CustomerDB):
        obj_dict = obj.__dict__.copy()
        if obj_dict.get('document'):
            doc = obj_dict['document']
            obj_dict['document'] = '*' * (len(doc) - 4) + doc[-4:]

        if obj_dict.get('available_credit') is None:
            obj_dict['available_credit'] = obj_dict.get('credit_limit', 0.0)

        return cls(**obj_dict)


class CustomersResponse(BaseModel):
    customers: List[CustomerResponse]
    total: int
    timestamp: datetime


class MessageResponse(BaseModel):
    message: str
    customer_id: int
    amount: float
    available_credit: Optional[float] = None


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    logger.info("Creating database tables for Customer Service...")
    Base.metadata.create_all(bind=engine)
    logger.info("Customer Service database tables created.")


app = FastAPI(
    title="Customer Service API",
    description="API para gerenciamento de clientes e crédito",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    create_tables()
    asyncio.create_task(subscribe_to_credit_commands())


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
        service='customer-service',
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


async def handle_reserve_credit_command(message):
    db = SessionLocal()
    try:
        command = ReserveCreditCommand.model_validate_json(message.data)
        logger.info(
            f"Received ReserveCreditCommand: {command.model_dump_json()}")

        customer = db.query(CustomerDB).filter(
            CustomerDB.id == command.customer_id).first()

        if not customer:
            await publish_event(
                CREDIT_RESERVATION_FAILED_EVENT_TOPIC,
                CreditReservationFailedEvent(
                    transaction_id=command.transaction_id,
                    customer_id=command.customer_id,
                    amount=command.amount,
                    reason="Customer not found"
                ),
                command.transaction_id
            )
            message.ack()
            return

        customer_available_credit = customer.available_credit if customer.available_credit is not None else 0.0

        if customer_available_credit < command.amount:
            await publish_event(
                CREDIT_RESERVATION_FAILED_EVENT_TOPIC,
                CreditReservationFailedEvent(
                    transaction_id=command.transaction_id,
                    customer_id=command.customer_id,
                    amount=command.amount,
                    reason="Insufficient credit"
                ),
                command.transaction_id
            )
            message.ack()
            return

        customer.available_credit -= command.amount
        db.add(customer)
        db.commit()
        db.refresh(customer)

        await publish_event(
            CREDIT_RESERVED_EVENT_TOPIC,
            CreditReservedEvent(
                transaction_id=command.transaction_id,
                customer_id=customer.id,
                amount=command.amount,
                available_credit=customer.available_credit
            ),
            command.transaction_id
        )
        logger.info(
            f"Credit reserved for customer {customer.id}. New available credit: {customer.available_credit}")
        message.ack()

    except ValidationError as e:
        logger.error(
            f"Validation error for ReserveCreditCommand: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error processing ReserveCreditCommand: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_release_credit_command(message):
    db = SessionLocal()
    try:
        command = ReleaseCreditCommand.model_validate_json(message.data)
        logger.info(
            f"Received ReleaseCreditCommand: {command.model_dump_json()}")

        customer = db.query(CustomerDB).filter(
            CustomerDB.id == command.customer_id).first()

        if not customer:
            logger.warning(
                f"Attempted to release credit for non-existent customer {command.customer_id}")
            message.ack()
            return

        customer.available_credit += command.amount
        db.add(customer)
        db.commit()
        db.refresh(customer)

        await publish_event(
            CREDIT_RELEASED_EVENT_TOPIC,
            CreditReleasedEvent(
                transaction_id=command.transaction_id,
                customer_id=customer.id,
                amount=command.amount,
                available_credit=customer.available_credit
            ),
            command.transaction_id
        )
        logger.info(
            f"Credit released for customer {customer.id}. New available credit: {customer.available_credit}")
        message.ack()

    except ValidationError as e:
        logger.error(
            f"Validation error for ReleaseCreditCommand: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error processing ReleaseCreditCommand: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def subscribe_to_credit_commands():
    loop = asyncio.get_event_loop()

    try:
        publisher.create_topic(request={"name": RESERVE_CREDIT_COMMAND_TOPIC})
        logger.info(f"Topic {RESERVE_CREDIT_COMMAND_TOPIC} ensured.")
    except Exception as e:
        if "Resource already exists" not in str(e):
            logger.error(
                f"Error creating topic {RESERVE_CREDIT_COMMAND_TOPIC}: {e}")
    try:
        subscriber.create_subscription(
            request={"name": RESERVE_CREDIT_SUBSCRIPTION, "topic": RESERVE_CREDIT_COMMAND_TOPIC})
        logger.info(f"Subscription {RESERVE_CREDIT_SUBSCRIPTION} ensured.")
    except Exception as e:
        if "Resource already exists" not in str(e):
            logger.error(
                f"Error creating subscription {RESERVE_CREDIT_SUBSCRIPTION}: {e}")

    try:
        publisher.create_topic(request={"name": RELEASE_CREDIT_COMMAND_TOPIC})
        logger.info(f"Topic {RELEASE_CREDIT_COMMAND_TOPIC} ensured.")
    except Exception as e:
        if "Resource already exists" not in str(e):
            logger.error(
                f"Error creating topic {RELEASE_CREDIT_COMMAND_TOPIC}: {e}")
    try:
        subscriber.create_subscription(
            request={"name": RELEASE_CREDIT_SUBSCRIPTION, "topic": RELEASE_CREDIT_COMMAND_TOPIC})
        logger.info(f"Subscription {RELEASE_CREDIT_SUBSCRIPTION} ensured.")
    except Exception as e:
        if "Resource already exists" not in str(e):
            logger.error(
                f"Error creating subscription {RELEASE_CREDIT_SUBSCRIPTION}: {e}")

    logger.info(f"Listening for messages on {RESERVE_CREDIT_SUBSCRIPTION}")
    streaming_pull_future_reserve = subscriber.subscribe(
        RESERVE_CREDIT_SUBSCRIPTION,
        callback=lambda message: loop.create_task(
            handle_reserve_credit_command(message))
    )

    logger.info(f"Listening for messages on {RELEASE_CREDIT_SUBSCRIPTION}")
    streaming_pull_future_release = subscriber.subscribe(
        RELEASE_CREDIT_SUBSCRIPTION,
        callback=lambda message: loop.create_task(
            handle_release_credit_command(message))
    )


@app.post("/customers", response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(customer: CustomerCreate, db: Annotated[Session, Depends(get_db)]):
    try:
        db_customer = CustomerDB(
            name=customer.name,
            email=customer.email,
            phone=customer.phone,
            document=customer.document,
            credit_limit=customer.credit_limit,
            available_credit=customer.credit_limit
        )
        db.add(db_customer)
        db.commit()
        db.refresh(db_customer)
        return CustomerResponse.from_orm_masked_document(db_customer)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Customer with this document or email already exists"
        )
    except Exception as e:
        logger.error(f"Error creating customer: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/customers", response_model=CustomersResponse)
async def get_customers(db: Annotated[Session, Depends(get_db)]):
    customers = db.query(CustomerDB).all()
    customers_masked = [
        CustomerResponse.from_orm_masked_document(c) for c in customers]
    return CustomersResponse(customers=customers_masked, total=len(customers), timestamp=datetime.now())


@app.get("/customers/{customer_id}", response_model=CustomerResponse)
async def get_customer(customer_id: int, db: Annotated[Session, Depends(get_db)]):
    customer = db.query(CustomerDB).filter(
        CustomerDB.id == customer_id).first()
    if not customer:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Customer not found")
    return CustomerResponse.from_orm_masked_document(customer)


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
