# ./tests/test_integration.py
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
        # Verificar saúde dos serviços
        await check_services_health()

        # Criar cliente e veículo
        customer = await create_test_customer(sample_customer)
        vehicle = await create_test_vehicle(sample_vehicle)

        # Dados da compra - SEM amount
        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "payment_type": "cash"  # Usar o saldo em conta
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
            # Preço foi obtido automaticamente
            assert final_saga["amount"] == vehicle["price"]

    @pytest.mark.asyncio
    async def test_insufficient_credit_flow(self, sample_vehicle):
        """Testa o fluxo de compra com crédito insuficiente."""
        # Verificar saúde dos serviços
        await check_services_health()

        # Criar cliente com crédito baixo (menor que o preço do veículo) - dados únicos
        rand_num = random.randint(100000, 999999)
        low_credit_customer = {
            "name": f"Cliente Sem Credito {rand_num}",
            "email": f"semcredito{rand_num}@email.com",
            "phone": f"11777{rand_num:06d}",
            "document": f"{rand_num:011d}",
            "initial_balance": 1000.0,  # Saldo baixo
            # Crédito menor que o preço do veículo (45000)
            "credit_limit": 10000.0
        }

        customer = await create_test_customer(low_credit_customer)
        vehicle = await create_test_vehicle(sample_vehicle)

        # Tentar compra com crédito (que será insuficiente)
        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "payment_type": "credit"  # Usar limite de crédito (insuficiente)
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # Deve falhar na validação inicial (400 - Insufficient credit limit)
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 400

            error_detail = response.json()
            assert "credit" in error_detail["detail"].lower()

            print(
                f"✅ Teste de crédito insuficiente passou - Validação funcionou: {error_detail['detail']}")

    @pytest.mark.asyncio
    async def test_insufficient_credit_saga_flow(self, sample_vehicle):
        """Testa o fluxo SAGA com crédito que falha durante a execução."""
        # Verificar saúde dos serviços
        await check_services_health()

        # Criar cliente com crédito exatamente igual ao preço do veículo - dados únicos
        rand_num = random.randint(200000, 299999)
        edge_case_customer = {
            "name": f"Cliente Edge Case {rand_num}",
            "email": f"edgecase{rand_num}@email.com",
            "phone": f"11888{rand_num:06d}",
            "document": f"{rand_num:011d}",
            "initial_balance": 1000.0,
            "credit_limit": 45000.0  # Exatamente o preço do veículo
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
                # SAGA iniciou, aguardar conclusão
                purchase = response.json()
                transaction_id = purchase["transaction_id"]
                final_saga = await wait_for_saga_completion(client, transaction_id)

                # Pode completar ou falhar, ambos são válidos para este teste
                assert final_saga["status"] in [
                    "COMPLETED", "FAILED", "FAILED_COMPENSATED"]
                print(
                    f"✅ SAGA edge case concluída com status: {final_saga['status']}")
            else:
                # Falhou na validação inicial, também é válido
                assert response.status_code == 400
                print("✅ Validação inicial rejeitou corretamente")

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
            "payment_type": "cash"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # Deve falhar na validação inicial, antes mesmo de iniciar a SAGA
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 404  # Customer not found

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
            "payment_type": "cash"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # Deve falhar na validação inicial, antes mesmo de iniciar a SAGA
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 404  # Vehicle not found

    @pytest.mark.asyncio
    async def test_insufficient_balance_validation(self, sample_vehicle):
        """Testa validação de saldo insuficiente antes da SAGA."""
        # Verificar saúde dos serviços
        await check_services_health()

        # Criar cliente com saldo baixo - dados únicos
        rand_num = random.randint(300000, 399999)
        customer_data = {
            "name": f"Cliente Pobre {rand_num}",
            "email": f"pobre{rand_num}@email.com",
            "phone": f"11777{rand_num:06d}",
            "document": f"{rand_num:011d}",
            "initial_balance": 1000.0,  # Saldo baixo
            "credit_limit": 0.0  # Sem crédito
        }
        customer = await create_test_customer(customer_data)
        vehicle = await create_test_vehicle(sample_vehicle)

        purchase_data = {
            "customer_id": customer["id"],
            "vehicle_id": vehicle["id"],
            "payment_type": "cash"
        }

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            # Deve falhar na validação inicial
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 400  # Insufficient account balance

            error_detail = response.json()
            assert "balance" in error_detail["detail"].lower()
            print(
                f"✅ Validação de saldo insuficiente funcionou: {error_detail['detail']}")

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
            "payment_type": "cash"
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
            assert initial_saga["status"] in [
                "STARTED", "IN_PROGRESS", "COMPLETED"]

            # Aguardar conclusão
            final_saga = await wait_for_saga_completion(client, transaction_id)

            # Verificar que o estado foi atualizado
            assert final_saga["status"] == "COMPLETED"
            assert final_saga["transaction_id"] == transaction_id

            print(
                f"✅ Estado da SAGA persistido corretamente: {initial_saga['status']} -> {final_saga['status']}")
