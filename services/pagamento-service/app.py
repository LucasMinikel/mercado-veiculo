from fastapi import FastAPI, HTTPException, status, Depends
from pydantic import BaseModel, Field
from typing import List, Optional, Annotated
import os
import logging
from datetime import datetime, timedelta
import uvicorn
import uuid
import random
from sqlalchemy import create_engine, Column, Integer, String, Float, DateTime, Boolean, text
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

class PaymentCodeDB(Base):
    __tablename__ = "payment_codes"

    id = Column(Integer, primary_key=True, index=True)
    payment_code = Column(String, unique=True, index=True)
    customer_id = Column(Integer)
    vehicle_id = Column(Integer)
    amount = Column(Float)
    expires_at = Column(DateTime)
    status = Column(String, default="pending")
    created_at = Column(DateTime, default=datetime.now)

class PaymentDB(Base):
    __tablename__ = "payments"

    id = Column(Integer, primary_key=True, index=True)
    payment_id = Column(String, unique=True, index=True)
    payment_code = Column(String, index=True)
    customer_id = Column(Integer)
    vehicle_id = Column(Integer)
    amount = Column(Float)
    payment_method = Column(String)
    status = Column(String, default="completed")
    processed_at = Column(DateTime, default=datetime.now)
    refunded_at = Column(DateTime, nullable=True)

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
    description="API para gerenciamento de pagamentos e códigos de pagamento",
    version="1.0.0"
)

@app.on_event("startup")
async def startup_event():
    create_tables()

class PaymentCodeRequest(BaseModel):
    customer_id: int = Field(..., description="ID do cliente")
    vehicle_id: int = Field(..., description="ID do veículo")
    amount: float = Field(..., gt=0, description="Valor do pagamento")

class PaymentCodeResponse(BaseModel):
    payment_code: str
    customer_id: int
    vehicle_id: int
    amount: float
    expires_at: datetime
    status: str
    created_at: datetime

class PaymentRequest(BaseModel):
    payment_code: str = Field(..., description="Código de pagamento")
    payment_method: str = Field(..., description="Método de pagamento (pix, card, bank_transfer)")

class PaymentResponse(BaseModel):
    payment_id: str
    payment_code: str
    customer_id: int
    vehicle_id: int
    amount: float
    payment_method: str
    status: str
    processed_at: datetime
    refunded_at: Optional[datetime] = None

class PaymentListResponse(BaseModel):
    payments: List[PaymentResponse]
    total: int
    timestamp: datetime

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

@app.post('/payment-codes', response_model=PaymentCodeResponse, status_code=status.HTTP_201_CREATED)
async def generate_payment_code(request: PaymentCodeRequest, db: Annotated[Session, Depends(get_db)]):
    try:
        payment_code_str = f"PAY-{uuid.uuid4().hex[:8].upper()}"
        expires_at = datetime.now() + timedelta(minutes=30)
        
        new_payment_code_db = PaymentCodeDB(
            payment_code=payment_code_str,
            customer_id=request.customer_id,
            vehicle_id=request.vehicle_id,
            amount=request.amount,
            expires_at=expires_at,
            status='pending',
            created_at=datetime.now()
        )
        
        db.add(new_payment_code_db)
        db.commit()
        db.refresh(new_payment_code_db)
        
        logger.info(f"Generated payment code in DB: {new_payment_code_db.payment_code} for customer {request.customer_id}")
        
        return PaymentCodeResponse(**new_payment_code_db.__dict__)
        
    except Exception as e:
        db.rollback()
        logger.error(f"Error generating payment code in DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/payments', response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def process_payment(request: PaymentRequest, db: Annotated[Session, Depends(get_db)]):
    try:
        payment_code_data = db.query(PaymentCodeDB).filter(PaymentCodeDB.payment_code == request.payment_code).first()
        
        if not payment_code_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment code not found"
            )
        
        if datetime.now() > payment_code_data.expires_at:
            if payment_code_data.status != 'used':
                payment_code_data.status = 'expired'
                db.add(payment_code_data)
                db.commit()
                db.refresh(payment_code_data)
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment code expired"
            )
        
        if payment_code_data.status != 'pending':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment code already processed or expired"
            )
        
        payment_success = random.random() > 0.1
        
        if not payment_success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment processing failed"
            )
        
        payment_id_str = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        new_payment_db = PaymentDB(
            payment_id=payment_id_str,
            payment_code=request.payment_code,
            customer_id=payment_code_data.customer_id,
            vehicle_id=payment_code_data.vehicle_id,
            amount=payment_code_data.amount,
            payment_method=request.payment_method,
            status='completed',
            processed_at=datetime.now(),
            refunded_at=None
        )
        
        payment_code_data.status = 'used'
        
        db.add(new_payment_db)
        db.add(payment_code_data)
        db.commit()
        db.refresh(new_payment_db)
        db.refresh(payment_code_data)
        
        logger.info(f"Payment processed in DB: {new_payment_db.payment_id} for code {request.payment_code}")
        
        return PaymentResponse(**new_payment_db.__dict__)
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error processing payment in DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.get('/payments', response_model=PaymentListResponse, status_code=status.HTTP_200_OK)
async def get_payments(db: Annotated[Session, Depends(get_db)]):
    try:
        db_payments = db.query(PaymentDB).all()
        payment_list = [PaymentResponse(**payment.__dict__) for payment in db_payments]
        
        logger.info(f"Returning {len(payment_list)} payments from DB")
        
        return PaymentListResponse(
            payments=payment_list,
            total=len(payment_list),
            timestamp=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Error fetching payments from DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.get('/payment-codes/{payment_code}', response_model=PaymentCodeResponse)
async def get_payment_code(payment_code: str, db: Annotated[Session, Depends(get_db)]):
    try:
        payment_code_data = db.query(PaymentCodeDB).filter(PaymentCodeDB.payment_code == payment_code).first()
        
        if not payment_code_data:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment code not found"
            )
        
        return PaymentCodeResponse(**payment_code_data.__dict__)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching payment code from DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/payments/{payment_id}/refund', response_model=PaymentResponse)
async def refund_payment(payment_id: str, db: Annotated[Session, Depends(get_db)]):
    try:
        payment = db.query(PaymentDB).filter(PaymentDB.payment_id == payment_id).first()
        
        if not payment:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        
        if payment.status != 'completed':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment cannot be refunded as it's not completed"
            )
        
        payment.status = 'refunded'
        payment.refunded_at = datetime.now()
        
        db.add(payment)
        db.commit()
        db.refresh(payment)
        
        logger.info(f"Payment refunded in DB: {payment.payment_id}")
        
        return PaymentResponse(**payment.__dict__)
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error refunding payment in DB: {str(e)}")
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