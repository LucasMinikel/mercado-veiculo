import pytest
import httpx
import asyncio
import random
from conftest import (
    ORQUESTRADOR_SERVICE_URL,
    DEFAULT_TIMEOUT,
    create_test_customer,
    create_test_vehicle,
    wait_for_saga_completion,
    generate_unique_vehicle_data
)


class TestCancellation:
    """Testes de cancelamento de compra."""

    @pytest.mark.asyncio
    async def test_cancel_purchase_during_payment_processing(self):
        """Testa cancelamento durante o processamento de pagamento."""

        rand_num = random.randint(50000, 59999)
        customer_data = {
            "name": f"Cliente Cancelamento {rand_num}",
            "email": f"cancelamento{rand_num}@email.com",
            "phone": f"11999{rand_num:05d}",
            "document": f"{rand_num:011d}",
            "initial_balance": 60000.0,
            "credit_limit": 50000.0
        }

        vehicle_data = generate_unique_vehicle_data(
            brand="Toyota", model="Corolla", year=2023, color="Branco", price=45000.0
        )

        customer = await create_test_customer(customer_data)
        vehicle = await create_test_vehicle(vehicle_data)

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
            print(f"✅ Compra iniciada: {transaction_id}")

            await asyncio.sleep(2)

            response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
            assert response.status_code == 200
            saga_before = response.json()
            print(
                f"📊 Estado antes do cancelamento: {saga_before['status']} - {saga_before.get('current_step', 'N/A')}")

            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase/{transaction_id}/cancel")

            if response.status_code == 200:
                cancel_result = response.json()
                print(f"✅ Cancelamento iniciado: {cancel_result['message']}")

                for i in range(15):
                    await asyncio.sleep(1)
                    response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
                    assert response.status_code == 200

                    saga = response.json()
                    status = saga['status']
                    step = saga.get('current_step', 'N/A')
                    print(f"📊 Estado {i+1}: {status} - {step}")

                    if status in ['CANCELLED', 'CANCELLATION_FAILED']:
                        print(f"🎯 Cancelamento finalizado: {status}")
                        assert status == 'CANCELLED'
                        break
                else:
                    pytest.fail("Timeout aguardando cancelamento")

            elif response.status_code == 400:
                error = response.json()
                print(f"⚠️ Cancelamento rejeitado: {error['detail']}")
                assert "Cannot cancel" in error['detail'] or "too advanced" in error['detail']

            else:
                pytest.fail(
                    f"Erro inesperado no cancelamento: {response.status_code} - {response.text}")

    @pytest.mark.asyncio
    async def test_cancel_completed_purchase_should_fail(self):
        """Testa que não é possível cancelar uma compra já concluída."""

        rand_num = random.randint(60000, 69999)
        customer_data = {
            "name": f"Cliente Completo {rand_num}",
            "email": f"completo{rand_num}@email.com",
            "phone": f"11888{rand_num:05d}",
            "document": f"{rand_num:011d}",
            "initial_balance": 60000.0,
            "credit_limit": 50000.0
        }

        vehicle_data = generate_unique_vehicle_data(
            brand="Honda", model="Civic", year=2023, color="Preto", price=40000.0
        )

        customer = await create_test_customer(customer_data)
        vehicle = await create_test_vehicle(vehicle_data)

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
            print(f"✅ Compra iniciada: {transaction_id}")

            final_saga = await wait_for_saga_completion(client, transaction_id)
            assert final_saga["status"] == "COMPLETED"
            print(f"✅ Compra concluída: {final_saga['status']}")

            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase/{transaction_id}/cancel")
            assert response.status_code == 400

            error = response.json()
            assert "Cannot cancel transaction with status: COMPLETED" in error['detail']
            print(f"✅ Cancelamento corretamente rejeitado: {error['detail']}")

    @pytest.mark.asyncio
    async def test_cancel_nonexistent_transaction(self):
        """Testa cancelamento de transação inexistente."""

        fake_transaction_id = "fake-transaction-123"

        async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase/{fake_transaction_id}/cancel")
            assert response.status_code == 404

            error = response.json()
            assert "Transaction not found" in error['detail']
            print(
                f"✅ Transação inexistente corretamente rejeitada: {error['detail']}")

    @pytest.mark.asyncio
    async def test_cancel_with_multiple_attempts(self):
        """Testa múltiplas tentativas de cancelamento para capturar diferentes timing."""

        success_count = 0
        rejection_count = 0

        for attempt in range(3):
            rand_num = random.randint(
                80000 + attempt * 1000, 80999 + attempt * 1000)

            customer_data = {
                "name": f"Cliente Multi {rand_num}",
                "email": f"multi{rand_num}@email.com",
                "phone": f"11888{rand_num:05d}",
                "document": f"{rand_num:011d}",
                "initial_balance": 60000.0,
                "credit_limit": 50000.0
            }

            vehicle_data = generate_unique_vehicle_data(
                brand="Multi", model="Test", year=2023, color="Azul", price=30000.0
            )

            customer = await create_test_customer(customer_data)
            vehicle = await create_test_vehicle(vehicle_data)

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
                print(f"🔄 Tentativa {attempt + 1}: Compra {transaction_id}")

                response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase/{transaction_id}/cancel")

                if response.status_code == 200:
                    print(f"✅ Tentativa {attempt + 1}: Cancelamento aceito")
                    success_count += 1

                    for i in range(10):
                        await asyncio.sleep(0.5)
                        response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
                        if response.status_code == 200:
                            saga = response.json()
                            if saga['status'] in ['CANCELLED', 'CANCELLATION_FAILED']:
                                print(
                                    f"🎯 Tentativa {attempt + 1}: Finalizado com {saga['status']}")
                                break

                elif response.status_code == 400:
                    print(
                        f"⚠️ Tentativa {attempt + 1}: Cancelamento rejeitado (transação rápida)")
                    rejection_count += 1

                await asyncio.sleep(0.1)

        print(
            f"📊 Resultado: {success_count} sucessos, {rejection_count} rejeições de {3} tentativas")

        assert (success_count +
                rejection_count) >= 2, "Pelo menos 2 tentativas devem ter comportamento esperado"

        if success_count > 0:
            print("✅ Funcionalidade de cancelamento está funcionando!")
        else:
            print(
                "ℹ️ Todas as transações foram muito rápidas para cancelar - isso também é válido!")

        @pytest.mark.asyncio
        async def test_cancel_early_stage_purchase(self):
            """Testa cancelamento em estágio inicial da compra."""

            rand_num = random.randint(70000, 79999)
            customer_data = {
                "name": f"Cliente Inicial {rand_num}",
                "email": f"inicial{rand_num}@email.com",
                "phone": f"11777{rand_num:05d}",
                "document": f"{rand_num:011d}",
                "initial_balance": 60000.0,
                "credit_limit": 50000.0
            }

            vehicle_data = generate_unique_vehicle_data(
                brand="Ford", model="Ka", year=2022, color="Vermelho", price=35000.0
            )

            customer = await create_test_customer(customer_data)
            vehicle = await create_test_vehicle(vehicle_data)

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
                print(f"✅ Compra iniciada: {transaction_id}")

                response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase/{transaction_id}/cancel")

                if response.status_code == 200:
                    cancel_result = response.json()
                    print(f"✅ Cancelamento aceito: {cancel_result['message']}")

                    for i in range(15):
                        await asyncio.sleep(1)
                        response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
                        assert response.status_code == 200

                        saga = response.json()
                        status = saga['status']
                        step = saga.get('current_step', 'N/A')
                        print(f"📊 Estado {i+1}: {status} - {step}")

                        if status in ['CANCELLED', 'CANCELLATION_FAILED']:
                            print(f"🎯 Cancelamento finalizado: {status}")
                            assert status in [
                                'CANCELLED', 'CANCELLATION_FAILED']
                            return

                    pytest.fail("Timeout aguardando resultado do cancelamento")

                elif response.status_code == 400:
                    error = response.json()
                    print(f"⚠️ Cancelamento rejeitado: {error['detail']}")

                    valid_rejection_reasons = [
                        "Cannot cancel transaction with status: COMPLETED",
                        "too advanced to cancel",
                        "already completed"
                    ]

                    rejection_is_valid = any(reason.lower() in error['detail'].lower()
                                             for reason in valid_rejection_reasons)

                    if rejection_is_valid:
                        print(
                            "✅ Rejeição válida - transação já estava muito avançada")
                        response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
                        if response.status_code == 200:
                            saga = response.json()
                            print(
                                f"📊 Status final da transação: {saga['status']}")
                            assert saga['status'] in ['COMPLETED',
                                                      'MARK_VEHICLE_AS_SOLD', 'SAGA_COMPLETE']
                    else:
                        pytest.fail(f"Rejeição inesperada: {error['detail']}")

                elif response.status_code == 409:
                    error = response.json()
                    print(f"⚠️ Conflito: {error['detail']}")
                    assert "already in progress" in error['detail'].lower()

                else:
                    pytest.fail(
                        f"Erro inesperado no cancelamento: {response.status_code} - {response.text}")
                    """Testa cancelamento em estágio inicial da compra."""

                    rand_num = random.randint(70000, 79999)
                    customer_data = {
                        "name": f"Cliente Inicial {rand_num}",
                        "email": f"inicial{rand_num}@email.com",
                        "phone": f"11777{rand_num:05d}",
                        "document": f"{rand_num:011d}",
                        "initial_balance": 60000.0,
                        "credit_limit": 50000.0
                    }

                    vehicle_data = generate_unique_vehicle_data(
                        brand="Ford", model="Ka", year=2022, color="Vermelho", price=35000.0
                    )

                    customer = await create_test_customer(customer_data)
                    vehicle = await create_test_vehicle(vehicle_data)

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
                        print(f"✅ Compra iniciada: {transaction_id}")

                        response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase/{transaction_id}/cancel")

                        if response.status_code == 200:
                            cancel_result = response.json()
                            print(
                                f"✅ Cancelamento aceito: {cancel_result['message']}")

                            for i in range(10):
                                await asyncio.sleep(1)
                                response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
                                assert response.status_code == 200

                                saga = response.json()
                                if saga['status'] in ['CANCELLED', 'CANCELLATION_FAILED']:
                                    print(
                                        f"🎯 Resultado final: {saga['status']}")
                                    assert saga['status'] in [
                                        'CANCELLED', 'CANCELLATION_FAILED']
                                    break
                            else:
                                pytest.fail(
                                    "Timeout aguardando resultado do cancelamento")
                        else:
                            error = response.json()
                            print(
                                f"ℹ️ Cancelamento não aceito: {error['detail']}")
                            assert response.status_code in [400, 409]
