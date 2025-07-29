# ./tests/test_integration.py
import pytest
import httpx
from conftest import (
    CLIENTE_SERVICE_URL,
    ORQUESTRADOR_SERVICE_URL,
    DEFAULT_TIMEOUT,
    wait_for_saga_completion,
    create_test_customer,
    create_test_vehicle,
    check_services_health
)


class TestIntegration:
    """Testes de integração completos do sistema."""

    @pytest.mark.asyncio
    async def test_successful_purchase_flow(self, sample_customer, sample_vehicle):
        """Testa o fluxo completo de compra bem-sucedida."""
        # Verificar saúde dos serviços
        await check_services_health()

        # Criar cliente e veículo
        customer = await create_test_customer(sample_customer)
        vehicle = await create_test_vehicle(sample_vehicle)

        # Dados da compra
        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "amount": vehicle["price"]
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # Iniciar compra
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202

            purchase = response.json()
            transaction_id = purchase["transaction_id"]

            # Aguardar conclusão
            final_saga = await wait_for_saga_completion(client, transaction_id)

            # Verificar resultado
            assert final_saga["status"] == "COMPLETED"
            assert final_saga["current_step"] == "SAGA_COMPLETE"
            assert final_saga["customer_id"] == customer["id"]
            assert final_saga["vehicle_id"] == vehicle["id"]
            assert final_saga["amount"] == vehicle["price"]

    @pytest.mark.asyncio
    async def test_insufficient_credit_flow(self, low_credit_customer, sample_vehicle):
        """Testa o fluxo de compra com crédito insuficiente."""
        # Verificar saúde dos serviços
        await check_services_health()

        # Criar cliente com crédito baixo e veículo
        customer = await create_test_customer(low_credit_customer)
        vehicle = await create_test_vehicle(sample_vehicle)

        # Tentar compra com valor maior que o crédito
        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "amount": vehicle["price"]  # Maior que o crédito do cliente
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202

            purchase = response.json()
            transaction_id = purchase["transaction_id"]

            # Aguardar conclusão
            final_saga = await wait_for_saga_completion(client, transaction_id)

            # Verificar falha - O importante é que falhou na reserva de crédito
            assert final_saga["status"] == "FAILED"
            assert final_saga["current_step"] == "CREDIT_RESERVATION_FAILED"

            # Verificar que os dados da transação estão corretos
            assert final_saga["customer_id"] == customer["id"]
            assert final_saga["vehicle_id"] == vehicle["id"]
            assert final_saga["amount"] == vehicle["price"]

            print(
                f"✅ Teste de crédito insuficiente passou - SAGA falhou corretamente no step: {final_saga['current_step']}")

    @pytest.mark.asyncio
    async def test_nonexistent_customer_flow(self, sample_vehicle):
        """Testa o fluxo com cliente inexistente."""
        # Verificar saúde dos serviços
        await check_services_health()

        # Criar apenas veículo
        vehicle = await create_test_vehicle(sample_vehicle)

        purchase_data = {
            "customer_id": 99999,  # ID inexistente
            "vehicle_id": vehicle["id"],
            "amount": vehicle["price"]
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202

            purchase = response.json()
            transaction_id = purchase["transaction_id"]

            # Aguardar conclusão
            final_saga = await wait_for_saga_completion(client, transaction_id)

            # Verificar falha - O importante é que falhou
            assert final_saga["status"] == "FAILED"

            # Verificar que os dados da transação estão corretos
            assert final_saga["customer_id"] == 99999
            assert final_saga["vehicle_id"] == vehicle["id"]
            assert final_saga["amount"] == vehicle["price"]

            print(
                f"✅ Teste de cliente inexistente passou - SAGA falhou corretamente no step: {final_saga['current_step']}")

    @pytest.mark.asyncio
    async def test_nonexistent_vehicle_flow(self, sample_customer):
        """Testa o fluxo com veículo inexistente."""
        # Verificar saúde dos serviços
        await check_services_health()

        # Criar apenas cliente
        customer = await create_test_customer(sample_customer)

        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": 99999,  # ID inexistente
            "amount": 50000.0
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202

            purchase = response.json()
            transaction_id = purchase["transaction_id"]

            # Aguardar conclusão
            final_saga = await wait_for_saga_completion(client, transaction_id, timeout=30)

            # Verificar falha - O importante é que falhou ou foi compensado
            assert final_saga["status"] in [
                "FAILED", "FAILED_COMPENSATED", "COMPENSATING"]

            # Verificar que os dados da transação estão corretos
            assert final_saga["customer_id"] == customer["id"]
            assert final_saga["vehicle_id"] == 99999
            assert final_saga["amount"] == 50000.0

            print(
                f"✅ Teste de veículo inexistente passou - SAGA falhou/compensou corretamente no step: {final_saga['current_step']}")

    @pytest.mark.asyncio
    async def test_saga_state_persistence(self, sample_customer, sample_vehicle):
        """Testa se o estado da SAGA é persistido corretamente."""
        # Verificar saúde dos serviços
        await check_services_health()

        # Criar cliente e veículo
        customer = await create_test_customer(sample_customer)
        vehicle = await create_test_vehicle(sample_vehicle)

        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "amount": vehicle["price"]
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # Iniciar compra
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202

            purchase = response.json()
            transaction_id = purchase["transaction_id"]

            # Verificar estado inicial
            response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
            assert response.status_code == 200
            initial_saga = response.json()
            assert initial_saga["status"] in ["STARTED", "COMPLETED"]

            # Aguardar conclusão
            final_saga = await wait_for_saga_completion(client, transaction_id)

            # Verificar que o estado foi atualizado
            assert final_saga["status"] == "COMPLETED"
            assert final_saga["transaction_id"] == transaction_id

            print(
                f"✅ Estado da SAGA persistido corretamente: {initial_saga['status']} -> {final_saga['status']}")
