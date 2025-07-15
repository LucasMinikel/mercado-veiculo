from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import logging
from datetime import datetime
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Customer Service API",
    description="API para gerenciamento de clientes e crédito",
    version="1.0.0"
)

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
    created_at: str

class CustomersListResponse(BaseModel):
    customers: List[CustomerResponse]
    total: int
    timestamp: str

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
    timestamp: str
    version: str

customers = [
    {
        "id": 1,
        "name": "João Silva",
        "email": "joao@email.com",
        "phone": "11999999999",
        "document": "12345678901",
        "credit_limit": 150000.00,
        "available_credit": 150000.00,
        "status": "active",
        "created_at": datetime.now().isoformat()
    },
    {
        "id": 2,
        "name": "Maria Santos",
        "email": "maria@email.com",
        "phone": "11888888888",
        "document": "98765432100",
        "credit_limit": 200000.00,
        "available_credit": 200000.00,
        "status": "active",
        "created_at": datetime.now().isoformat()
    }
]

@app.get('/health', response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check():
    return HealthResponse(
        status='healthy',
        service='customer-service',
        timestamp=datetime.now().isoformat(),
        version='1.0.0'
    )

@app.get('/customers', response_model=CustomersListResponse, status_code=status.HTTP_200_OK)
async def get_customers():
    try:
        safe_customers = []
        for customer in customers:
            safe_customer = customer.copy()
            safe_customer['document'] = '*' * 7 + customer['document'][-4:]
            safe_customers.append(CustomerResponse(**safe_customer))
        
        logger.info(f"Returning {len(safe_customers)} customers")
        
        return CustomersListResponse(
            customers=safe_customers,
            total=len(safe_customers),
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error fetching customers: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/customers', response_model=CustomerResponse, status_code=status.HTTP_201_CREATED)
async def create_customer(customer_data: CustomerCreate):
    try:
        existing_customer = next((c for c in customers if c['document'] == customer_data.document), None)
        if existing_customer:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="Customer already exists"
            )
        
        new_customer = {
            'id': len(customers) + 1,
            'name': customer_data.name,
            'email': customer_data.email,
            'phone': customer_data.phone,
            'document': customer_data.document,
            'credit_limit': customer_data.credit_limit,
            'available_credit': customer_data.credit_limit,
            'status': 'active',
            'created_at': datetime.now().isoformat()
        }
        
        customers.append(new_customer)
        logger.info(f"Created new customer: {new_customer['id']}")
        
        safe_customer = new_customer.copy()
        safe_customer['document'] = '*' * 7 + new_customer['document'][-4:]
        
        return CustomerResponse(**safe_customer)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error creating customer: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/customers/{customer_id}/credit/reserve', response_model=CreditOperationResponse)
async def reserve_credit(customer_id: int, credit_data: CreditOperation):
    try:
        customer = next((c for c in customers if c['id'] == customer_id), None)
        
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )
            
        if customer['status'] != 'active':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Customer not active"
            )
        
        if customer['available_credit'] < credit_data.amount:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Insufficient credit"
            )
        
        customer['available_credit'] -= credit_data.amount
        
        logger.info(f"Reserved credit for customer {customer_id}: ${credit_data.amount}")
        
        return CreditOperationResponse(
            message='Credit reserved successfully',
            customer_id=customer_id,
            amount=credit_data.amount,
            available_credit=customer['available_credit']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reserving credit: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/customers/{customer_id}/credit/release', response_model=CreditOperationResponse)
async def release_credit(customer_id: int, credit_data: CreditOperation):
    try:
        customer = next((c for c in customers if c['id'] == customer_id), None)
        
        if not customer:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Customer not found"
            )
        
        customer['available_credit'] += credit_data.amount
        
        logger.info(f"Released credit for customer {customer_id}: ${credit_data.amount}")
        
        return CreditOperationResponse(
            message='Credit released successfully',
            customer_id=customer_id,
            amount=credit_data.amount,
            available_credit=customer['available_credit']
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing credit: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

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