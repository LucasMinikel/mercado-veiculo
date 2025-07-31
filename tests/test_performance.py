import pytest
import httpx
import asyncio
import time
import random
from conftest import (
    CLIENTE_SERVICE_URL,
    VEICULO_SERVICE_URL,
    PAGAMENTO_SERVICE_URL,
    ORQUESTRADOR_SERVICE_URL,
    DEFAULT_TIMEOUT,
    create_test_customer,
    create_test_vehicle
)


class TestPerformance:
    """Testes de performance do sistema."""

    @pytest.mark.asyncio
    async def test_concurrent_customer_creation(self):
        """Testa criação concorrente de clientes."""
        async def create_customer(index):
            base_num = random.randint(400000, 499999)
            customer_data = {
                "name": f"Cliente Concorrente {base_num}",
                "email": f"concorrente{base_num}@email.com",
                "phone": f"11999{base_num:06d}",
                "document": f"{base_num:011d}",
                "initial_balance": 50000.0,
                "credit_limit": 30000.0
            }

            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=customer_data)
                return response.status_code == 201

        start_time = time.time()
        tasks = [create_customer(i) for i in range(5)]
        results = await asyncio.gather(*tasks, return_exceptions=True)
        end_time = time.time()

        successful_creations = sum(1 for result in results if result is True)
        print(f"Criações bem-sucedidas: {successful_creations}/5")
        print(f"Tempo total: {end_time - start_time:.2f}s")

        assert successful_creations >= 4

    @pytest.mark.asyncio
    async def test_saga_response_time(self, sample_customer, sample_vehicle):
        """Testa tempo de resposta da SAGA."""
        customer = await create_test_customer(sample_customer)
        vehicle = await create_test_vehicle(sample_vehicle)

        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "payment_type": "cash"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            start_time = time.time()
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            end_time = time.time()

            assert response.status_code == 202

            response_time = end_time - start_time
            print(f"Tempo de resposta da SAGA: {response_time:.3f}s")

            assert response_time < 2.0

            purchase = response.json()
            assert "transaction_id" in purchase
            assert "vehicle_price" in purchase
            assert purchase["vehicle_price"] == vehicle["price"]

    @pytest.mark.asyncio
    async def test_health_check_response_time(self):
        """Testa tempo de resposta dos health checks."""
        services = {
            "cliente": f"{CLIENTE_SERVICE_URL}/health",
            "veiculo": f"{VEICULO_SERVICE_URL}/health",
            "pagamento": f"{PAGAMENTO_SERVICE_URL}/health",
            "orquestrador": f"{ORQUESTRADOR_SERVICE_URL}/health"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            for name, url in services.items():
                start_time = time.time()
                response = await client.get(url)
                end_time = time.time()

                assert response.status_code == 200

                response_time = end_time - start_time
                print(f"Health check {name}: {response_time:.3f}s")

                assert response_time < 1.0

    @pytest.mark.asyncio
    async def test_sequential_customer_creation(self):
        """Testa criação sequencial de clientes."""
        customers_created = 0
        total_time = 0

        for i in range(3):
            base_num = random.randint(500000, 599999) + i
            customer_data = {
                "name": f"Cliente Sequencial {base_num}",
                "email": f"sequencial{base_num}@email.com",
                "phone": f"11888{base_num:06d}",
                "document": f"{base_num:011d}",
                "initial_balance": 40000.0,
                "credit_limit": 25000.0
            }

            start_time = time.time()
            async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
                response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=customer_data)
            end_time = time.time()

            if response.status_code == 201:
                customers_created += 1
                total_time += (end_time - start_time)

        if customers_created > 0:
            avg_time = total_time / customers_created
            print(f"Clientes criados: {customers_created}/3")
            print(f"Tempo médio por criação: {avg_time:.3f}s")

            assert avg_time < 1.0

        assert customers_created >= 2
