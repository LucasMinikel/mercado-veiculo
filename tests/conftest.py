# tests/conftest.py
import pytest
from sqlalchemy import create_engine, text
# CORRIGIDO: importação de declarative_base()
from sqlalchemy.orm import sessionmaker, declarative_base

import os
import time
import requests
import warnings

# Base para os modelos ORM dos testes (usado para criar tabelas temporárias se necessário)
# CORRIGIDO: Uso de declarative_base() do sqlalchemy.orm
Base = declarative_base()

# Configuração do banco de dados para os testes
# Usa a mesma DATABASE_URL definida no docker-compose
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@db:5432/main_db")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)

@pytest.fixture(scope="session", autouse=True)
def wait_for_services():
    """Aguarda todos os serviços e o banco de dados ficarem disponíveis antes de iniciar os testes."""
    service_urls = {
        "cliente-service": "http://cliente-service:8080/health",
        "veiculo-service": "http://veiculo-service:8080/health",
        "pagamento-service": "http://pagamento-service:8080/health",
    }
    
    # Aguarda o DB estar saudável
    db_health_check_passed = False
    start_time = time.time()
    print("\nWaiting for DB to be healthy...")
    while time.time() - start_time < 60: # 60 segundos de timeout para o DB
        try:
            # Tenta conectar e executar uma query simples
            temp_engine = create_engine(DATABASE_URL)
            with temp_engine.connect() as connection:
                connection.execute(text("SELECT 1")) # Garante que a conexão com o DB está OK
            print("DB is healthy.")
            db_health_check_passed = True
            break
        except Exception as e:
            print(f"DB not ready yet: {e}")
            time.sleep(2)
    
    if not db_health_check_passed:
        pytest.fail("Database did not become healthy in time.")

    # Aguarda os microserviços estarem saudáveis
    for service_name, url in service_urls.items():
        print(f"Waiting for {service_name} at {url}...")
        start_time = time.time()
        while time.time() - start_time < 90: # 90 segundos de timeout para cada serviço
            try:
                response = requests.get(url, timeout=5)
                if response.status_code == 200 and response.json().get('status') == 'healthy':
                    print(f"{service_name} is healthy.")
                    break
            except requests.exceptions.ConnectionError:
                pass
            except requests.exceptions.Timeout:
                pass
            time.sleep(2)
        else:
            pytest.fail(f"{service_name} did not become healthy in time.")
    
    yield # Executa os testes

@pytest.fixture(scope="function", autouse=True)
def setup_teardown_db():
    """Fixture para limpar o banco de dados antes de cada função de teste."""
    # Garante que todas as tabelas sejam criadas (no caso de ser a primeira execução ou reset)
    # Ignora avisos sobre tabelas já existentes para evitar poluir a saída do teste.
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        Base.metadata.create_all(bind=engine)
    
    # Limpa todas as tabelas antes de cada teste
    with TestingSessionLocal() as session:
        print("\nCleaning database before test function...")
        
        tables_to_clear = ["customers", "vehicles", "payment_codes", "payments"]
        for table_name in tables_to_clear:
            try:
                # TRUNCATE é mais eficiente para limpar tabelas e reiniciar sequências de ID
                # CASCADE é para lidar com chaves estrangeiras (se houver)
                session.execute(text(f"TRUNCATE TABLE {table_name} RESTART IDENTITY CASCADE;"))
                print(f"Table {table_name} truncated.")
            except Exception as e:
                print(f"Could not truncate table {table_name}: {e}")
                session.rollback() # Rollback em caso de erro no truncate
        
        session.commit()
        print("Database cleanup for test function completed.")
    
    yield # Executa a função de teste