import pytest
from conftest import PAGAMENTO_SERVICE_URL


class TestPagamentoService:
    """Testes específicos do serviço de pagamentos."""

    @pytest.mark.asyncio
    async def test_payment_service_health(self):
        """Testa se o serviço de pagamento está funcionando."""
        import httpx

        async with httpx.AsyncClient(timeout=10.0) as client:
            response = await client.get(f"{PAGAMENTO_SERVICE_URL}/health")
            assert response.status_code == 200

            health = response.json()
            assert health["status"] == "healthy"
            print(f"✅ Serviço de pagamento está saudável")

            try:
                response = await client.get(f"{PAGAMENTO_SERVICE_URL}/payment-codes")
                if response.status_code == 200:
                    codes = response.json()
                    print(
                        f"✅ Endpoint de códigos acessível - {len(codes)} códigos encontrados")
                else:
                    print(
                        f"ℹ️ Endpoint de códigos retornou: {response.status_code}")
            except Exception as e:
                print(f"ℹ️ Endpoint de listagem não disponível: {e}")
