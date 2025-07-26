from fastapi import FastAPI, HTTPException, status, Query, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Annotated
import os
import logging
from datetime import datetime
import uvicorn
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, text
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker, Session

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
class VehicleDB(Base):
    __tablename__ = "vehicles"

    id = Column(Integer, primary_key=True, index=True)
    brand = Column(String, index=True)
    model = Column(String, index=True)
    year = Column(Integer)
    color = Column(String)
    price = Column(Float)
    status = Column(String, default="available")
    created_at = Column(DateTime, default=datetime.now)
    reserved_at = Column(DateTime, nullable=True)

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

class VehicleCreate(BaseModel):
    brand: str = Field(..., min_length=1, description="Marca do veículo")
    model: str = Field(..., min_length=1, description="Modelo do veículo")
    year: int = Field(..., ge=1900, le=2030, description="Ano do veículo")
    color: str = Field(..., min_length=1, description="Cor do veículo")
    price: float = Field(..., gt=0, description="Preço do veículo")

class VehicleResponse(BaseModel):
    id: int
    brand: str
    model: str
    year: int
    color: str
    price: float
    status: str
    created_at: datetime
    reserved_at: Optional[datetime] = None

class VehiclesListResponse(BaseModel):
    vehicles: List[VehicleResponse]
    total: int
    timestamp: datetime

class VehicleReservationResponse(BaseModel):
    message: str
    vehicle_id: int
    status: str

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

@app.get('/vehicles', response_model=VehiclesListResponse, status_code=status.HTTP_200_OK)
async def get_vehicles(
    db: Annotated[Session, Depends(get_db)],
    status_filter: Optional[str] = Query(
        "available", 
        description="Filtrar veículos por status (available, reserved, sold)"
    ),
    sort_by: Optional[str] = Query(
        "price", 
        description="Ordenar por campo (price, year, brand, model)"
    ),
    sort_order: Optional[str] = Query(
        "asc", 
        description="Ordem de classificação (asc, desc)"
    )
):
    try:
        query = db.query(VehicleDB)

        if status_filter:
            query = query.filter(VehicleDB.status == status_filter)
        
        sort_column = None
        if sort_by == 'price':
            sort_column = VehicleDB.price
        elif sort_by == 'year':
            sort_column = VehicleDB.year
        elif sort_by == 'brand':
            sort_column = VehicleDB.brand
        elif sort_by == 'model':
            sort_column = VehicleDB.model
        
        if sort_column:
            if sort_order.lower() == 'desc':
                query = query.order_by(sort_column.desc())
            else:
                query = query.order_by(sort_column.asc())
        
        db_vehicles = query.all()
        
        vehicle_responses = [VehicleResponse(**vehicle.__dict__) for vehicle in db_vehicles]
        
        logger.info(f"Returning {len(vehicle_responses)} vehicles with status '{status_filter}' from DB")
        
        return VehiclesListResponse(
            vehicles=vehicle_responses,
            total=len(vehicle_responses),
            timestamp=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Error fetching vehicles from DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/vehicles', response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle(vehicle_data: VehicleCreate, db: Annotated[Session, Depends(get_db)]):
    try:
        new_vehicle_db = VehicleDB(
            brand=vehicle_data.brand,
            model=vehicle_data.model,
            year=vehicle_data.year,
            color=vehicle_data.color,
            price=vehicle_data.price,
            status='available',
            created_at=datetime.now()
        )
        
        db.add(new_vehicle_db)
        db.commit()
        db.refresh(new_vehicle_db)
        
        logger.info(f"Created new vehicle in DB: {new_vehicle_db.id} - {new_vehicle_db.brand} {new_vehicle_db.model}")
        
        return VehicleResponse(**new_vehicle_db.__dict__)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating vehicle in DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.get('/vehicles/{vehicle_id}', response_model=VehicleResponse, status_code=status.HTTP_200_OK)
async def get_vehicle(vehicle_id: int, db: Annotated[Session, Depends(get_db)]):
    try:
        vehicle = db.query(VehicleDB).filter(VehicleDB.id == vehicle_id).first()
        
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
        
        logger.info(f"Returning vehicle details for ID: {vehicle_id} from DB")
        return VehicleResponse(**vehicle.__dict__)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching vehicle {vehicle_id} from DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/vehicles/{vehicle_id}/reserve', response_model=VehicleReservationResponse)
async def reserve_vehicle(vehicle_id: int, db: Annotated[Session, Depends(get_db)]):
    try:
        vehicle = db.query(VehicleDB).filter(VehicleDB.id == vehicle_id).first()
        
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
            
        if vehicle.status != 'available':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vehicle not available for reservation"
            )
        
        vehicle.status = 'reserved'
        vehicle.reserved_at = datetime.now()
        
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
        
        logger.info(f"Reserved vehicle in DB: {vehicle_id} - {vehicle.brand} {vehicle.model}")
        
        return VehicleReservationResponse(
            message='Vehicle reserved successfully',
            vehicle_id=vehicle_id,
            status='reserved'
        )
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error reserving vehicle in DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/vehicles/{vehicle_id}/release', response_model=VehicleReservationResponse)
async def release_vehicle(vehicle_id: int, db: Annotated[Session, Depends(get_db)]):
    try:
        vehicle = db.query(VehicleDB).filter(VehicleDB.id == vehicle_id).first()
        
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
            
        if vehicle.status != 'reserved':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vehicle is not reserved"
            )
        
        vehicle.status = 'available'
        vehicle.reserved_at = None
        
        db.add(vehicle)
        db.commit()
        db.refresh(vehicle)
        
        logger.info(f"Released vehicle in DB: {vehicle_id} - {vehicle.brand} {vehicle.model}")
        
        return VehicleReservationResponse(
            message='Vehicle released successfully',
            vehicle_id=vehicle_id,
            status='available'
        )
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error releasing vehicle in DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.delete('/vehicles/{vehicle_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(vehicle_id: int, db: Annotated[Session, Depends(get_db)]):
    try:
        vehicle = db.query(VehicleDB).filter(VehicleDB.id == vehicle_id).first()
        
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
        
        db.delete(vehicle)
        db.commit()
        
        logger.info(f"Deleted vehicle from DB: {vehicle_id} - {vehicle.brand} {vehicle.model}")
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error deleting vehicle from DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

if __name__ == '__main__':
    create_tables()
    port = int(os.environ.get('PORT', 8080))
    debug_mode = os.environ.get('DEBUG', '1') == '1'
    
    uvicorn.run(
        "app:app",
        host='0.0.0.0',
        port=port,
        reload=debug_mode,
        log_level="info"
    )