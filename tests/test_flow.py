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

        await asyncio.sleep(2)

        async with httpx.AsyncClient(timeout=30.0) as client:
            rand_num = random.randint(10000, 99999)

            customer_data = {
                "name": f"João Silva {rand_num}",
                "email": f"joao{rand_num}@email.com",
                "phone": f"11999{rand_num:05d}",
                "document": f"{rand_num:011d}",
                "initial_balance": 60000.0,
                "credit_limit": 50000.0
            }

            print(f"📝 Criando cliente: {customer_data['email']}")
            response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=customer_data)
            assert response.status_code == 201
            customer = response.json()
            print(
                f"✅ Cliente criado: {customer['id']} com saldo R\$ {customer['account_balance']}")

            vehicle_data = generate_unique_vehicle_data(
                brand="Honda", model="Civic", year=2023, color="Preto", price=45000.0
            )

            print(f"🚗 Criando veículo: {vehicle_data['license_plate']}")
            response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=vehicle_data)
            assert response.status_code == 201
            vehicle = response.json()
            print(f"✅ Veículo criado: {vehicle['id']}")

            purchase_data = {
                "customer_id": customer["id"],
                "vehicle_id": vehicle["id"],
                "payment_type": "cash"
            }
            print(
                f"🛒 Iniciando compra para cliente {customer['id']} e veículo {vehicle['id']}")
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202
            saga_init_response = response.json()
            transaction_id = saga_init_response["transaction_id"]
            print(f"⏳ Compra iniciada, Transaction ID: {transaction_id}")

            final_saga_state = await wait_for_saga_completion(client, transaction_id)
            print(f"✅ SAGA concluída com status: {final_saga_state['status']}")
            assert final_saga_state["status"] == "COMPLETED"

            response = await client.get(f"{CLIENTE_SERVICE_URL}/customers/{customer['id']}")
            assert response.status_code == 200
            updated_customer = response.json()
            expected_balance = customer_data["initial_balance"] - \
                vehicle_data["price"]
            assert updated_customer["account_balance"] == expected_balance
            assert updated_customer["available_credit"] == customer_data["credit_limit"]

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

            customer_data = {
                "name": f"Maria Credito {rand_num}",
                "email": f"maria{rand_num}@email.com",
                "phone": f"11888{rand_num:05d}",
                "document": f"{rand_num:011d}",
                "initial_balance": 5000.0,
                "credit_limit": 60000.0
            }

            response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=customer_data)
            assert response.status_code == 201
            customer = response.json()
            print(
                f"✅ Cliente criado: saldo R\$ {customer['account_balance']}, crédito R\$ {customer['available_credit']}")

            vehicle_data = generate_unique_vehicle_data(
                brand="Toyota", model="Corolla", year=2023, color="Branco", price=50000.0
            )

            response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=vehicle_data)
            assert response.status_code == 201
            vehicle = response.json()
            print(f"✅ Veículo criado: {vehicle['id']}")

            purchase_data = {
                "customer_id": customer["id"],
                "vehicle_id": vehicle["id"],
                "payment_type": "credit"
            }
            print(
                f"🛒 Iniciando compra por crédito para cliente {customer['id']} e veículo {vehicle['id']}")
            response = await client.post(f"{ORQUESTRADOR_SERVICE_URL}/purchase", json=purchase_data)
            assert response.status_code == 202
            saga_init_response = response.json()
            transaction_id = saga_init_response["transaction_id"]
            print(
                f"⏳ Compra por crédito iniciada, Transaction ID: {transaction_id}")

            final_saga_state = await wait_for_saga_completion(client, transaction_id)
            print(
                f"✅ SAGA por crédito concluída com status: {final_saga_state['status']}")
            assert final_saga_state["status"] == "COMPLETED"

            response = await client.get(f"{CLIENTE_SERVICE_URL}/customers/{customer['id']}")
            assert response.status_code == 200
            updated_customer = response.json()
            assert updated_customer["account_balance"] == customer_data["initial_balance"]
            assert updated_customer["available_credit"] == customer_data["credit_limit"] - \
                vehicle_data["price"]

            response = await client.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle['id']}")
            assert response.status_code == 200
            updated_vehicle = response.json()
            assert updated_vehicle["is_reserved"] is False
            assert updated_vehicle["is_sold"] is True

            print("✅ Fluxo de compra por crédito testado com sucesso.")
