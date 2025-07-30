# ./services/veiculo-service/app.py
from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, Field, ValidationError
from typing import List, Optional, Annotated
import os
import logging
from datetime import datetime
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text, Boolean
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session
from sqlalchemy.exc import IntegrityError

from google.cloud import pubsub_v1
import json
import asyncio
from shared.models import (
    ReserveVehicleCommand, ReleaseVehicleCommand,
    VehicleReservedEvent, VehicleReservationFailedEvent, VehicleReleasedEvent
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

RESERVE_VEHICLE_COMMAND_TOPIC = f"projects/{PROJECT_ID}/topics/commands.vehicle.reserve"
RELEASE_VEHICLE_COMMAND_TOPIC = f"projects/{PROJECT_ID}/topics/commands.vehicle.release"

RESERVE_VEHICLE_SUBSCRIPTION = f"projects/{PROJECT_ID}/subscriptions/veiculo-service-reserve-vehicle-sub"
RELEASE_VEHICLE_SUBSCRIPTION = f"projects/{PROJECT_ID}/subscriptions/veiculo-service-release-vehicle-sub"

VEHICLE_RESERVED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.vehicle.reserved"
VEHICLE_RESERVATION_FAILED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.vehicle.reservation_failed"
VEHICLE_RELEASED_EVENT_TOPIC = f"projects/{PROJECT_ID}/topics/events.vehicle.released"


class VehicleDB(Base):
    __tablename__ = "vehicles"
    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, index=True)
    model = Column(String, index=True)
    year = Column(Integer)
    color = Column(String)
    price = Column(Float)
    license_plate = Column(String, unique=True, index=True)
    is_reserved = Column(Boolean, default=False)
    is_sold = Column(Boolean, default=False)
    created_at = Column(DateTime, default=datetime.now)


class VehicleCreate(BaseModel):
    brand: str = Field(..., min_length=2, max_length=50)
    model: str = Field(..., min_length=2, max_length=50)
    year: int = Field(..., ge=1900, le=datetime.now().year + 1)
    color: str = Field(..., min_length=3, max_length=30)
    price: float = Field(..., gt=0)
    license_plate: str = Field(..., min_length=7, max_length=10)


class VehicleUpdate(BaseModel):
    brand: Optional[str] = Field(None, min_length=2, max_length=50)
    model: Optional[str] = Field(None, min_length=2, max_length=50)
    year: Optional[int] = Field(None, ge=1900, le=datetime.now().year + 1)
    color: Optional[str] = Field(None, min_length=3, max_length=30)
    price: Optional[float] = Field(None, gt=0)
    license_plate: Optional[str] = Field(None, min_length=7, max_length=10)


class VehicleResponse(BaseModel):
    id: int
    brand: str
    model: str
    year: int
    color: str
    price: float
    license_plate: str
    is_reserved: bool
    is_sold: bool
    created_at: datetime

    @classmethod
    def from_orm_masked_license_plate(cls, obj: VehicleDB):
        obj_dict = obj.__dict__.copy()
        if obj_dict.get('license_plate'):
            lp = obj_dict['license_plate']
            obj_dict['license_plate'] = '*' * (len(lp) - 3) + lp[-3:]
        return cls(**obj_dict)


class VehiclesResponse(BaseModel):
    vehicles: List[VehicleResponse]
    total: int
    timestamp: datetime


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def create_tables():
    logger.info("Creating database tables for Vehicle Service...")
    Base.metadata.create_all(bind=engine)
    logger.info("Vehicle Service database tables created.")


app = FastAPI(
    title="Vehicle Service API",
    description="API para gerenciamento de veículos",
    version="1.0.0"
)


@app.on_event("startup")
async def startup_event():
    create_tables()
    asyncio.create_task(subscribe_to_vehicle_commands())


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
        service='vehicle-service',
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


async def handle_reserve_vehicle_command(message):
    db = SessionLocal()
    try:
        command = ReserveVehicleCommand.model_validate_json(message.data)
        logger.info(
            f"Received ReserveVehicleCommand: {command.model_dump_json()}")

        vehicle = db.query(VehicleDB).filter(
            VehicleDB.id == command.vehicle_id).first()

        if not vehicle:
            await publish_event(
                VEHICLE_RESERVATION_FAILED_EVENT_TOPIC,
                VehicleReservationFailedEvent(
                    transaction_id=command.transaction_id,
                    vehicle_id=command.vehicle_id,
                    reason="Vehicle not found"
                ),
                command.transaction_id
            )
            message.ack()
            return

        if vehicle.is_reserved or vehicle.is_sold:
            await publish_event(
                VEHICLE_RESERVATION_FAILED_EVENT_TOPIC,
                VehicleReservationFailedEvent(
                    transaction_id=command.transaction_id,
                    vehicle_id=command.vehicle_id,
                    reason="Vehicle already reserved or sold"
                ),
                command.transaction_id
            )
            message.ack()
            return

        vehicle.is_reserved = True
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)

        await publish_event(
            VEHICLE_RESERVED_EVENT_TOPIC,
            VehicleReservedEvent(
                transaction_id=command.transaction_id,
                vehicle_id=vehicle.id,
                vehicle_price=vehicle.price
            ),
            command.transaction_id
        )
        logger.info(f"Vehicle {vehicle.id} reserved.")
        message.ack()

    except ValidationError as e:
        logger.error(
            f"Validation error for ReserveVehicleCommand: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error processing ReserveVehicleCommand: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def handle_release_vehicle_command(message):
    db = SessionLocal()
    try:
        command = ReleaseVehicleCommand.model_validate_json(message.data)
        logger.info(
            f"Received ReleaseVehicleCommand: {command.model_dump_json()}")

        vehicle = db.query(VehicleDB).filter(
            VehicleDB.id == command.vehicle_id).first()

        if not vehicle:
            logger.warning(
                f"Attempted to release non-existent vehicle {command.vehicle_id}")
            message.ack()
            return

        if vehicle.is_reserved and not vehicle.is_sold:
            vehicle.is_reserved = False
            db.add(vehicle)
            db.commit()
            db.refresh(vehicle)
            logger.info(f"Vehicle {vehicle.id} released.")
        else:
            logger.info(
                f"Vehicle {vehicle.id} not reserved or already sold, no action needed for release.")

        await publish_event(
            VEHICLE_RELEASED_EVENT_TOPIC,
            VehicleReleasedEvent(
                transaction_id=command.transaction_id,
                vehicle_id=vehicle.id
            ),
            command.transaction_id
        )
        message.ack()

    except ValidationError as e:
        logger.error(
            f"Validation error for ReleaseVehicleCommand: {e} - Data: {message.data}")
        message.ack()
    except Exception as e:
        logger.error(f"Error processing ReleaseVehicleCommand: {e}")
        db.rollback()
        message.ack()
    finally:
        db.close()


async def subscribe_to_vehicle_commands():
    loop = asyncio.get_event_loop()

    try:
        publisher.create_topic(request={"name": RESERVE_VEHICLE_COMMAND_TOPIC})
        logger.info(f"Topic {RESERVE_VEHICLE_COMMAND_TOPIC} ensured.")
    except Exception as e:
        if "Resource already exists" not in str(e):
            logger.error(
                f"Error creating topic {RESERVE_VEHICLE_COMMAND_TOPIC}: {e}")
    try:
        subscriber.create_subscription(request={
                                       "name": RESERVE_VEHICLE_SUBSCRIPTION, "topic": RESERVE_VEHICLE_COMMAND_TOPIC})
        logger.info(f"Subscription {RESERVE_VEHICLE_SUBSCRIPTION} ensured.")
    except Exception as e:
        if "Resource already exists" not in str(e):
            logger.error(
                f"Error creating subscription {RESERVE_VEHICLE_SUBSCRIPTION}: {e}")

    try:
        publisher.create_topic(request={"name": RELEASE_VEHICLE_COMMAND_TOPIC})
        logger.info(f"Topic {RELEASE_VEHICLE_COMMAND_TOPIC} ensured.")
    except Exception as e:
        if "Resource already exists" not in str(e):
            logger.error(
                f"Error creating topic {RELEASE_VEHICLE_COMMAND_TOPIC}: {e}")
    try:
        subscriber.create_subscription(request={
                                       "name": RELEASE_VEHICLE_SUBSCRIPTION, "topic": RELEASE_VEHICLE_COMMAND_TOPIC})
        logger.info(f"Subscription {RELEASE_VEHICLE_SUBSCRIPTION} ensured.")
    except Exception as e:
        if "Resource already exists" not in str(e):
            logger.error(
                f"Error creating subscription {RELEASE_VEHICLE_SUBSCRIPTION}: {e}")

    logger.info(f"Listening for messages on {RESERVE_VEHICLE_SUBSCRIPTION}")
    streaming_pull_future_reserve = subscriber.subscribe(
        RESERVE_VEHICLE_SUBSCRIPTION,
        callback=lambda message: loop.create_task(
            handle_reserve_vehicle_command(message))
    )

    logger.info(f"Listening for messages on {RELEASE_VEHICLE_SUBSCRIPTION}")
    streaming_pull_future_release = subscriber.subscribe(
        RELEASE_VEHICLE_SUBSCRIPTION,
        callback=lambda message: loop.create_task(
            handle_release_vehicle_command(message))
    )


@app.post("/vehicles", response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle(vehicle: VehicleCreate, db: Annotated[Session, Depends(get_db)]):
    try:
        db_vehicle = VehicleDB(**vehicle.model_dump())
        db.add(db_vehicle)
        db.commit()
        db.refresh(db_vehicle)
        return VehicleResponse.from_orm_masked_license_plate(db_vehicle)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Vehicle with this license plate already exists"
        )
    except Exception as e:
        logger.error(f"Error creating vehicle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.put("/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def update_vehicle(vehicle_id: int, vehicle_update: VehicleUpdate, db: Annotated[Session, Depends(get_db)]):
    try:
        db_vehicle = db.query(VehicleDB).filter(
            VehicleDB.id == vehicle_id).first()
        if not db_vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )

        # Não permitir edição de veículos reservados ou vendidos
        if db_vehicle.is_reserved or db_vehicle.is_sold:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Cannot edit vehicle that is reserved or sold"
            )

        update_data = vehicle_update.model_dump(exclude_unset=True)
        for field, value in update_data.items():
            setattr(db_vehicle, field, value)

        db.add(db_vehicle)
        db.commit()
        db.refresh(db_vehicle)
        return VehicleResponse.from_orm_masked_license_plate(db_vehicle)
    except IntegrityError:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="License plate already exists for another vehicle"
        )
    except Exception as e:
        logger.error(f"Error updating vehicle: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )


@app.get("/vehicles", response_model=VehiclesResponse)
async def get_vehicles(
    db: Annotated[Session, Depends(get_db)],
    status_filter: Optional[str] = None,
    sort_by: Optional[str] = "price_asc"
):
    query = db.query(VehicleDB)

    # Filtrar por status
    if status_filter == "available":
        query = query.filter(VehicleDB.is_reserved ==
                             False, VehicleDB.is_sold == False)
    elif status_filter == "sold":
        query = query.filter(VehicleDB.is_sold == True)
    elif status_filter == "reserved":
        query = query.filter(VehicleDB.is_reserved == True,
                             VehicleDB.is_sold == False)

    # Ordenar
    if sort_by == "price_asc":
        query = query.order_by(VehicleDB.price.asc())
    elif sort_by == "price_desc":
        query = query.order_by(VehicleDB.price.desc())
    elif sort_by == "year_desc":
        query = query.order_by(VehicleDB.year.desc())
    elif sort_by == "brand_asc":
        query = query.order_by(VehicleDB.brand.asc())

    vehicles = query.all()
    vehicles_masked = [
        VehicleResponse.from_orm_masked_license_plate(v) for v in vehicles]
    return VehiclesResponse(vehicles=vehicles_masked, total=len(vehicles), timestamp=datetime.now())


@app.get("/vehicles/{vehicle_id}", response_model=VehicleResponse)
async def get_vehicle(vehicle_id: int, db: Annotated[Session, Depends(get_db)]):
    vehicle = db.query(VehicleDB).filter(VehicleDB.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")
    return VehicleResponse.from_orm_masked_license_plate(vehicle)


@app.patch("/vehicles/{vehicle_id}/mark_as_sold", response_model=VehicleResponse)
async def mark_vehicle_as_sold(vehicle_id: int, db: Annotated[Session, Depends(get_db)]):
    vehicle = db.query(VehicleDB).filter(VehicleDB.id == vehicle_id).first()
    if not vehicle:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="Vehicle not found")

    vehicle.is_sold = True
    vehicle.is_reserved = False
    db.add(vehicle)
    db.commit()
    db.refresh(vehicle)

    logger.info(f"Vehicle {vehicle_id} marked as sold.")
    return VehicleResponse.from_orm_masked_license_plate(vehicle)

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
