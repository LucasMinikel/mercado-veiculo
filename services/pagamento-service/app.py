# services/pagamento-service/app.py
from fastapi import FastAPI, HTTPException, status
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import logging
from datetime import datetime, timedelta
import uvicorn
import uuid
import random

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Payment Service API",
    description="API para gerenciamento de pagamentos e códigos de pagamento",
    version="1.0.0"
)

class PaymentCodeRequest(BaseModel):
    customer_id: int = Field(..., description="ID do cliente")
    vehicle_id: int = Field(..., description="ID do veículo")
    amount: float = Field(..., gt=0, description="Valor do pagamento")

class PaymentCodeResponse(BaseModel):
    payment_code: str
    customer_id: int
    vehicle_id: int
    amount: float
    expires_at: str
    status: str
    created_at: str

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
    processed_at: str
    refunded_at: Optional[str] = None  # Adicionado campo opcional

class PaymentListResponse(BaseModel):
    payments: List[PaymentResponse]
    total: int
    timestamp: str

class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str
    version: str

# Armazenamento em memória (será substituído por banco de dados)
payment_codes = {}
payments = {}

@app.get('/health', response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check():
    return HealthResponse(
        status='healthy',
        service='payment-service',
        timestamp=datetime.now().isoformat(),
        version='1.0.0'
    )

@app.post('/payment-codes', response_model=PaymentCodeResponse, status_code=status.HTTP_201_CREATED)
async def generate_payment_code(request: PaymentCodeRequest):
    try:
        # Gerar código único de pagamento
        payment_code = f"PAY-{uuid.uuid4().hex[:8].upper()}"
        expires_at = datetime.now() + timedelta(minutes=30)  # Expira em 30 minutos
        
        payment_code_data = {
            'payment_code': payment_code,
            'customer_id': request.customer_id,
            'vehicle_id': request.vehicle_id,
            'amount': request.amount,
            'expires_at': expires_at.isoformat(),
            'status': 'pending',
            'created_at': datetime.now().isoformat()
        }
        
        payment_codes[payment_code] = payment_code_data
        
        logger.info(f"Generated payment code: {payment_code} for customer {request.customer_id}")
        
        return PaymentCodeResponse(**payment_code_data)
        
    except Exception as e:
        logger.error(f"Error generating payment code: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/payments', response_model=PaymentResponse, status_code=status.HTTP_201_CREATED)
async def process_payment(request: PaymentRequest):
    try:
        # Verificar se o código de pagamento existe
        if request.payment_code not in payment_codes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment code not found"
            )
        
        payment_code_data = payment_codes[request.payment_code]
        
        # Verificar se o código não expirou
        expires_at = datetime.fromisoformat(payment_code_data['expires_at'])
        if datetime.now() > expires_at:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment code expired"
            )
        
        # Verificar se já foi processado
        if payment_code_data['status'] != 'pending':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment code already processed"
            )
        
        # Simular processamento do pagamento (90% de sucesso)
        payment_success = random.random() > 0.1
        
        if not payment_success:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment processing failed"
            )
        
        # Criar registro de pagamento
        payment_id = f"TXN-{uuid.uuid4().hex[:12].upper()}"
        payment_data = {
            'payment_id': payment_id,
            'payment_code': request.payment_code,
            'customer_id': payment_code_data['customer_id'],
            'vehicle_id': payment_code_data['vehicle_id'],
            'amount': payment_code_data['amount'],
            'payment_method': request.payment_method,
            'status': 'completed',
            'processed_at': datetime.now().isoformat(),
            'refunded_at': None  # Inicialmente None
        }
        
        payments[payment_id] = payment_data
        payment_codes[request.payment_code]['status'] = 'used'
        
        logger.info(f"Payment processed: {payment_id} for code {request.payment_code}")
        
        return PaymentResponse(**payment_data)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error processing payment: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.get('/payments', response_model=PaymentListResponse, status_code=status.HTTP_200_OK)
async def get_payments():
    try:
        payment_list = [PaymentResponse(**payment) for payment in payments.values()]
        
        logger.info(f"Returning {len(payment_list)} payments")
        
        return PaymentListResponse(
            payments=payment_list,
            total=len(payment_list),
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error fetching payments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.get('/payment-codes/{payment_code}', response_model=PaymentCodeResponse)
async def get_payment_code(payment_code: str):
    try:
        if payment_code not in payment_codes:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment code not found"
            )
        
        return PaymentCodeResponse(**payment_codes[payment_code])
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching payment code: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/payments/{payment_id}/refund', response_model=PaymentResponse)
async def refund_payment(payment_id: str):
    """Endpoint para estorno - usado em compensações do Saga"""
    try:
        if payment_id not in payments:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Payment not found"
            )
        
        payment = payments[payment_id]
        
        if payment['status'] != 'completed':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Payment cannot be refunded"
            )
        
        # Atualiza o status e adiciona timestamp do estorno
        payment['status'] = 'refunded'
        payment['refunded_at'] = datetime.now().isoformat()
        
        logger.info(f"Payment refunded: {payment_id}")
        
        return PaymentResponse(**payment)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error refunding payment: {str(e)}")
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