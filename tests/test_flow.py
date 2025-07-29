# ./tests/test_flow.py
import pytest
import httpx
import asyncio
import random

# URLs dos serviços
CLIENTE_SERVICE_URL = "http://cliente-service:8080"
VEICULO_SERVICE_URL = "http://veiculo-service:8080"
PAGAMENTO_SERVICE_URL = "http://pagamento-service:8080"
ORQUESTRADOR_SERVICE_URL = "http://orquestrador:8080"


class TestFlow:
    """Testes de fluxo completo do sistema."""

    @pytest.mark.asyncio
    async def test_services_health(self):
        """Testa se todos os serviços estão saudáveis."""
        services = {
            "cliente": f"{CLIENTE_SERVICE_URL}/health",
            "veiculo": f"{VEICULO_SERVICE_URL}/health",
            "pagamento": f"{PAGAMENTO_SERVICE_URL}/health",
            "orquestrador": f"{ORQUESTRADOR_SERVICE_URL}/health"
        }

        async with httpx.AsyncClient(timeout=30.0) as client:
            for name, url in services.items():
                response = await client.get(url)
                assert response.status_code == 200
                health = response.json()
                assert health["status"] == "healthy"
                print(f"✅ {name} está saudável")

    @pytest.mark.asyncio
    async def test_complete_purchase_flow(self):
        """Testa o fluxo completo de compra de veículo."""
        print("🔄 Aguardando serviços...")

        # Aguardar um pouco para garantir que os serviços estejam prontos
        await asyncio.sleep(2)

        async with httpx.AsyncClient(timeout=30.0) as client:
            # Dados únicos para evitar conflitos
            rand_num = random.randint(10000, 99999)

            # 1. Criar cliente
            customer_data = {
                "name": f"João Silva {rand_num}",
                "email": f"joao{rand_num}@email.com",
                "phone": f"11999{rand_num:05d}",
                "document": f"{rand_num:011d}",
                "credit_limit": 50000.0
            }

            print(f"📝 Criando cliente: {customer_data['email']}")
            response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=customer_data)
            assert response.status_code == 201
            customer = response.json()
            print(f"✅ Cliente criado: {customer['id']}")

            # 2. Criar veículo
            vehicle_data = {
                "brand": "Honda",
                "model": "Civic",
                "year": 2023,
                "color": "Preto",
                "price": 45000.0,
                "license_plate": f"ABC{rand_num % 10000:04d}"
            }

            print(f"🚗 Criando veículo: {vehicle_data['license_plate']}")
            response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=vehicle_data)
            assert response.status_code == 201
            vehicle = response.json()
            print(f"✅ Veículo criado: {vehicle['id']}")

            # 3. Iniciar compra
            purchase_data = {
                "customer_id": customer["id"],
                "vehicle_id": vehicle["id"],
                "amount": vehicle["price"]
            }

            print(
                f"💰 Iniciando compra: Cliente {customer['id']} -> Veículo {vehicle['id']} (R\$ {vehicle['price']})")
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202

            purchase = response.json()
            transaction_id = purchase["transaction_id"]
            print(f"✅ Compra iniciada: {transaction_id}")

            # 4. Acompanhar SAGA
            max_attempts = 30
            for attempt in range(max_attempts):
                response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
                assert response.status_code == 200

                saga = response.json()
                status = saga["status"]
                step = saga["current_step"]

                print(f"📊 SAGA Status: {status} - Step: {step}")

                if status == "COMPLETED":
                    print(f"🏁 Status final: {status}")
                    print("✅ Fluxo completo executado com sucesso!")
                    return
                elif status in ["FAILED", "FAILED_COMPENSATED"]:
                    pytest.fail(
                        f"SAGA falhou: {status} - {saga.get('context', {})}")

                await asyncio.sleep(2)

            pytest.fail(
                f"SAGA não foi concluída em {max_attempts * 2} segundos")
