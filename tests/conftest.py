import pytest
import httpx
import os
import random
import asyncio
import string
from typing import Dict, Any

CLIENTE_SERVICE_URL = os.getenv(
    "CLIENTE_SERVICE_URL", "http://cliente-service:8080")
VEICULO_SERVICE_URL = os.getenv(
    "VEICULO_SERVICE_URL", "http://veiculo-service:8080")
PAGAMENTO_SERVICE_URL = os.getenv(
    "PAGAMENTO_SERVICE_URL", "http://pagamento-service:8080")
ORQUESTRADOR_SERVICE_URL = os.getenv(
    "ORQUESTRADOR_SERVICE_URL", "http://orquestrador:8080")

DEFAULT_TIMEOUT = 30.0


def generate_unique_vehicle_data(brand="Toyota", model="Corolla", year=2023, color="Branco", price=45000.0):
    """Gera dados de veículo únicos e válidos para testes."""
    license_plate_chars = ''.join(random.choices(
        string.ascii_uppercase + string.digits, k=4))

    chassi_random_chars = ''.join(random.choices(
        string.ascii_uppercase + string.digits + string.digits, k=14))

    renavam_random_digits = ''.join(random.choices(string.digits, k=5))

    return {
        "brand": brand,
        "model": model,
        "year": year,
        "color": color,
        "price": price,
        "license_plate": f"ABC{license_plate_chars}",
        "chassi_number": f"VIN{chassi_random_chars}",
        "renavam": f"123456{renavam_random_digits}"
    }


@pytest.fixture
def sample_customer():
    """Gera dados de cliente únicos para cada teste."""
    rand_num = random.randint(10000, 99999)
    return {
        "name": f"João Silva {rand_num}",
        "email": f"joao{rand_num}@email.com",
        "phone": f"11999{rand_num:05d}",
        "document": f"{rand_num:011d}",
        "initial_balance": 60000.0,
        "credit_limit": 50000.0
    }


@pytest.fixture
def sample_vehicle():
    """Fixture que retorna dados de veículo únicos, usando a função helper."""
    return generate_unique_vehicle_data()


@pytest.fixture
def low_credit_customer():
    """Cliente com crédito insuficiente para testes de falha."""
    rand_num = random.randint(10000, 99999)
    return {
        "name": f"Maria Pobre {rand_num}",
        "email": f"maria{rand_num}@email.com",
        "phone": f"11888{rand_num:05d}",
        "document": f"{rand_num:011d}",
        "initial_balance": 1000.0,
        "credit_limit": 1000.0
    }


async def wait_for_saga_completion(http_client, transaction_id: str, timeout: int = 60) -> Dict[str, Any]:
    """Aguarda a conclusão de uma SAGA e retorna o estado final."""
    for _ in range(timeout):
        try:
            response = await http_client.get(f"{ORQUESTRADOR_SERVICE_URL}/saga-states/{transaction_id}")
            if response.status_code == 200:
                saga = response.json()
                status = saga["status"]
                if status in ["COMPLETED", "FAILED", "FAILED_COMPENSATED", "FAILED_REQUIRES_MANUAL_INTERVENTION"]:
                    return saga
        except Exception:
            pass
        await asyncio.sleep(1)

    pytest.fail(
        f"SAGA {transaction_id} não foi concluída em {timeout} segundos")


async def create_test_customer(customer_data):
    """Função helper para criar cliente."""
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.post(f"{CLIENTE_SERVICE_URL}/customers", json=customer_data)
        assert response.status_code == 201
        return response.json()


async def create_test_vehicle(vehicle_data):
    """Função helper para criar veículo."""
    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        response = await client.post(f"{VEICULO_SERVICE_URL}/vehicles", json=vehicle_data)
        assert response.status_code == 201
        return response.json()


async def check_services_health():
    """Função helper para verificar saúde dos serviços."""
    services = {
        "cliente": f"{CLIENTE_SERVICE_URL}/health",
        "veiculo": f"{VEICULO_SERVICE_URL}/health",
        "pagamento": f"{PAGAMENTO_SERVICE_URL}/health",
        "orquestrador": f"{ORQUESTRADOR_SERVICE_URL}/health"
    }

    async with httpx.AsyncClient(timeout=DEFAULT_TIMEOUT) as client:
        for name, url in services.items():
            for attempt in range(10):
                try:
                    response = await client.get(url)
                    if response.status_code == 200:
                        health = response.json()
                        assert health["status"] == "healthy", f"Serviço {name} não está saudável"
                        break
                except Exception as e:
                    if attempt == 9:
                        pytest.fail(
                            f"Serviço {name} não ficou disponível: {e}")
                    await asyncio.sleep(1)
    return True
