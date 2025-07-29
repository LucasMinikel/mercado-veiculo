# ./tests/test_veiculo_service.py
import pytest
import random
from conftest import VEICULO_SERVICE_URL


class TestVeiculoService:
    """Testes específicos do serviço de veículos."""

    @pytest.mark.asyncio
    async def test_create_and_get_vehicle(self):
        """Testa criação e busca de veículo."""
        import httpx

        # Dados únicos
        rand_num = random.randint(1000, 9999)
        vehicle_data = {
            "brand": "Honda",
            "model": "Civic",
            "year": 2022,
            "color": "Preto",
            "price": 35000.0,
            "license_plate": f"XYZ{rand_num}"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Criar veículo
            response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=vehicle_data)
            assert response.status_code == 201

            created_vehicle = response.json()
            vehicle_id = created_vehicle["id"]
            print(f"✅ Veículo criado: {vehicle_id}")

            # Buscar veículo
            response = await client.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
            assert response.status_code == 200

            found_vehicle = response.json()
            assert found_vehicle["brand"] == vehicle_data["brand"]
            assert found_vehicle["model"] == vehicle_data["model"]
            assert found_vehicle["price"] == vehicle_data["price"]
            assert found_vehicle["is_reserved"] is False
            assert found_vehicle["is_sold"] is False
            print(
                f"✅ Veículo encontrado: {found_vehicle['brand']} {found_vehicle['model']}")
