# tests/test_pagamento_service.py
import requests
import time
import uuid
import threading

# Configurações do teste
PAGAMENTO_SERVICE_URL = "http://pagamento-service:8080"

class TestPagamentoService:
    # O setup_method e wait_for_service foram removidos e são gerenciados por conftest.py
    
    def generate_unique_payment_data(self):
        """Gera dados únicos para pagamento"""
        unique_id = int(str(uuid.uuid4().int)[:8])  # Converte para int
        return {
            "customer_id": unique_id % 1000 + 1,  # ID do cliente entre 1-1000
            "vehicle_id": unique_id % 100 + 1,    # ID do veículo entre 1-100
            "amount": 50000.00 + (unique_id % 50000)  # Valor variável
        }
    
    def test_health_check(self):
        """Testa o endpoint de health check"""
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'payment-service'
        assert data['version'] == '1.0.0'
        assert 'timestamp' in data
    
    def test_generate_payment_code_success(self):
        """Testa a geração de código de pagamento"""
        payment_data = self.generate_unique_payment_data()
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        data = response.json()
        
        # Verifica estrutura da resposta
        required_fields = ['payment_code', 'customer_id', 'vehicle_id', 'amount', 'expires_at', 'status', 'created_at']
        for field in required_fields:
            assert field in data
        
        assert data['customer_id'] == payment_data['customer_id']
        assert data['vehicle_id'] == payment_data['vehicle_id']
        assert data['amount'] == payment_data['amount']
        assert data['status'] == 'pending'
        assert data['payment_code'].startswith('PAY-')
        assert len(data['payment_code']) == 12  # PAY- + 8 caracteres
    
    def test_generate_payment_code_validation_errors(self):
        """Testa a geração de código com dados inválidos"""
        # Teste com campos obrigatórios faltando
        incomplete_data = {
            "customer_id": 1,
            "amount": 50000.00
            # Faltando vehicle_id
        }
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=incomplete_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422  # FastAPI validation error
        
        # Teste com valor negativo
        negative_amount_data = {
            "customer_id": 1,
            "vehicle_id": 1,
            "amount": -1000.00
        }
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=negative_amount_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422
        
        # Teste com valor zero
        zero_amount_data = {
            "customer_id": 1,
            "vehicle_id": 1,
            "amount": 0.00
        }
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=zero_amount_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422
    
    def test_get_payment_code_success(self):
        """Testa a obtenção de um código de pagamento"""
        # Primeiro gera um código
        payment_data = self.generate_unique_payment_data()
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        payment_code = response.json()['payment_code']
        
        # Obtém o código gerado
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payment-codes/{payment_code}")
        
        assert response.status_code == 200
        data = response.json()
        assert data['payment_code'] == payment_code
        assert data['customer_id'] == payment_data['customer_id']
        assert data['vehicle_id'] == payment_data['vehicle_id']
        assert data['amount'] == payment_data['amount']
        assert data['status'] == 'pending'
    
    def test_get_nonexistent_payment_code(self):
        """Testa a obtenção de um código que não existe"""
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payment-codes/PAY-INVALIDNONEXIST")
        
        assert response.status_code == 404
        data = response.json()
        assert data['detail'] == 'Payment code not found'
    
    def test_process_payment_success(self):
        """Testa o processamento de pagamento"""
        # Primeiro gera um código
        payment_data = self.generate_unique_payment_data()
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        payment_code = response.json()['payment_code']
        
        # Processa o pagamento
        payment_request = {
            "payment_code": payment_code,
            "payment_method": "pix"
        }
        
        # Como há 10% de chance de falha, tentamos algumas vezes
        max_attempts = 5
        processed_successfully = False
        
        for _ in range(max_attempts):
            response = requests.post(
                f"{PAGAMENTO_SERVICE_URL}/payments",
                json=payment_request,
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code == 201:
                processed_successfully = True
                break
            elif response.status_code == 400 and "Payment processing failed" in response.json().get('detail', ''):
                # Se falhou por aleatoriedade, gera um novo código e tenta novamente
                payment_data = self.generate_unique_payment_data()
                response = requests.post(
                    f"{PAGAMENTO_SERVICE_URL}/payment-codes",
                    json=payment_data,
                    headers={'Content-Type': 'application/json'}
                )
                payment_code = response.json()['payment_code']
                payment_request["payment_code"] = payment_code
                time.sleep(0.5) # Pequena pausa antes de re-tentar
            else:
                break # Se falhou por outro motivo, não retenta
        
        # Se conseguiu processar o pagamento
        assert processed_successfully, f"Failed to process payment after {max_attempts} attempts: {response.json()}"
        
        data = response.json()
        required_fields = ['payment_id', 'payment_code', 'customer_id', 'vehicle_id', 'amount', 'payment_method', 'status', 'processed_at']
        for field in required_fields:
            assert field in data
        
        assert data['payment_code'] == payment_code
        assert data['payment_method'] == 'pix'
        assert data['status'] == 'completed'
        assert data['payment_id'].startswith('TXN-')
    
    def test_process_payment_with_invalid_code(self):
        """Testa o processamento com código inválido"""
        payment_request = {
            "payment_code": "PAY-INVALIDCODE",
            "payment_method": "pix"
        }
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payments",
            json=payment_request,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert data['detail'] == 'Payment code not found'
    
    def test_process_payment_already_used(self):
        """Testa o processamento de código já utilizado"""
        # Gera e processa um pagamento
        payment_data = self.generate_unique_payment_data()
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        payment_code = response.json()['payment_code']
        
        payment_request = {
            "payment_code": payment_code,
            "payment_method": "pix"
        }
        
        # Tenta processar até conseguir (devido ao random)
        processed_successfully = False
        max_attempts = 10
        for _ in range(max_attempts):
            response = requests.post(
                f"{PAGAMENTO_SERVICE_URL}/payments",
                json=payment_request,
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code == 201:
                processed_successfully = True
                break
            elif response.status_code == 400 and "Payment processing failed" in response.json().get('detail', ''):
                # Gera novo código e continua tentando
                payment_data = self.generate_unique_payment_data()
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
        
        assert processed_successfully, "Failed to process payment for initial attempt."

        # Se conseguiu processar, tenta usar o mesmo código novamente
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payments",
            json=payment_request,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data['detail'] == 'Payment code already processed or expired'
    
    def test_get_payments_list(self):
        """Testa a listagem de pagamentos"""
        # Cria um pagamento para garantir que a lista não esteja vazia
        payment_data = self.generate_unique_payment_data()
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        payment_code = response.json()['payment_code']
        
        payment_request = {
            "payment_code": payment_code,
            "payment_method": "card"
        }
        
        max_attempts = 5
        for _ in range(max_attempts):
            response = requests.post(
                f"{PAGAMENTO_SERVICE_URL}/payments",
                json=payment_request,
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code == 201:
                break
            elif response.status_code == 400 and "Payment processing failed" in response.json().get('detail', ''):
                payment_data = self.generate_unique_payment_data()
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

        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payments")
        
        assert response.status_code == 200
        data = response.json()
        assert 'payments' in data
        assert 'total' in data
        assert 'timestamp' in data
        assert isinstance(data['payments'], list)
        assert data['total'] >= 0
    
    def test_refund_payment_success(self):
        """Testa o estorno de pagamento"""
        # Primeiro processa um pagamento
        payment_data = self.generate_unique_payment_data()
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        payment_code = response.json()['payment_code']
        
        payment_request = {
            "payment_code": payment_code,
            "payment_method": "pix"
        }
        
        # Tenta processar até conseguir
        payment_id = None
        max_attempts = 10
        processed_successfully = False
        for _ in range(max_attempts):
            response = requests.post(
                f"{PAGAMENTO_SERVICE_URL}/payments",
                json=payment_request,
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code == 201:
                payment_id = response.json()['payment_id']
                processed_successfully = True
                break
            elif response.status_code == 400 and "Payment processing failed" in response.json().get('detail', ''):
                # Gera novo código e continua tentando
                payment_data = self.generate_unique_payment_data()
                response = requests.post(
                    f"{PAGAMENTO_SERVICE_URL}/payment-codes",
                    json=payment_data,
                    headers={'Content-Type': 'application/json'}
                )
                payment_code = response.json()['payment_code']
                payment_request["payment_code"] = payment_code
                time.sleep(0.5)
        
        assert processed_successfully, "Failed to process payment for refund test."

        # Se conseguiu processar, testa o estorno
        if payment_id:
            response = requests.post(f"{PAGAMENTO_SERVICE_URL}/payments/{payment_id}/refund")
            
            assert response.status_code == 200
            data = response.json()
            assert data['payment_id'] == payment_id
            assert data['status'] == 'refunded'
            assert 'refunded_at' in data
    
    def test_refund_nonexistent_payment(self):
        """Testa estorno de pagamento inexistente"""
        response = requests.post(f"{PAGAMENTO_SERVICE_URL}/payments/TXN-INVALIDNONEXIST/refund")
        
        assert response.status_code == 404
        data = response.json()
        assert data['detail'] == 'Payment not found'
    
    def test_payment_workflow_complete(self):
        """Testa um fluxo completo de pagamento"""
        # 1. Gera código de pagamento
        payment_data = self.generate_unique_payment_data()
        
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 201
        payment_code = response.json()['payment_code']
        
        # 2. Verifica se o código foi criado
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payment-codes/{payment_code}")
        assert response.status_code == 200
        assert response.json()['status'] == 'pending'
        
        # 3. Processa o pagamento (com retry devido ao random)
        payment_request = {
            "payment_code": payment_code,
            "payment_method": "card"
        }
        
        payment_id = None
        max_attempts = 10
        processed_successfully = False
        for _ in range(max_attempts):
            response = requests.post(
                f"{PAGAMENTO_SERVICE_URL}/payments",
                json=payment_request,
                headers={'Content-Type': 'application/json'}
            )
            if response.status_code == 201:
                payment_id = response.json()['payment_id']
                processed_successfully = True
                break
            elif response.status_code == 400 and "Payment processing failed" in response.json().get('detail', ''):
                # Gera novo código e continua tentando
                payment_data = self.generate_unique_payment_data()
                response = requests.post(
                    f"{PAGAMENTO_SERVICE_URL}/payment-codes",
                    json=payment_data,
                    headers={'Content-Type': 'application/json'}
                )
                payment_code = response.json()['payment_code']
                payment_request["payment_code"] = payment_code
                time.sleep(0.5)
        
        assert processed_successfully, "Failed to process payment in workflow test."

        # Se conseguiu processar
        if payment_id:
            # 4. Verifica se o código foi marcado como usado
            response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payment-codes/{payment_code}")
            assert response.status_code == 200
            assert response.json()['status'] == 'used'
            
            # 5. Verifica se o pagamento aparece na lista
            response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payments")
            assert response.status_code == 200
            payments = response.json()['payments']
            payment_ids = [p['payment_id'] for p in payments]
            assert payment_id in payment_ids
    
    def test_concurrent_payment_generation(self):
        """Testa geração concorrente de códigos de pagamento"""
        results = []
        errors = []
        
        def generate_payment_code_thread():
            try:
                payment_data = self.generate_unique_payment_data()
                response = requests.post(
                    f"{PAGAMENTO_SERVICE_URL}/payment-codes",
                    json=payment_data,
                    headers={'Content-Type': 'application/json'},
                    timeout=5
                )
                results.append(response.status_code)
            except Exception as e:
                errors.append(str(e))
        
        threads = []
        for _ in range(5):
            thread = threading.Thread(target=generate_payment_code_thread)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verifica se não houve erros
        assert len(errors) == 0, f"Erros encontrados: {errors}"
        
        # Todas as requisições devem ter sucesso
        assert all(status == 201 for status in results)
        assert len(results) == 5
    
    def test_api_response_time(self):
        """Testa o tempo de resposta da API"""
        start_time = time.time()
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payments")
        end_time = time.time()
        
        response_time = end_time - start_time
        assert response_time < 2.0  # Deve responder em menos de 2 segundos
        assert response.status_code == 200