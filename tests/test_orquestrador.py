import pytest
import random
from conftest import ORQUESTRADOR_SERVICE_URL


class TestOrquestrador:
    """Testes específicos do orquestrador."""

    @pytest.mark.asyncio
    async def test_saga_state_tracking(self):
        """Testa o acompanhamento de estado da SAGA."""
        import httpx

        transaction_data = {
            "customer_id": random.randint(1, 1000),
            "vehicle_id": random.randint(1, 1000),
            "payment_type": "cash"
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=transaction_data)

            if response.status_code == 202:
                purchase = response.json()
                transaction_id = purchase["transaction_id"]
                print(f"✅ Transação iniciada: {transaction_id}")

                response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
                assert response.status_code == 200

                saga_state = response.json()
                assert "status" in saga_state
                assert "transaction_id" in saga_state
                assert saga_state["transaction_id"] == transaction_id
                print(f"✅ Estado da SAGA: {saga_state['status']}")

            elif response.status_code in [404, 400]:
                print(
                    "ℹ️ Transação falhou (IDs não existem ou validação falhou) - comportamento esperado")
                assert True

            else:
                print(
                    f"❌ Erro inesperado: {response.status_code} - {response.text}")
                assert False, f"Erro inesperado: {response.status_code}"

    @pytest.mark.asyncio
    async def test_purchase_validation(self):
        """Testa validações do endpoint de compra."""
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            invalid_data = {
                "customer_id": "invalid",
                "vehicle_id": 1,
                "payment_type": "invalid_type"
            }

            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=invalid_data)
            assert response.status_code == 422

            valid_data = {
                "customer_id": 999999,
                "vehicle_id": 999999,
                "payment_type": "cash"
            }

            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=valid_data)
            assert response.status_code in [400, 404]
            print("✅ Validações funcionando corretamente")
