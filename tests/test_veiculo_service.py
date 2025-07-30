# ./tests/test_veiculo_service.py
import pytest
import random
import httpx
from conftest import VEICULO_SERVICE_URL, DEFAULT_TIMEOUT, create_test_vehicle, generate_unique_vehicle_data


class TestVeiculoService:
    """Testes específicos do serviço de veículos."""

    @pytest.mark.asyncio
    async def test_create_and_get_vehicle(self, sample_vehicle):
        """Testa criação e busca de veículo."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # Criar veículo
            response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=sample_vehicle)
            assert response.status_code == 201

            created_vehicle = response.json()
            vehicle_id = created_vehicle["id"]

            # Verificar campos criados
            assert created_vehicle["brand"] == sample_vehicle["brand"]
            assert created_vehicle["model"] == sample_vehicle["model"]
            assert created_vehicle["price"] == sample_vehicle["price"]
            assert created_vehicle["license_plate"] == '*' * (len(
                # Mascarado
                sample_vehicle["license_plate"]) - 3) + sample_vehicle["license_plate"][-3:]
            # Não mascarado
            assert created_vehicle["chassi_number"] == sample_vehicle["chassi_number"]
            # Não mascarado
            assert created_vehicle["renavam"] == sample_vehicle["renavam"]
            assert created_vehicle["is_reserved"] is False
            assert created_vehicle["is_sold"] is False
            assert "id" in created_vehicle
            assert "created_at" in created_vehicle

            # Buscar veículo
            response = await client.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
            assert response.status_code == 200

            found_vehicle = response.json()
            assert found_vehicle["id"] == vehicle_id
            assert found_vehicle["brand"] == sample_vehicle["brand"]
            assert found_vehicle["model"] == sample_vehicle["model"]
            assert found_vehicle["price"] == sample_vehicle["price"]
            assert found_vehicle["chassi_number"] == sample_vehicle["chassi_number"]
            assert found_vehicle["renavam"] == sample_vehicle["renavam"]

    @pytest.mark.asyncio
    async def test_create_vehicle_duplicate_identifiers(self, sample_vehicle):
        """Testa criação de veículo com placa, chassi ou renavam duplicados."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # Criar o primeiro veículo
            response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=sample_vehicle)
            assert response.status_code == 201

            # Tentar criar outro veículo com os mesmos identificadores
            # Mantém os mesmos valores para license_plate, chassi_number, renavam
            duplicate_vehicle_data = sample_vehicle.copy()
            # Altera outro campo para ser diferente
            duplicate_vehicle_data["model"] = "Another Model"

            response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=duplicate_vehicle_data)
            assert response.status_code == 409
            assert "license plate, chassi number or renavam already exists" in response.json()[
                "detail"]

    @pytest.mark.asyncio
    async def test_update_vehicle_success(self, sample_vehicle):
        """Testa atualização bem-sucedida de veículo."""
        vehicle = await create_test_vehicle(sample_vehicle)
        vehicle_id = vehicle["id"]

        # Gerar novos dados válidos para chassi_number e renavam
        new_identifiers = generate_unique_vehicle_data()
        updated_data = {
            "color": "Azul Metálico",
            "price": 47500.0,
            # Usar um valor válido gerado
            "chassi_number": new_identifiers["chassi_number"],
            # Usar um valor válido gerado
            "renavam": new_identifiers["renavam"]
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.put(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}", json=updated_data)
            assert response.status_code == 200

            updated_vehicle = response.json()
            assert updated_vehicle["id"] == vehicle_id
            assert updated_vehicle["color"] == updated_data["color"]
            assert updated_vehicle["price"] == updated_data["price"]
            assert updated_vehicle["chassi_number"] == updated_data["chassi_number"]
            assert updated_vehicle["renavam"] == updated_data["renavam"]
            # Outros campos devem permanecer os mesmos
            assert updated_vehicle["brand"] == sample_vehicle["brand"]

    @pytest.mark.asyncio
    async def test_update_vehicle_duplicate_renavam(self, sample_vehicle):
        """Testa atualização de veículo com renavam duplicado."""
        vehicle1 = await create_test_vehicle(sample_vehicle)

        # Criar um segundo veículo com dados diferentes usando o helper
        vehicle2_data = generate_unique_vehicle_data(
            brand="Ford", model="Ka", year=2020, color="Vermelho", price=25000.0
        )
        vehicle2 = await create_test_vehicle(vehicle2_data)

        # Tentar atualizar o veículo2 com o renavam do veículo1
        update_data = {"renavam": sample_vehicle["renavam"]}

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.put(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle2['id']}", json=update_data)
            assert response.status_code == 409
            # Alteração aqui: Ajustar a string de asserção
            assert "License plate, chassi number or renavam already exists for another vehicle" in response.json()[
                "detail"]

    @pytest.mark.asyncio
    async def test_update_vehicle_reserved_or_sold(self, sample_vehicle):
        """Testa que não é possível atualizar veículo reservado ou vendido."""
        vehicle = await create_test_vehicle(sample_vehicle)
        vehicle_id = vehicle["id"]

        # Marcar como reservado
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # Testar a API de marcação como vendido (que já existe)
            response = await client.patch(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/mark_as_sold")
            assert response.status_code == 200
            sold_vehicle = response.json()
            assert sold_vehicle["is_sold"] is True

            # Tentar atualizar o veículo vendido
            # Simple update, should not cause 500
            update_data = {"color": "Cor Nova"}
            response = await client.put(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}", json=update_data)
            assert response.status_code == 400
            assert "Cannot edit vehicle that is reserved or sold" in response.json()[
                "detail"]

    @pytest.mark.asyncio
    async def test_list_vehicles_with_new_fields(self, sample_vehicle):
        """Testa listagem de veículos."""
        # Criar veículo primeiro
        await create_test_vehicle(sample_vehicle)

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(f"{VEICULO_SERVICE_URL}/vehicles")
            assert response.status_code == 200

            data = response.json()
            assert "vehicles" in data
            assert "total" in data
            assert "timestamp" in data
            assert data["total"] >= 1
            assert len(data["vehicles"]) >= 1

            # Verificar se os novos campos estão presentes na listagem
            first_vehicle = data["vehicles"][0]
            assert "chassi_number" in first_vehicle
            assert "renavam" in first_vehicle

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Testa health check do serviço."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(f"{VEICULO_SERVICE_URL}/health")
            assert response.status_code == 200

            health = response.json()
            assert health["status"] == "healthy"
            assert health["service"] == "vehicle-service"
            assert "timestamp" in health
            assert "version" in health
