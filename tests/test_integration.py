import requests
import time
import threading
import uuid

VEICULO_SERVICE_URL = "http://veiculo-service:8080"
CLIENTE_SERVICE_URL = "http://cliente-service:8080"
PAGAMENTO_SERVICE_URL = "http://pagamento-service:8080"

class TestIntegration:
    def generate_unique_document(self):
        unique_id = str(uuid.uuid4()).replace('-', '')[:11]
        return unique_id
    
    
    def test_all_services_health(self):
        response = requests.get(f"{VEICULO_SERVICE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'vehicle-service'
    
        response = requests.get(f"{CLIENTE_SERVICE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'customer-service'
        
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'payment-service'
    
    
    def test_services_communication(self):
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles")
        assert response.status_code == 200
        vehicles_data = response.json()
        assert 'vehicles' in vehicles_data
        assert 'total' in vehicles_data
        
        response = requests.get(f"{CLIENTE_SERVICE_URL}/customers")
        assert response.status_code == 200
        customers_data = response.json()
        assert 'customers' in customers_data
        assert 'total' in customers_data
        
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payments")
        assert response.status_code == 200
        payments_data = response.json()
        assert 'payments' in payments_data
        assert 'total' in payments_data
    
    
    def test_service_isolation(self):
        unique_id = str(uuid.uuid4())[:8]
        new_vehicle = {
            "brand": f"BMW_{unique_id}",
            "model": "X3",
            "year": 2023,
            "color": "Preto",
            "price": 150000.00
        }
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        created_vehicle = response.json()
        
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles")
        assert response.status_code == 200
        vehicles = response.json()['vehicles']
        
        vehicle_ids = [v['id'] for v in vehicles]
        assert created_vehicle['id'] in vehicle_ids
        
        unique_doc = self.generate_unique_document()
        unique_email = f"integration_{unique_doc}@email.com"
        
        new_customer = {
            "name": f"João Teste Integration {unique_doc[:6]}",
            "email": unique_email,
            "phone": "11999999999",
            "document": unique_doc,
            "credit_limit": 100000.00
        }
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=new_customer,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 409:
            unique_doc = self.generate_unique_document()
            unique_email = f"integration_{unique_doc}@email.com"
            new_customer["document"] = unique_doc
            new_customer["email"] = unique_email
            new_customer["name"] = f"João Teste Integration {unique_doc[:6]}"
            
            response = requests.post(
                f"{CLIENTE_SERVICE_URL}/customers",
                json=new_customer,
                headers={'Content-Type': 'application/json'}
            )
        
        assert response.status_code == 201
        created_customer = response.json()
        assert created_customer['name'] == new_customer['name']
        
        payment_data = {
            "customer_id": created_customer['id'],
            "vehicle_id": created_vehicle['id'],
            "amount": created_vehicle['price']
        }
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        payment_code_data = response.json()
        assert payment_code_data['customer_id'] == created_customer['id']
        assert payment_code_data['vehicle_id'] == created_vehicle['id']
        assert payment_code_data['amount'] == created_vehicle['price']
    
    
    def test_error_handling_integration(self):
        response = requests.get(f"{VEICULO_SERVICE_URL}/nonexistent")
        assert response.status_code == 404
        
        response = requests.get(f"{CLIENTE_SERVICE_URL}/nonexistent")
        assert response.status_code == 404
        
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/nonexistent")
        assert response.status_code == 404
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            data="invalid json",
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 422
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            data="invalid json",
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 422
    
    
    def test_concurrent_requests_integration(self):
        results = []
        errors = []
        
        def make_request(service_url, endpoint):
            try:
                response = requests.get(f"{service_url}{endpoint}", timeout=5)
                results.append(response.status_code)
            except Exception as e:
                errors.append(str(e))
        
        threads = []
        
        for _ in range(3):
            threads.append(threading.Thread(target=make_request, args=(VEICULO_SERVICE_URL, "/vehicles")))
            threads.append(threading.Thread(target=make_request, args=(CLIENTE_SERVICE_URL, "/customers")))
            threads.append(threading.Thread(target=make_request, args=(PAGAMENTO_SERVICE_URL, "/payments")))
            threads.append(threading.Thread(target=make_request, args=(VEICULO_SERVICE_URL, "/health")))
            threads.append(threading.Thread(target=make_request, args=(CLIENTE_SERVICE_URL, "/health")))
            threads.append(threading.Thread(target=make_request, args=(PAGAMENTO_SERVICE_URL, "/health")))
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        assert len(errors) == 0, f"Erros encontrados: {errors}"
        
        assert all(status == 200 for status in results), f"Status codes: {results}"
        assert len(results) == 18
    
    
    def test_service_performance_integration(self):
        start_time = time.time()
        
        responses = []
        
        for i in range(3):
            response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles")
            responses.append(response.status_code)
            
            response = requests.get(f"{CLIENTE_SERVICE_URL}/customers")
            responses.append(response.status_code)
            
            response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payments")
            responses.append(response.status_code)
        
        end_time = time.time()
        total_time = end_time - start_time
        
        assert all(status == 200 for status in responses)
        
        assert total_time < 15.0
    
    
    def test_cross_service_workflow(self):
        unique_doc = self.generate_unique_document()
        unique_email = f"workflow_{unique_doc}@email.com"
        unique_id = str(uuid.uuid4())[:8]
        
        new_customer = {
            "name": f"Cliente Workflow {unique_id}",
            "email": unique_email,
            "phone": "11999999999",
            "document": unique_doc,
            "credit_limit": 200000.00
        }
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=new_customer,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 409:
            unique_doc = self.generate_unique_document()
            unique_email = f"workflow_{unique_doc}@email.com"
            unique_id = str(uuid.uuid4())[:8]
            new_customer["document"] = unique_doc
            new_customer["email"] = unique_email
            new_customer["name"] = f"Cliente Workflow {unique_id}"
            
            response = requests.post(
                f"{CLIENTE_SERVICE_URL}/customers",
                json=new_customer,
                headers={'Content-Type': 'application/json'}
            )
        
        assert response.status_code == 201
        customer = response.json()
        customer_id = customer['id']
        
        vehicle_unique_id = str(uuid.uuid4())[:8]
        new_vehicle = {
            "brand": f"Audi_{vehicle_unique_id}",
            "model": "A4",
            "year": 2023,
            "color": "Branco",
            "price": 180000.00
        }
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 201
        vehicle = response.json()
        vehicle_id = vehicle['id']
        
        credit_data = {"amount": vehicle['price']}
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/{customer_id}/credit/reserve",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 200
        
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/reserve")
        assert response.status_code == 200
        
        payment_data = {
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "amount": vehicle['price']
        }
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 201
        payment_code = response.json()['payment_code']
        
        payment_request = {
            "payment_code": payment_code,
            "payment_method": "pix"
        }
        
        payment_processed = False
        max_attempts = 10
        for _ in range(max_attempts):
            response = requests.post(
                f"{PAGAMENTO_SERVICE_URL}/payments",
                json=payment_request,
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code == 201:
                payment_processed = True
                payment_id = response.json()['payment_id']
                break
            elif response.status_code == 400 and "Payment processing failed" in response.json().get('detail', ''):
                response = requests.post(
                    f"{PAGAMENTO_SERVICE_URL}/payment-codes",
                    json=payment_data,
                    headers={'Content-Type': 'application/json'}
                )
                payment_code = response.json()['payment_code']
                payment_request["payment_code"] = payment_code
                time.sleep(0.5)
            else:
                break
        
        assert payment_processed, f"Failed to process payment after {max_attempts} attempts: {response.json()}"
        
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        assert response.status_code == 200
        vehicle_status = response.json()
        assert vehicle_status['status'] == 'reserved'
        
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/release")
        assert response.status_code == 200
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/{customer_id}/credit/release",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 200
        
        if payment_processed:
            response = requests.post(f"{PAGAMENTO_SERVICE_URL}/payments/{payment_id}/refund")
            assert response.status_code == 200
        
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        vehicle_final = response.json()
        assert vehicle_final['status'] == 'available'
    
    
    def test_payment_integration_workflow(self):
        unique_doc = self.generate_unique_document()
        unique_email = f"payment_test_{unique_doc}@email.com"
        unique_id = str(uuid.uuid4())[:8]
        
        new_customer = {
            "name": f"Cliente Payment Test {unique_id}",
            "email": unique_email,
            "phone": "11999999999",
            "document": unique_doc,
            "credit_limit": 100000.00
        }
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=new_customer,
            headers={'Content-Type': 'application/json'}
        )
        
        if response.status_code == 409:
            unique_doc = self.generate_unique_document()
            unique_email = f"payment_test_{unique_doc}@email.com"
            new_customer["document"] = unique_doc
            new_customer["email"] = unique_email
            
            response = requests.post(
                f"{CLIENTE_SERVICE_URL}/customers",
                json=new_customer,
                headers={'Content-Type': 'application/json'}
            )
        
        assert response.status_code == 201
        customer_id = response.json()['id']
        
        vehicle_unique_id = str(uuid.uuid4())[:8]
        new_vehicle = {
            "brand": f"Payment_Test_{vehicle_unique_id}",
            "model": "Test_Model",
            "year": 2023,
            "color": "Test_Color",
            "price": 75000.00
        }
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 201
        vehicle_id = response.json()['id']
        
        payment_data = {
            "customer_id": customer_id,
            "vehicle_id": vehicle_id,
            "amount": 75000.00
        }
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 201
        payment_code_data = response.json()
        
        assert payment_code_data['customer_id'] == customer_id
        assert payment_code_data['vehicle_id'] == vehicle_id
        assert payment_code_data['amount'] == 75000.00
        
        payment_methods = ["pix", "card", "bank_transfer"]
        
        for method in payment_methods:
            response = requests.post(
                f"{PAGAMENTO_SERVICE_URL}/payment-codes",
                json=payment_data,
                headers={'Content-Type': 'application/json'}
            )
            payment_code = response.json()['payment_code']
            
            payment_request = {
                "payment_code": payment_code,
                "payment_method": method
            }
            
            max_attempts = 5
            processed = False
            for _ in range(max_attempts):
                response = requests.post(
                    f"{PAGAMENTO_SERVICE_URL}/payments",
                    json=payment_request,
                    headers={'Content-Type': 'application/json'}
                )
                if response.status_code == 201:
                    payment_data_response = response.json()
                    assert payment_data_response['payment_method'] == method
                    processed = True
                    break
                elif response.status_code == 400 and "Payment processing failed" in response.json().get('detail', ''):
                    response = requests.post(
                        f"{PAGAMENTO_SERVICE_URL}/payment-codes",
                        json=payment_data,
                        headers={'Content-Type': 'application/json'}
                    )
                    payment_code = response.json()['payment_code']
                    payment_request["payment_code"] = payment_code
                    time.sleep(0.5)
                else:
                    break
            assert processed, f"Failed to process payment for method {method} after {max_attempts} attempts: {response.json()}"
    
    
    def test_microservices_resilience(self):
        results = {
            'veiculo': [],
            'cliente': [],
            'pagamento': []
        }
        errors = []
        
        def stress_test_service(service_name, service_url, endpoint):
            try:
                for _ in range(3):
                    response = requests.get(f"{service_url}{endpoint}", timeout=5)
                    results[service_name].append(response.status_code)
                    time.sleep(0.1)
            except Exception as e:
                errors.append(f"{service_name}: {str(e)}")
        
        threads = [
            threading.Thread(target=stress_test_service, args=('veiculo', VEICULO_SERVICE_URL, '/vehicles')),
            threading.Thread(target=stress_test_service, args=('cliente', CLIENTE_SERVICE_URL, '/customers')),
            threading.Thread(target=stress_test_service, args=('pagamento', PAGAMENTO_SERVICE_URL, '/payments')),
        ]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        assert len(errors) == 0, f"Erros encontrados: {errors}"
        
        for service_name, status_codes in results.items():
            assert len(status_codes) == 3, f"Serviço {service_name} não completou todas as requisições"
            assert all(status == 200 for status in status_codes), f"Serviço {service_name} teve falhas: {status_codes}"