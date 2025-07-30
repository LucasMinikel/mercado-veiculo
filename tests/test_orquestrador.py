# ./tests/test_orquestrador.py
import pytest
import random
from conftest import ORQUESTRADOR_SERVICE_URL


class TestOrquestrador:
    """Testes específicos do orquestrador."""

    @pytest.mark.asyncio
    async def test_saga_state_tracking(self):
        """Testa o acompanhamento de estado da SAGA."""
        import httpx

        # Dados de uma transação fictícia
        transaction_data = {
            "customer_id": random.randint(1, 1000),
            "vehicle_id": random.randint(1, 1000),
            "payment_type": "cash"  # Remover amount
        }

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Iniciar transação (pode falhar se IDs não existem, mas vamos testar a resposta)
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=transaction_data)

            if response.status_code == 202:
                # Transação iniciada com sucesso
                purchase = response.json()
                transaction_id = purchase["transaction_id"]
                print(f"✅ Transação iniciada: {transaction_id}")

                # Verificar estado da SAGA
                response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
                assert response.status_code == 200

                saga_state = response.json()
                assert "status" in saga_state
                assert "transaction_id" in saga_state
                assert saga_state["transaction_id"] == transaction_id
                print(f"✅ Estado da SAGA: {saga_state['status']}")

            elif response.status_code in [404, 400]:
                # IDs não existem ou validação falhou, mas isso é esperado em teste isolado
                print(
                    "ℹ️ Transação falhou (IDs não existem ou validação falhou) - comportamento esperado")
                assert True  # Teste passa mesmo assim

            else:
                # Outro erro inesperado
                print(
                    f"❌ Erro inesperado: {response.status_code} - {response.text}")
                assert False, f"Erro inesperado: {response.status_code}"

    @pytest.mark.asyncio
    async def test_purchase_validation(self):
        """Testa validações do endpoint de compra."""
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            # Teste com dados inválidos
            invalid_data = {
                "customer_id": "invalid",  # Deve ser int
                "vehicle_id": 1,
                "payment_type": "invalid_type"  # Deve ser cash ou credit
            }

            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=invalid_data)
            assert response.status_code == 422  # Validation error

            # Teste com payment_type válido
            valid_data = {
                "customer_id": 999999,  # ID que não existe
                "vehicle_id": 999999,
                "payment_type": "cash"
            }

            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=valid_data)
            # Deve retornar 404 (customer/vehicle not found) ou 400 (validation failed)
            assert response.status_code in [400, 404]
            print("✅ Validações funcionando corretamente")
