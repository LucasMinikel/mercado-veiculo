# tests/test_integration.py
import requests
import time
import threading
import uuid

# Configurações do teste
VEICULO_SERVICE_URL = "http://veiculo-service:8080"
CLIENTE_SERVICE_URL = "http://cliente-service:8080"
PAGAMENTO_SERVICE_URL = "http://pagamento-service:8080"

class TestIntegration:
    
    def setup_method(self):
        """Aguarda os serviços ficarem prontos antes de cada teste"""
        self.wait_for_services()
    
    def wait_for_services(self, timeout=30):
        """Aguarda todos os serviços ficarem disponíveis"""
        services = [
            VEICULO_SERVICE_URL,
            CLIENTE_SERVICE_URL,
            PAGAMENTO_SERVICE_URL
        ]
        
        for service_url in services:
            start_time = time.time()
            while time.time() - start_time < timeout:
                try:
                    response = requests.get(f"{service_url}/health", timeout=2)
                    if response.status_code == 200:
                        break
                except requests.RequestException:
                    pass
                time.sleep(1)
            else:
                raise Exception(f"Serviço {service_url} não ficou disponível em {timeout} segundos")
    
    def generate_unique_document(self):
        """Gera um documento único para evitar conflitos"""
        # Usa UUID para garantir unicidade
        unique_id = str(uuid.uuid4()).replace('-', '')[:11]
        return unique_id
    
    
    def test_all_services_health(self):
        """Testa se todos os serviços estão funcionando"""
        # Testa veiculo-service
        response = requests.get(f"{VEICULO_SERVICE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'vehicle-service'
        
        # Testa cliente-service
        response = requests.get(f"{CLIENTE_SERVICE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'customer-service'
        
        # Testa pagamento-service
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/health")
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'payment-service'
    
    
    def test_services_communication(self):
        """Testa se os serviços podem se comunicar entre si"""
        # Obtém veículos disponíveis
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles")
        assert response.status_code == 200
        vehicles_data = response.json()
        assert 'vehicles' in vehicles_data
        assert 'total' in vehicles_data
        
        # Obtém clientes
        response = requests.get(f"{CLIENTE_SERVICE_URL}/customers")
        assert response.status_code == 200
        customers_data = response.json()
        assert 'customers' in customers_data
        assert 'total' in customers_data
        
        # Obtém pagamentos
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payments")
        assert response.status_code == 200
        payments_data = response.json()
        assert 'payments' in payments_data
        assert 'total' in payments_data
    
    
    def test_service_isolation(self):
        """Testa se os serviços funcionam independentemente"""
        # Cria um veículo com ID único
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
        
        # Verifica se o veículo foi criado corretamente
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles")
        assert response.status_code == 200
        vehicles = response.json()['vehicles']
        
        # Verifica se o novo veículo está na lista
        vehicle_ids = [v['id'] for v in vehicles]
        assert created_vehicle['id'] in vehicle_ids
        
        # Cria um cliente com documento único
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
        
        # Se der 409, tenta com outro documento
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
        
        # Cria um código de pagamento
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
        """Testa o tratamento de erros em cenários de integração"""
        # Testa requisição para endpoint inexistente
        response = requests.get(f"{VEICULO_SERVICE_URL}/nonexistent")
        assert response.status_code == 404
        
        response = requests.get(f"{CLIENTE_SERVICE_URL}/nonexistent")
        assert response.status_code == 404
        
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/nonexistent")
        assert response.status_code == 404
        
        # Testa requisição malformada
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            data="invalid json",
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 422  # FastAPI retorna 422 para validation errors
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            data="invalid json",
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 422
    
    
    def test_concurrent_requests_integration(self):
        """Testa requisições concorrentes para verificar estabilidade"""
        results = []
        errors = []
        
        def make_request(service_url, endpoint):
            try:
                response = requests.get(f"{service_url}{endpoint}", timeout=5)
                results.append(response.status_code)
            except Exception as e:
                errors.append(str(e))
        
        threads = []
        
        # Cria múltiplas threads para fazer requisições simultâneas
        for _ in range(3):
            threads.append(threading.Thread(target=make_request, args=(VEICULO_SERVICE_URL, "/vehicles")))
            threads.append(threading.Thread(target=make_request, args=(CLIENTE_SERVICE_URL, "/customers")))
            threads.append(threading.Thread(target=make_request, args=(PAGAMENTO_SERVICE_URL, "/payments")))
            threads.append(threading.Thread(target=make_request, args=(VEICULO_SERVICE_URL, "/health")))
            threads.append(threading.Thread(target=make_request, args=(CLIENTE_SERVICE_URL, "/health")))
            threads.append(threading.Thread(target=make_request, args=(PAGAMENTO_SERVICE_URL, "/health")))
        
        # Inicia todas as threads
        for thread in threads:
            thread.start()
        
        # Aguarda todas as threads terminarem
        for thread in threads:
            thread.join()
        
        # Verifica se não houve erros
        assert len(errors) == 0, f"Erros encontrados: {errors}"
        
        # Verifica se todas as requisições foram bem-sucedidas
        assert all(status == 200 for status in results), f"Status codes: {results}"
        assert len(results) == 18  # 6 requisições × 3 iterações
    
    
    def test_service_performance_integration(self):
        """Testa performance em cenário de integração"""
        start_time = time.time()
        
        # Faz múltiplas requisições para diferentes serviços
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
        
        # Todas as requisições devem ter sucesso
        assert all(status == 200 for status in responses)
        
        # Tempo total deve ser razoável
        assert total_time < 15.0  # Menos de 15 segundos para todas as requisições
    
    
    def test_cross_service_workflow(self):
        """Testa um fluxo completo entre serviços"""
        # 1. Cria um cliente com dados únicos
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
        
        # Se der 409, tenta com outro documento
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
        
        # 2. Cria um veículo com dados únicos
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
        
        # 3. Reserva crédito do cliente
        credit_data = {"amount": vehicle['price']}
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/{customer_id}/credit/reserve",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 200
        
        # 4. Reserva o veículo
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/reserve")
        assert response.status_code == 200
        
        # 5. Gera código de pagamento
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
        
        # 6. Processa o pagamento (com retry devido ao random)
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
                # Gera novo código e tenta novamente
                response = requests.post(
                    f"{PAGAMENTO_SERVICE_URL}/payment-codes",
                    json=payment_data,
                    headers={'Content-Type': 'application/json'}
                )
                payment_code = response.json()['payment_code']
                payment_request["payment_code"] = payment_code
            else:
                break
        
        # 7. Verifica se o veículo está reservado
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        assert response.status_code == 200
        vehicle_status = response.json()
        assert vehicle_status['status'] == 'reserved'
        
        # 8. Cleanup - Libera a reserva do veículo
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/release")
        assert response.status_code == 200
        
        # 9. Cleanup - Libera o crédito do cliente
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/{customer_id}/credit/release",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 200
        
        # 10. Se o pagamento foi processado, faz o estorno
        if payment_processed:
            response = requests.post(f"{PAGAMENTO_SERVICE_URL}/payments/{payment_id}/refund")
            assert response.status_code == 200
        
        # 11. Verifica se tudo voltou ao estado original
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        vehicle_final = response.json()
        assert vehicle_final['status'] == 'available'
    
    
    def test_payment_integration_workflow(self):
        """Testa especificamente a integração do serviço de pagamento"""
        # 1. Cria cliente e veículo para o teste
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
        
        # 2. Testa geração de código de pagamento
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
        
        # 3. Verifica se os IDs correspondem
        assert payment_code_data['customer_id'] == customer_id
        assert payment_code_data['vehicle_id'] == vehicle_id
        assert payment_code_data['amount'] == 75000.00
        
        # 4. Testa diferentes métodos de pagamento
        payment_methods = ["pix", "card", "bank_transfer"]
        
        for method in payment_methods:
            # Gera novo código para cada método
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
            
            # Tenta processar (com retry devido ao random)
            max_attempts = 5
            for _ in range(max_attempts):
                response = requests.post(
                    f"{PAGAMENTO_SERVICE_URL}/payments",
                    json=payment_request,
                    headers={'Content-Type': 'application/json'}
                )
                if response.status_code == 201:
                    payment_data_response = response.json()
                    assert payment_data_response['payment_method'] == method
                    break
                elif response.status_code == 400 and "Payment processing failed" in response.json().get('detail', ''):
                    # Gera novo código e tenta novamente
                    response = requests.post(
                        f"{PAGAMENTO_SERVICE_URL}/payment-codes",
                        json=payment_data,
                        headers={'Content-Type': 'application/json'}
                    )
                    payment_code = response.json()['payment_code']
                    payment_request["payment_code"] = payment_code
                else:
                    break
    
    
    def test_microservices_resilience(self):
        """Testa a resiliência dos microsserviços"""
        # Testa se cada serviço continua funcionando independentemente
        # mesmo quando outros serviços estão sendo utilizados intensivamente
        
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
                    time.sleep(0.1)  # Pequena pausa entre requisições
            except Exception as e:
                errors.append(f"{service_name}: {str(e)}")
        
        # Executa testes de stress em paralelo
        threads = [
            threading.Thread(target=stress_test_service, args=('veiculo', VEICULO_SERVICE_URL, '/vehicles')),
            threading.Thread(target=stress_test_service, args=('cliente', CLIENTE_SERVICE_URL, '/customers')),
            threading.Thread(target=stress_test_service, args=('pagamento', PAGAMENTO_SERVICE_URL, '/payments')),
        ]
        
        for thread in threads:
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verifica se não houve erros
        assert len(errors) == 0, f"Erros encontrados: {errors}"
        
        # Verifica se todos os serviços responderam corretamente
        for service_name, status_codes in results.items():
            assert len(status_codes) == 3, f"Serviço {service_name} não completou todas as requisições"
            assert all(status == 200 for status in status_codes), f"Serviço {service_name} teve falhas: {status_codes}"