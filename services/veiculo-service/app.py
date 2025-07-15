from fastapi import FastAPI, HTTPException, status, Query
from pydantic import BaseModel, Field
from typing import List, Optional
import os
import logging
from datetime import datetime
import uvicorn

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

app = FastAPI(
    title="Vehicle Service API",
    description="API para gerenciamento de veículos",
    version="1.0.0"
)

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
    created_at: str
    reserved_at: Optional[str] = None

class VehiclesListResponse(BaseModel):
    vehicles: List[VehicleResponse]
    total: int
    timestamp: str

class VehicleReservationResponse(BaseModel):
    message: str
    vehicle_id: int
    status: str

class HealthResponse(BaseModel):
    status: str
    service: str
    timestamp: str
    version: str

vehicles = [
    {
        "id": 1,
        "brand": "Toyota",
        "model": "Corolla",
        "year": 2022,
        "color": "Branco",
        "price": 85000.00,
        "status": "available",
        "created_at": datetime.now().isoformat()
    },
    {
        "id": 2,
        "brand": "Honda",
        "model": "Civic",
        "year": 2021,
        "color": "Preto",
        "price": 92000.00,
        "status": "available",
        "created_at": datetime.now().isoformat()
    }
]

@app.get('/health', response_model=HealthResponse, status_code=status.HTTP_200_OK)
async def health_check():
    return HealthResponse(
        status='healthy',
        service='vehicle-service',
        timestamp=datetime.now().isoformat(),
        version='1.0.0'
    )

@app.get('/vehicles', response_model=VehiclesListResponse, status_code=status.HTTP_200_OK)
async def get_vehicles(
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
        if status_filter:
            filtered_vehicles = [v for v in vehicles if v['status'] == status_filter]
        else:
            filtered_vehicles = vehicles.copy()
        
        if sort_by in ['price', 'year', 'brand', 'model']:
            reverse_order = sort_order.lower() == 'desc'
            filtered_vehicles = sorted(
                filtered_vehicles, 
                key=lambda x: x[sort_by], 
                reverse=reverse_order
            )
        
        vehicle_responses = [VehicleResponse(**vehicle) for vehicle in filtered_vehicles]
        
        logger.info(f"Returning {len(vehicle_responses)} vehicles with status '{status_filter}'")
        
        return VehiclesListResponse(
            vehicles=vehicle_responses,
            total=len(vehicle_responses),
            timestamp=datetime.now().isoformat()
        )
        
    except Exception as e:
        logger.error(f"Error fetching vehicles: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/vehicles', response_model=VehicleResponse, status_code=status.HTTP_201_CREATED)
async def create_vehicle(vehicle_data: VehicleCreate):
    try:
        new_vehicle = {
            'id': len(vehicles) + 1,
            'brand': vehicle_data.brand,
            'model': vehicle_data.model,
            'year': vehicle_data.year,
            'color': vehicle_data.color,
            'price': vehicle_data.price,
            'status': 'available',
            'created_at': datetime.now().isoformat()
        }
        
        vehicles.append(new_vehicle)
        logger.info(f"Created new vehicle: {new_vehicle['id']} - {new_vehicle['brand']} {new_vehicle['model']}")
        
        return VehicleResponse(**new_vehicle)
        
    except Exception as e:
        logger.error(f"Error creating vehicle: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.get('/vehicles/{vehicle_id}', response_model=VehicleResponse, status_code=status.HTTP_200_OK)
async def get_vehicle(vehicle_id: int):
    try:
        vehicle = next((v for v in vehicles if v['id'] == vehicle_id), None)
        
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
        
        logger.info(f"Returning vehicle details for ID: {vehicle_id}")
        return VehicleResponse(**vehicle)
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error fetching vehicle {vehicle_id}: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/vehicles/{vehicle_id}/reserve', response_model=VehicleReservationResponse)
async def reserve_vehicle(vehicle_id: int):
    try:
        vehicle = next((v for v in vehicles if v['id'] == vehicle_id), None)
        
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
            
        if vehicle['status'] != 'available':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vehicle not available for reservation"
            )
        
        vehicle['status'] = 'reserved'
        vehicle['reserved_at'] = datetime.now().isoformat()
        
        logger.info(f"Reserved vehicle: {vehicle_id} - {vehicle['brand']} {vehicle['model']}")
        
        return VehicleReservationResponse(
            message='Vehicle reserved successfully',
            vehicle_id=vehicle_id,
            status='reserved'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error reserving vehicle: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.post('/vehicles/{vehicle_id}/release', response_model=VehicleReservationResponse)
async def release_vehicle(vehicle_id: int):
    try:
        vehicle = next((v for v in vehicles if v['id'] == vehicle_id), None)
        
        if not vehicle:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
            
        if vehicle['status'] != 'reserved':
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Vehicle is not reserved"
            )
        
        vehicle['status'] = 'available'
        if 'reserved_at' in vehicle:
            del vehicle['reserved_at']
        
        logger.info(f"Released vehicle: {vehicle_id} - {vehicle['brand']} {vehicle['model']}")
        
        return VehicleReservationResponse(
            message='Vehicle released successfully',
            vehicle_id=vehicle_id,
            status='available'
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error releasing vehicle: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )

@app.delete('/vehicles/{vehicle_id}', status_code=status.HTTP_204_NO_CONTENT)
async def delete_vehicle(vehicle_id: int):
    try:
        vehicle_index = next((i for i, v in enumerate(vehicles) if v['id'] == vehicle_id), None)
        
        if vehicle_index is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="Vehicle not found"
            )
        
        deleted_vehicle = vehicles.pop(vehicle_index)
        logger.info(f"Deleted vehicle: {vehicle_id} - {deleted_vehicle['brand']} {deleted_vehicle['model']}")
        
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error deleting vehicle: {str(e)}")
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