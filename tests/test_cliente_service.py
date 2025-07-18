import requests
import time
import uuid

# Configurações do teste
CLIENTE_SERVICE_URL = "http://cliente-service:8080"

class TestClienteService:
    
    def setup_method(self):
        """Aguarda os serviços ficarem prontos antes de cada teste"""
        self.wait_for_service(CLIENTE_SERVICE_URL)
    
    def wait_for_service(self, url, timeout=30):
        """Aguarda o serviço ficar disponível"""
        start_time = time.time()
        while time.time() - start_time < timeout:
            try:
                response = requests.get(f"{url}/health", timeout=2)
                if response.status_code == 200:
                    return
            except requests.RequestException:
                pass
            time.sleep(1)
        raise Exception(f"Serviço {url} não ficou disponível em {timeout} segundos")
    
    def generate_unique_document(self):
        """Gera um documento único para evitar conflitos"""
        # Usa UUID para garantir unicidade
        unique_id = str(uuid.uuid4()).replace('-', '')[:11]
        return unique_id
    
    
    def test_health_check(self):
        """Testa o endpoint de health check"""
        response = requests.get(f"{CLIENTE_SERVICE_URL}/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'customer-service'
        assert data['version'] == '1.0.0'
        assert 'timestamp' in data
    
    
    def test_get_customers_success(self):
        """Testa a listagem de clientes"""
        response = requests.get(f"{CLIENTE_SERVICE_URL}/customers")
        
        assert response.status_code == 200
        data = response.json()
        assert 'customers' in data
        assert 'total' in data
        assert 'timestamp' in data
        assert isinstance(data['customers'], list)
        assert data['total'] >= 0
    
    
    def test_get_customers_structure(self):
        """Testa a estrutura dos dados dos clientes"""
        response = requests.get(f"{CLIENTE_SERVICE_URL}/customers")
        data = response.json()
        
        if data['customers']:
            customer = data['customers'][0]
            required_fields = ['id', 'name', 'email', 'phone', 'document', 'credit_limit', 'available_credit', 'status', 'created_at']
            for field in required_fields:
                assert field in customer
            
            # Verifica se o documento está mascarado
            assert '*' in customer['document']
            assert len(customer['document']) == 11  # 7 asteriscos + 4 dígitos
    
    
    def test_create_customer_success(self):
        """Testa a criação de um novo cliente"""
        unique_doc = self.generate_unique_document()
        unique_email = f"test_{unique_doc}@email.com"
        unique_id = str(uuid.uuid4())[:8]
        
        new_customer = {
            "name": f"Maria Silva Teste {unique_id}",
            "email": unique_email,
            "phone": "11987654321",
            "document": unique_doc,
            "credit_limit": 120000.00
        }
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=new_customer,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data['name'] == new_customer['name']
        assert data['email'] == new_customer['email']
        assert data['phone'] == new_customer['phone']
        assert data['credit_limit'] == new_customer['credit_limit']
        assert data['available_credit'] == new_customer['credit_limit']
        assert data['status'] == 'active'
        assert 'id' in data
        assert 'created_at' in data
        
        # Verifica se o documento está mascarado na resposta
        assert '*' in data['document']
        assert data['document'].endswith(unique_doc[-4:])  # Últimos 4 dígitos
    
    
    def test_create_customer_validation_errors(self):
        """Testa a criação de cliente com dados inválidos"""
        # Teste com campos obrigatórios faltando
        incomplete_customer = {
            "name": "João Silva",
            "email": "joao@email.com"
            # Faltando phone e document
        }
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=incomplete_customer,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert 'detail' in data
        
        # Teste com documento inválido (muito curto)
        invalid_document_customer = {
            "name": "João Silva",
            "email": "joao@email.com",
            "phone": "11999999999",
            "document": "123",  # Muito curto
            "credit_limit": 100000.00
        }
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=invalid_document_customer,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422
        
        # Teste com limite de crédito negativo
        negative_credit_customer = {
            "name": "João Silva",
            "email": "joao@email.com",
            "phone": "11999999999",
            "document": "12345678901",
            "credit_limit": -1000.00  # Negativo
        }
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=negative_credit_customer,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422
    
    
    def test_create_duplicate_customer(self):
        """Testa a criação de cliente duplicado"""
        unique_doc = self.generate_unique_document()
        unique_email = f"duplicado_{unique_doc}@email.com"
        unique_id = str(uuid.uuid4())[:8]
        
        customer_data = {
            "name": f"Cliente Duplicado {unique_id}",
            "email": unique_email,
            "phone": "11999999999",
            "document": unique_doc,
            "credit_limit": 100000.00
        }
        
        # Cria o primeiro cliente
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=customer_data,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 201
        
        # Tenta criar o mesmo cliente novamente
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=customer_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 409  # Conflict
        data = response.json()
        assert data['detail'] == 'Customer already exists'
    
    
    def test_reserve_credit_success(self):
        """Testa a reserva de crédito"""
        # Cria um cliente primeiro
        unique_doc = self.generate_unique_document()
        unique_email = f"credit_{unique_doc}@email.com"
        unique_id = str(uuid.uuid4())[:8]
        
        new_customer = {
            "name": f"Cliente Crédito {unique_id}",
            "email": unique_email,
            "phone": "11999999999",
            "document": unique_doc,
            "credit_limit": 50000.00
        }
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=new_customer,
            headers={'Content-Type': 'application/json'}
        )
        customer_id = response.json()['id']
        
        # Reserva crédito
        credit_data = {"amount": 10000.00}
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/{customer_id}/credit/reserve",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['message'] == 'Credit reserved successfully'
        assert data['customer_id'] == customer_id
        assert data['amount'] == 10000.00
        assert 'available_credit' in data
    
    
    def test_reserve_credit_insufficient(self):
        """Testa reserva de crédito insuficiente"""
        # Cria um cliente com limite baixo
        unique_doc = self.generate_unique_document()
        unique_email = f"limite_{unique_doc}@email.com"
        unique_id = str(uuid.uuid4())[:8]
        
        new_customer = {
            "name": f"Cliente Limite Baixo {unique_id}",
            "email": unique_email,
            "phone": "11999999999",
            "document": unique_doc,
            "credit_limit": 1000.00
        }
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=new_customer,
            headers={'Content-Type': 'application/json'}
        )
        customer_id = response.json()['id']
        
        # Tenta reservar mais crédito do que disponível
        credit_data = {"amount": 2000.00}
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/{customer_id}/credit/reserve",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 400
        data = response.json()
        assert data['detail'] == 'Insufficient credit'
    
    
    def test_reserve_credit_invalid_amount(self):
        """Testa reserva com valor inválido"""
        # Cria um cliente primeiro
        unique_doc = self.generate_unique_document()
        unique_email = f"invalid_{unique_doc}@email.com"
        unique_id = str(uuid.uuid4())[:8]
        
        new_customer = {
            "name": f"Cliente Invalid {unique_id}",
            "email": unique_email,
            "phone": "11999999999",
            "document": unique_doc,
            "credit_limit": 50000.00
        }
        
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers",
            json=new_customer,
            headers={'Content-Type': 'application/json'}
        )
        customer_id = response.json()['id']
        
        # Tenta reservar valor negativo
        credit_data = {"amount": -1000.00}
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/{customer_id}/credit/reserve",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422  # Validation error
        
        # Tenta reservar valor zero
        credit_data = {"amount": 0.00}
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/{customer_id}/credit/reserve",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422
    
    
    def test_release_credit_success(self):
        """Testa a liberação de crédito"""
        # Cria um cliente
        unique_doc = self.generate_unique_document()
        unique_email = f"release_{unique_doc}@email.com"
        unique_id = str(uuid.uuid4())[:8]
        
        new_customer = {
            "name": f"Cliente Release {unique_id}",
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
        customer_id = response.json()['id']
        
        # Reserva crédito primeiro
        credit_data = {"amount": 10000.00}
        requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/{customer_id}/credit/reserve",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        
        # Libera o crédito
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/{customer_id}/credit/release",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 200
        data = response.json()
        assert data['message'] == 'Credit released successfully'
        assert data['customer_id'] == customer_id
        assert data['amount'] == 10000.00
        assert data['available_credit'] == 100000.00  # Voltou ao limite original
    
    
    def test_customer_not_found(self):
        """Testa operações com cliente inexistente"""
        # Tenta reservar crédito para cliente inexistente
        credit_data = {"amount": 1000.00}
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/999/credit/reserve",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert data['detail'] == 'Customer not found'
        
        # Tenta liberar crédito para cliente inexistente
        response = requests.post(
            f"{CLIENTE_SERVICE_URL}/customers/999/credit/release",
            json=credit_data,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 404
        data = response.json()
        assert data['detail'] == 'Customer not found'