import pytest
import httpx
import random
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
        await check_services_health()

        customer = await create_test_customer(sample_customer)
        vehicle = await create_test_vehicle(sample_vehicle)

        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "payment_type": "cash"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202

            purchase = response.json()
            transaction_id = purchase["transaction_id"]

            final_saga = await wait_for_saga_completion(client, transaction_id)

            assert final_saga["status"] == "COMPLETED"
            assert final_saga["current_step"] == "SAGA_COMPLETE"
            assert final_saga["customer_id"] == customer["id"]
            assert final_saga["vehicle_id"] == vehicle["id"]
            assert final_saga["amount"] == vehicle["price"]

    @pytest.mark.asyncio
    async def test_insufficient_credit_flow(self, sample_vehicle):
        """Testa o fluxo de compra com crédito insuficiente."""
        await check_services_health()

        rand_num = random.randint(100000, 999999)
        low_credit_customer = {
            "name": f"Cliente Sem Credito {rand_num}",
            "email": f"semcredito{rand_num}@email.com",
            "phone": f"11777{rand_num:06d}",
            "document": f"{rand_num:011d}",
            "initial_balance": 1000.0,
            "credit_limit": 10000.0
        }

        customer = await create_test_customer(low_credit_customer)
        vehicle = await create_test_vehicle(sample_vehicle)

        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "payment_type": "credit"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 400

            error_detail = response.json()
            assert "credit" in error_detail["detail"].lower()

            print(
                f"✅ Teste de crédito insuficiente passou - Validação funcionou: {error_detail['detail']}")

    @pytest.mark.asyncio
    async def test_insufficient_credit_saga_flow(self, sample_vehicle):
        """Testa o fluxo SAGA com crédito que falha durante a execução."""
        await check_services_health()

        rand_num = random.randint(200000, 299999)
        edge_case_customer = {
            "name": f"Cliente Edge Case {rand_num}",
            "email": f"edgecase{rand_num}@email.com",
            "phone": f"11888{rand_num:06d}",
            "document": f"{rand_num:011d}",
            "initial_balance": 1000.0,
            "credit_limit": 45000.0
        }

        customer = await create_test_customer(edge_case_customer)
        vehicle = await create_test_vehicle(sample_vehicle)

        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "payment_type": "credit"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)

            if response.status_code == 202:
                purchase = response.json()
                transaction_id = purchase["transaction_id"]
                final_saga = await wait_for_saga_completion(client, transaction_id)

                assert final_saga["status"] in [
                    "COMPLETED", "FAILED", "FAILED_COMPENSATED"]
                print(
                    f"✅ SAGA edge case concluída com status: {final_saga['status']}")
            else:
                assert response.status_code == 400
                print("✅ Validação inicial rejeitou corretamente")

    @pytest.mark.asyncio
    async def test_nonexistent_customer_flow(self, sample_vehicle):
        """Testa o fluxo com cliente inexistente."""
        await check_services_health()

        vehicle = await create_test_vehicle(sample_vehicle)

        purchase_data = {
            "customer_id": 99999,
            "vehicle_id": vehicle["id"],
            "payment_type": "cash"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_nonexistent_vehicle_flow(self, sample_customer):
        """Testa o fluxo com veículo inexistente."""
        await check_services_health()

        customer = await create_test_customer(sample_customer)

        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": 99999,
            "payment_type": "cash"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 404

    @pytest.mark.asyncio
    async def test_insufficient_balance_validation(self, sample_vehicle):
        """Testa validação de saldo insuficiente antes da SAGA."""
        await check_services_health()

        rand_num = random.randint(300000, 399999)
        customer_data = {
            "name": f"Cliente Pobre {rand_num}",
            "email": f"pobre{rand_num}@email.com",
            "phone": f"11777{rand_num:06d}",
            "document": f"{rand_num:011d}",
            "initial_balance": 1000.0,
            "credit_limit": 0.0
        }
        customer = await create_test_customer(customer_data)
        vehicle = await create_test_vehicle(sample_vehicle)

        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "payment_type": "cash"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 400

            error_detail = response.json()
            assert "balance" in error_detail["detail"].lower()
            print(
                f"✅ Validação de saldo insuficiente funcionou: {error_detail['detail']}")

    @pytest.mark.asyncio
    async def test_saga_state_persistence(self, sample_customer, sample_vehicle):
        """Testa se o estado da SAGA é persistido corretamente."""
        await check_services_health()

        customer = await create_test_customer(sample_customer)
        vehicle = await create_test_vehicle(sample_vehicle)

        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "payment_type": "cash"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202

            purchase = response.json()
            transaction_id = purchase["transaction_id"]

            response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
            assert response.status_code == 200
            initial_saga = response.json()
            assert initial_saga["status"] in [
                "STARTED", "IN_PROGRESS", "COMPLETED"]

            final_saga = await wait_for_saga_completion(client, transaction_id)

            assert final_saga["status"] == "COMPLETED"
            assert final_saga["transaction_id"] == transaction_id

            print(
                f"✅ Estado da SAGA persistido corretamente: {initial_saga['status']} -> {final_saga['status']}")
