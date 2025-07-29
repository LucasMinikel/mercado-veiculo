# ./tests/test_cliente_service.py
import pytest
import httpx
from conftest import CLIENTE_SERVICE_URL, DEFAULT_TIMEOUT, create_test_customer


class TestClienteService:
    """Testes específicos do serviço de clientes."""

    @pytest.mark.asyncio
    async def test_create_customer_success(self, sample_customer):
        """Testa criação bem-sucedida de cliente."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=sample_customer)
            assert response.status_code == 201

            customer = response.json()
            assert customer["name"] == sample_customer["name"]
            assert customer["email"] == sample_customer["email"]
            assert customer["credit_limit"] == sample_customer["credit_limit"]
            assert customer["available_credit"] == sample_customer["credit_limit"]
            assert customer["status"] == "active"
            assert "id" in customer
            assert "created_at" in customer

    @pytest.mark.asyncio
    async def test_get_customer_success(self, sample_customer):
        """Testa busca bem-sucedida de cliente."""
        # Criar cliente primeiro
        customer = await create_test_customer(sample_customer)
        customer_id = customer["id"]

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(f"{CLIENTE_SERVICE_URL}/customers/{customer_id}")
            assert response.status_code == 200

            found_customer = response.json()
            assert found_customer["id"] == customer_id
            assert found_customer["name"] == customer["name"]
            assert found_customer["email"] == customer["email"]

    @pytest.mark.asyncio
    async def test_get_nonexistent_customer(self):
        """Testa busca de cliente inexistente."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(f"{CLIENTE_SERVICE_URL}/customers/99999")
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_create_customer_duplicate_email(self, sample_customer):
        """Testa criação de cliente com email duplicado."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # Criar primeiro cliente
            response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=sample_customer)
            assert response.status_code == 201

            # Tentar criar segundo cliente com mesmo email
            response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=sample_customer)
            assert response.status_code == 409

    @pytest.mark.asyncio
    async def test_create_customer_invalid_data(self):
        """Testa criação de cliente com dados inválidos."""
        invalid_customer = {
            "name": "A",  # Nome muito curto
            "email": "invalid-email",  # Email inválido
            "phone": "123",  # Telefone muito curto
            "document": "123",  # Documento muito curto
            "credit_limit": -1000  # Crédito negativo
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=invalid_customer)
            assert response.status_code == 422

    @pytest.mark.asyncio
    async def test_list_customers(self, sample_customer):
        """Testa listagem de clientes."""
        # Criar cliente primeiro
        await create_test_customer(sample_customer)

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(f"{CLIENTE_SERVICE_URL}/customers")
            assert response.status_code == 200

            data = response.json()
            assert "customers" in data
            assert "total" in data
            assert "timestamp" in data
            assert data["total"] >= 1
            assert len(data["customers"]) >= 1

    @pytest.mark.asyncio
    async def test_health_check(self):
        """Testa health check do serviço."""
        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.get(f"{CLIENTE_SERVICE_URL}/health")
            assert response.status_code == 200

            health = response.json()
            assert health["status"] == "healthy"
            assert health["service"] == "customer-service"
            assert "timestamp" in health
            assert "version" in health
