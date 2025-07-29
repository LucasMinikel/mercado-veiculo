from pydantic import BaseModel, Field
from typing import Optional, List
from datetime import datetime


class ReserveCreditCommand(BaseModel):
    transaction_id: str
    customer_id: int
    amount: float


class ReleaseCreditCommand(BaseModel):
    transaction_id: str
    customer_id: int
    amount: float


class ReserveVehicleCommand(BaseModel):
    transaction_id: str
    vehicle_id: int


class ReleaseVehicleCommand(BaseModel):
    transaction_id: str
    vehicle_id: int


class GeneratePaymentCodeCommand(BaseModel):
    transaction_id: str
    customer_id: int
    vehicle_id: int
    amount: float


class ProcessPaymentCommand(BaseModel):
    transaction_id: str
    payment_code: str
    payment_method: str


class RefundPaymentCommand(BaseModel):
    transaction_id: str
    payment_id: str


class CreditReservedEvent(BaseModel):
    transaction_id: str
    customer_id: int
    amount: float
    available_credit: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CreditReservationFailedEvent(BaseModel):
    transaction_id: str
    customer_id: int
    amount: float
    reason: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class CreditReleasedEvent(BaseModel):
    transaction_id: str
    customer_id: int
    amount: float
    available_credit: float
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VehicleReservedEvent(BaseModel):
    transaction_id: str
    vehicle_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VehicleReservationFailedEvent(BaseModel):
    transaction_id: str
    vehicle_id: int
    reason: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class VehicleReleasedEvent(BaseModel):
    transaction_id: str
    vehicle_id: int
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaymentCodeGeneratedEvent(BaseModel):
    transaction_id: str
    payment_code: str
    customer_id: int
    vehicle_id: int
    amount: float
    expires_at: datetime
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaymentCodeGenerationFailedEvent(BaseModel):
    transaction_id: str
    customer_id: int
    vehicle_id: int
    amount: float
    reason: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaymentProcessedEvent(BaseModel):
    transaction_id: str
    payment_id: str
    payment_code: str
    customer_id: int
    vehicle_id: int
    amount: float
    payment_method: str
    status: str = "completed"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaymentFailedEvent(BaseModel):
    transaction_id: str
    payment_code: str
    customer_id: int
    vehicle_id: int
    amount: float
    reason: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaymentRefundedEvent(BaseModel):
    transaction_id: str
    payment_id: str
    status: str = "refunded"
    timestamp: datetime = Field(default_factory=datetime.utcnow)


class PaymentRefundFailedEvent(BaseModel):
    transaction_id: str
    payment_id: str
    reason: str
    timestamp: datetime = Field(default_factory=datetime.utcnow)
