from fastapi import FastAPI, HTTPException, status, Depends
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

class CustomerDB(Base):
    __tablename__ = "customers"

    id = Column(Integer, primary_key=True, index=True)
    name = Column(String, index=True)
    email = Column(String, unique=True, index=True)
    phone = Column(String)
    document = Column(String, unique=True, index=True)
    credit_limit = Column(Float)
    available_credit = Column(Float)
    status = Column(String)
    created_at = Column(DateTime, default=datetime.now)

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

class CustomerCreate(BaseModel):
    name: str = Field(..., min_length=1, description="Nome do cliente")
    email: str = Field(..., description="Email do cliente")
    phone: str = Field(..., description="Telefone do cliente")
    document: str = Field(..., min_length=11, max_length=11, description="CPF do cliente")
    credit_limit: Optional[float] = Field(100000.00, ge=0, description="Limite de crédito")

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

class CustomersListResponse(BaseModel):
    customers: List[CustomerResponse]
    total: int
    timestamp: datetime

class CreditOperation(BaseModel):
    amount: float = Field(..., gt=0, description="Valor da operação de crédito")

class CreditOperationResponse(BaseModel):
    message: str
    customer_id: int
    amount: float
    available_credit: float

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

@app.get('/customers', response_model=CustomersListResponse, status_code=status.HTTP_200_OK)
async def get_customers(db: Annotated[Session, Depends(get_db)]):
    try:
        db_customers = db.query(CustomerDB).all()
        
        safe_customers = []
        for customer in db_customers:
            customer_dict = customer.__dict__.copy()
            safe_customer = CustomerResponse(
                id=customer_dict['id'],
                name=customer_dict['name'],
                email=customer_dict['email'],
                phone=customer_dict['phone'],
                document='*' * 7 + customer_dict['document'][-4:],
                credit_limit=customer_dict['credit_limit'],
                available_credit=customer_dict['available_credit'],
                status=customer_dict['status'],
                created_at=customer_dict['created_at']
            )
            safe_customers.append(safe_customer)
        
        logger.info(f"Returning {len(safe_customers)} customers from DB")
        
        return CustomersListResponse(
            customers=safe_customers,
            total=len(safe_customers),
            timestamp=datetime.now()
        )
        
    except Exception as e:
        logger.error(f"Error fetching customers from DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/customers', response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(customer_data: CustomerCreate, db: Annotated[Session, Depends(get_db)]):
    try:
        existing_customer = db.query(CustomerDB).filter(
            (CustomerDB.document == customer_data.document) | 
            (CustomerDB.email == customer_data.email)
        ).first()
        
        if existing_customer:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Customer with this document or email already exists"
            )
        
        new_customer_db = CustomerDB(
            name=customer_data.name,
            email=customer_data.email,
            phone=customer_data.phone,
            document=customer_data.document,
            credit_limit=customer_data.credit_limit,
            available_credit=customer_data.credit_limit,
            status='active',
            created_at=datetime.now()
        )
        
        db.add(new_customer_db)
        db.commit()
        db.refresh(new_customer_db)
        
        logger.info(f"Created new customer in DB: {new_customer_db.id}")
        
        safe_customer = new_customer_db.__dict__.copy()
        safe_customer['document'] = '*' * 7 + new_customer_db.document[-4:]
        
        return CustomerResponse(**safe_customer)
        
    except HTTPException:
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error creating customer in DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/customers/{customer_id}/credit/reserve', response_model=CreditOperationResponse)
async def reserve_credit(customer_id: int, credit_data: CreditOperation, db: Annotated[Session, Depends(get_db)]):
    try:
        customer = db.query(CustomerDB).filter(CustomerDB.id == customer_id).first()
        
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )
            
        if customer.status != 'active':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer not active"
            )
        
        if customer.available_credit < credit_data.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient credit"
            )
        
        customer.available_credit -= credit_data.amount
        
        db.add(customer)
        db.commit()
        db.refresh(customer)
        
        logger.info(f"Reserved credit for customer {customer_id} in DB: ${credit_data.amount}")
        
        return CreditOperationResponse(
            message='Credit reserved successfully',
            customer_id=customer_id,
            amount=credit_data.amount,
            available_credit=customer.available_credit
        )
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error reserving credit in DB: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/customers/{customer_id}/credit/release', response_model=CreditOperationResponse)
async def release_credit(customer_id: int, credit_data: CreditOperation, db: Annotated[Session, Depends(get_db)]):
    try:
        customer = db.query(CustomerDB).filter(CustomerDB.id == customer_id).first()
        
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )
        
        customer.available_credit += credit_data.amount
        
        db.add(customer)
        db.commit()
        db.refresh(customer)
        
        logger.info(f"Released credit for customer {customer_id} in DB: ${credit_data.amount}")
        
        return CreditOperationResponse(
            message='Credit released successfully',
            customer_id=customer_id,
            amount=credit_data.amount,
            available_credit=customer.available_credit
        )
        
    except HTTPException:
        db.rollback()
        raise
    except Exception as e:
        db.rollback()
        logger.error(f"Error releasing credit in DB: {str(e)}")
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