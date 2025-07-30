# ./tests/test_flow.py
import pytest
import httpx
import random
import asyncio
from conftest import CLIENTE_SERVICE_URL, VEICULO_SERVICE_URL, PAGAMENTO_SERVICE_URL, ORQUESTRADOR_SERVICE_URL, \
    wait_for_saga_completion, check_services_health, generate_unique_vehicle_data


class TestFlow:
    """Testes de fluxo completo e cenários da SAGA."""

    @pytest.mark.asyncio
    async def test_services_health(self):
        """Verifica se todos os serviços estão saudáveis antes de rodar os testes de fluxo."""
        await check_services_health()
        print("✅ cliente está saudável")
        print("✅ veiculo está saudável")
        print("✅ pagamento está saudável")
        print("✅ orquestrador está saudável")

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
            # Usar o helper para gerar dados completos e válidos
            vehicle_data = generate_unique_vehicle_data(
                brand="Honda", model="Civic", year=2023, color="Preto", price=45000.0
            )

            print(f"🚗 Criando veículo: {vehicle_data['license_plate']}")
            response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=vehicle_data)
            assert response.status_code == 201
            vehicle = response.json()
            print(f"✅ Veículo criado: {vehicle['id']}")

            # 3. Iniciar o processo de compra (SAGA)
            purchase_data = {
                "customer_id": customer["id"],
                "vehicle_id": vehicle["id"],
                "payment_type": "cash"  # ALTERADO PARA 'cash'
            }
            print(
                f"🛒 Iniciando compra para cliente {customer['id']} e veículo {vehicle['id']}")
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202
            saga_init_response = response.json()
            transaction_id = saga_init_response["transaction_id"]
            print(f"⏳ Compra iniciada, Transaction ID: {transaction_id}")

            # 4. Aguardar a conclusão da SAGA
            final_saga_state = await wait_for_saga_completion(client, transaction_id)
            print(f"✅ SAGA concluída com status: {final_saga_state['status']}")
            assert final_saga_state["status"] == "COMPLETED"

            # 5. Verificar o estado final do cliente
            response = await client.get(f"{CLIENTE_SERVICE_URL}/customers/{customer['id']}")
            assert response.status_code == 200
            updated_customer = response.json()
            # Saldo inicial - preço do veículo
            expected_balance = customer_data["initial_balance"] - \
                vehicle_data["price"]
            assert updated_customer["account_balance"] == expected_balance
            # Limite de crédito não deve ser tocado para pagamento em dinheiro
            assert updated_customer["available_credit"] == customer_data["credit_limit"]

            # 6. Verificar o estado final do veículo
            response = await client.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle['id']}")
            assert response.status_code == 200
            updated_vehicle = response.json()
            assert updated_vehicle["is_reserved"] is False
            assert updated_vehicle["is_sold"] is True

            print("✅ Fluxo de compra completo testado com sucesso.")

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
            # Usar o helper para gerar dados completos e válidos
            vehicle_data = generate_unique_vehicle_data(
                # Ajustar o preço se necessário
                brand="Toyota", model="Corolla", year=2023, color="Branco", price=50000.0
            )

            response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=vehicle_data)
            assert response.status_code == 201
            vehicle = response.json()
            print(f"✅ Veículo criado: {vehicle['id']}")

            # 3. Iniciar o processo de compra (SAGA)
            purchase_data = {
                "customer_id": customer["id"],
                "vehicle_id": vehicle["id"],
                "payment_type": "credit"  # Usar crédito
            }
            print(
                f"🛒 Iniciando compra por crédito para cliente {customer['id']} e veículo {vehicle['id']}")
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202
            saga_init_response = response.json()
            transaction_id = saga_init_response["transaction_id"]
            print(
                f"⏳ Compra por crédito iniciada, Transaction ID: {transaction_id}")

            # 4. Aguardar a conclusão da SAGA
            final_saga_state = await wait_for_saga_completion(client, transaction_id)
            print(
                f"✅ SAGA por crédito concluída com status: {final_saga_state['status']}")
            assert final_saga_state["status"] == "COMPLETED"

            # 5. Verificar o estado final do cliente (crédito utilizado)
            response = await client.get(f"{CLIENTE_SERVICE_URL}/customers/{customer['id']}")
            assert response.status_code == 200
            updated_customer = response.json()
            # Saldo deve permanecer o mesmo, crédito utilizado deve ser o preço do veículo
            assert updated_customer["account_balance"] == customer_data["initial_balance"]
            assert updated_customer["available_credit"] == customer_data["credit_limit"] - \
                vehicle_data["price"]

            # 6. Verificar o estado final do veículo
            response = await client.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle['id']}")
            assert response.status_code == 200
            updated_vehicle = response.json()
            assert updated_vehicle["is_reserved"] is False
            assert updated_vehicle["is_sold"] is True

            print("✅ Fluxo de compra por crédito testado com sucesso.")
