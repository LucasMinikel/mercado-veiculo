import pytest
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker, declarative_base

import os
import time
import requests
import warnings

Base = declarative_base()

DATABASE_URL = os.getenv(
    "DATABASE_URL", "postgresql://user:password@db:5432/main_db")
engine = create_engine(DATABASE_URL)
TestingSessionLocal = sessionmaker(
    autocommit=False, autoflush=False, bind=engine)


@pytest.fixture(scope="session", autouse=True)
def wait_for_services():
    service_urls = {
        "cliente-service": "http://cliente-service:8080/health",
        "veiculo-service": "http://veiculo-service:8080/health",
        "pagamento-service": "http://pagamento-service:8080/health",
    }

    db_health_check_passed = False
    start_time = time.time()
    print("\nWaiting for DB to be healthy...")
    while time.time() - start_time < 60:
        try:
            temp_engine = create_engine(DATABASE_URL)
            with temp_engine.connect() as connection:
                connection.execute(text("SELECT 1"))
            print("DB is healthy.")
            db_health_check_passed = True
            break
        except Exception as e:
            print(f"DB not ready yet: {e}")
            time.sleep(2)

    if not db_health_check_passed:
        pytest.fail("Database did not become healthy in time.")

    for service_name, url in service_urls.items():
        print(f"Waiting for {service_name} at {url}...")
        start_time = time.time()
        while time.time() - start_time < 90:
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

    yield


@pytest.fixture(scope="function", autouse=True)
def setup_teardown_db():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore")
        Base.metadata.create_all(bind=engine)

    with TestingSessionLocal() as session:
        print("\nCleaning database before test function...")

        tables_to_clear = ["customers", "vehicles",
                           "payment_codes", "payments"]
        allowed_tables = set(tables_to_clear)
        for table_name in tables_to_clear:
            try:
                if table_name in allowed_tables:
                    session.execute(
                        text(f'TRUNCATE TABLE "{table_name}" RESTART IDENTITY CASCADE;'))
                    print(f"Table {table_name} truncated.")
                else:
                    print(
                        f"Table {table_name} is not allowed to be truncated.")
            except Exception as e:
                print(f"Could not truncate table {table_name}: {e}")
                session.rollback()

        session.commit()
        print("Database cleanup for test function completed.")

    yield
