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

            # 1. Criar cliente com saldo suficiente
            customer_data = {
                "name": f"João Silva {rand_num}",
                "email": f"joao{rand_num}@email.com",
                "phone": f"11999{rand_num:05d}",
                "document": f"{rand_num:011d}",
                "initial_balance": 60000.0,  # Saldo suficiente
                "credit_limit": 50000.0
            }

            print(f"📝 Criando cliente: {customer_data['email']}")
            response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=customer_data)
            assert response.status_code == 201
            customer = response.json()
            print(
                f"✅ Cliente criado: {customer['id']} com saldo R\$ {customer['account_balance']}")

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
            print(
                f"✅ Veículo criado: {vehicle['id']} - R\$ {vehicle['price']}")

            # 3. Iniciar compra - SEM amount
            purchase_data = {
                "customer_id": customer["id"],
                "vehicle_id": vehicle["id"],
                "payment_type": "cash"  # Usar saldo em conta
            }

            print(
                f"💰 Iniciando compra: Cliente {customer['id']} -> Veículo {vehicle['id']} (R\$ {vehicle['price']}) via {purchase_data['payment_type']}")
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202

            purchase = response.json()
            transaction_id = purchase["transaction_id"]
            print(f"✅ Compra iniciada: {transaction_id}")
            print(
                f"📊 Preço detectado automaticamente: R\$ {purchase.get('vehicle_price', 'N/A')}")

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

                    # Verificar se o preço foi definido corretamente
                    assert saga["amount"] == vehicle["price"]
                    print(f"✅ Preço correto na SAGA: R\$ {saga['amount']}")
                    return
                elif status in ["FAILED", "FAILED_COMPENSATED"]:
                    print(f"❌ SAGA falhou: {status}")
                    print(f"🔍 Contexto: {saga.get('context', {})}")
                    pytest.fail(
                        f"SAGA falhou: {status} - {saga.get('context', {})}")

                await asyncio.sleep(2)

            pytest.fail(
                f"SAGA não foi concluída em {max_attempts * 2} segundos")

    @pytest.mark.asyncio
    async def test_credit_purchase_flow(self):
        """Testa o fluxo de compra usando limite de crédito."""
        async with httpx.AsyncClient(timeout=30.0) as client:
            rand_num = random.randint(20000, 29999)

            # 1. Criar cliente com limite de crédito alto, mas saldo baixo
            customer_data = {
                "name": f"Maria Credito {rand_num}",
                "email": f"maria{rand_num}@email.com",
                "phone": f"11888{rand_num:05d}",
                "document": f"{rand_num:011d}",
                "initial_balance": 5000.0,  # Saldo baixo
                "credit_limit": 60000.0     # Crédito alto
            }

            response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=customer_data)
            assert response.status_code == 201
            customer = response.json()
            print(
                f"✅ Cliente criado: saldo R\$ {customer['account_balance']}, crédito R\$ {customer['available_credit']}")

            # 2. Criar veículo
            vehicle_data = {
                "brand": "Toyota",
                "model": "Corolla",
                "year": 2023,
                "color": "Branco",
                "price": 50000.0,
                "license_plate": f"XYZ{rand_num % 10000:04d}"
            }

            response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=vehicle_data)
            assert response.status_code == 201
            vehicle = response.json()

            # 3. Compra usando crédito
            purchase_data = {
                "customer_id": customer["id"],
                "vehicle_id": vehicle["id"],
                "payment_type": "credit"  # Usar limite de crédito
            }

            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202

            purchase = response.json()
            transaction_id = purchase["transaction_id"]
            print(f"✅ Compra a crédito iniciada: {transaction_id}")

            # 4. Aguardar conclusão
            for attempt in range(30):
                response = await client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
                saga = response.json()

                if saga["status"] == "COMPLETED":
                    print("✅ Compra a crédito concluída com sucesso!")
                    return
                elif saga["status"] in ["FAILED", "FAILED_COMPENSATED"]:
                    pytest.fail(f"Compra a crédito falhou: {saga['status']}")

                await asyncio.sleep(2)

            pytest.fail("Compra a crédito não foi concluída")
