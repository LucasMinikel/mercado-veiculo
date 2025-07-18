import requests
import time
import threading
import uuid

# Configurações do teste
VEICULO_SERVICE_URL = "http://veiculo-service:8080"

class TestVeiculoService:
    
    def setup_method(self):
        """Aguarda os serviços ficarem prontos antes de cada teste"""
        self.wait_for_service(VEICULO_SERVICE_URL)
    
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
    
    def generate_unique_vehicle_data(self):
        """Gera dados únicos para veículo"""
        unique_id = str(uuid.uuid4())[:8]
        return {
            "brand": f"Test_{unique_id}",
            "model": f"Model_{unique_id}",
            "year": 2023,
            "color": f"Color_{unique_id}",
            "price": 50000.00 + (hash(unique_id) % 50000)  # Preço variável
        }
    
    
    def test_health_check(self):
        """Testa o endpoint de health check"""
        response = requests.get(f"{VEICULO_SERVICE_URL}/health")
        
        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'vehicle-service'
        assert data['version'] == '1.0.0'
        assert 'timestamp' in data
    
    
    def test_get_vehicles_success(self):
        """Testa a listagem de veículos disponíveis"""
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles")
        
        assert response.status_code == 200
        data = response.json()
        assert 'vehicles' in data
        assert 'total' in data
        assert 'timestamp' in data
        assert isinstance(data['vehicles'], list)
        assert data['total'] >= 0
    
    
    def test_get_vehicles_with_filters(self):
        """Testa a listagem de veículos com filtros"""
        # Testa filtro por status
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles?status_filter=available")
        assert response.status_code == 200
        data = response.json()
        
        for vehicle in data['vehicles']:
            assert vehicle['status'] == 'available'
        
        # Testa ordenação por preço
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles?sort_by=price&sort_order=asc")
        assert response.status_code == 200
        data = response.json()
        
        if len(data['vehicles']) > 1:
            prices = [v['price'] for v in data['vehicles']]
            assert prices == sorted(prices)
        
        # Testa ordenação decrescente
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles?sort_by=price&sort_order=desc")
        assert response.status_code == 200
        data = response.json()
        
        if len(data['vehicles']) > 1:
            prices = [v['price'] for v in data['vehicles']]
            assert prices == sorted(prices, reverse=True)
    
    
    def test_get_vehicles_structure(self):
        """Testa a estrutura dos dados dos veículos"""
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles")
        data = response.json()
        
        if data['vehicles']:
            vehicle = data['vehicles'][0]
            required_fields = ['id', 'brand', 'model', 'year', 'color', 'price', 'status', 'created_at']
            for field in required_fields:
                assert field in vehicle
            
            assert isinstance(vehicle['price'], (int, float))
            assert isinstance(vehicle['year'], int)
            assert vehicle['year'] >= 1900
    
    
    def test_get_vehicle_by_id(self):
        """Testa a obtenção de um veículo específico"""
        # Primeiro cria um veículo para garantir que existe
        new_vehicle = self.generate_unique_vehicle_data()
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        vehicle_id = response.json()['id']
        
        # Obtém o veículo específico
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        assert response.status_code == 200
        
        vehicle = response.json()
        assert vehicle['id'] == vehicle_id
        
        required_fields = ['id', 'brand', 'model', 'year', 'color', 'price', 'status', 'created_at']
        for field in required_fields:
            assert field in vehicle
    
    
    def test_get_nonexistent_vehicle(self):
        """Testa a obtenção de um veículo que não existe"""
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/999999")
        assert response.status_code == 404
        
        data = response.json()
        assert 'detail' in data
        assert data['detail'] == 'Vehicle not found'
    
    
    def test_create_vehicle_success(self):
        """Testa a criação de um novo veículo"""
        new_vehicle = self.generate_unique_vehicle_data()
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 201
        data = response.json()
        assert data['brand'] == new_vehicle['brand']
        assert data['model'] == new_vehicle['model']
        assert data['year'] == new_vehicle['year']
        assert data['color'] == new_vehicle['color']
        assert data['price'] == new_vehicle['price']
        assert data['status'] == 'available'
        assert 'id' in data
        assert 'created_at' in data
    
    
    def test_create_vehicle_validation_errors(self):
        """Testa a criação de veículo com dados inválidos"""
        # Teste com campos obrigatórios faltando
        incomplete_vehicle = {
            "brand": "Ford",
            "model": "Focus"
            # Faltando year, color, price
        }
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=incomplete_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422  # FastAPI validation error
        data = response.json()
        assert 'detail' in data
        
        # Teste com ano inválido
        invalid_year_vehicle = {
            "brand": "Ford",
            "model": "Focus",
            "year": 1800,  # Muito antigo
            "color": "Azul",
            "price": 50000.00
        }
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=invalid_year_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422
        
        # Teste com preço negativo
        negative_price_vehicle = {
            "brand": "Ford",
            "model": "Focus",
            "year": 2023,
            "color": "Azul",
            "price": -1000.00  # Preço negativo
        }
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=negative_price_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        
        assert response.status_code == 422
    
    
    def test_reserve_vehicle_success(self):
        """Testa a reserva de um veículo"""
        # Primeiro, cria um veículo para garantir que temos um disponível
        new_vehicle = self.generate_unique_vehicle_data()
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        vehicle_id = response.json()['id']
        
        # Reserva o veículo
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/reserve")
        
        assert response.status_code == 200
        data = response.json()
        assert data['message'] == 'Vehicle reserved successfully'
        assert data['vehicle_id'] == vehicle_id
        assert data['status'] == 'reserved'
        
        # Verifica se o veículo foi realmente reservado
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        vehicle = response.json()
        assert vehicle['status'] == 'reserved'
        assert 'reserved_at' in vehicle
    
    
    def test_reserve_nonexistent_vehicle(self):
        """Testa a reserva de um veículo que não existe"""
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/999999/reserve")
        
        assert response.status_code == 404
        data = response.json()
        assert data['detail'] == 'Vehicle not found'
    
    
    def test_reserve_already_reserved_vehicle(self):
        """Testa a reserva de um veículo já reservado"""
        # Primeiro, cria um veículo
        new_vehicle = self.generate_unique_vehicle_data()
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        vehicle_id = response.json()['id']
        
        # Reserva o veículo pela primeira vez
        requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/reserve")
        
        # Tenta reservar novamente
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/reserve")
        
        assert response.status_code == 400
        data = response.json()
        assert data['detail'] == 'Vehicle not available for reservation'
    
    
    def test_release_vehicle_success(self):
        """Testa a liberação de um veículo reservado"""
        # Primeiro, cria e reserva um veículo
        new_vehicle = self.generate_unique_vehicle_data()
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        vehicle_id = response.json()['id']
        
        # Reserva o veículo
        requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/reserve")
        
        # Libera o veículo
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/release")
        
        assert response.status_code == 200
        data = response.json()
        assert data['message'] == 'Vehicle released successfully'
        assert data['vehicle_id'] == vehicle_id
        assert data['status'] == 'available'
        
        # Verifica se o veículo foi realmente liberado
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        vehicle = response.json()
        assert vehicle['status'] == 'available'
    
    
    def test_release_non_reserved_vehicle(self):
        """Testa a liberação de um veículo que não está reservado"""
        # Cria um veículo disponível
        new_vehicle = self.generate_unique_vehicle_data()
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        vehicle_id = response.json()['id']
        
        # Tenta liberar sem ter reservado
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/release")
        
        assert response.status_code == 400
        data = response.json()
        assert data['detail'] == 'Vehicle is not reserved'
    
    
    def test_delete_vehicle_success(self):
        """Testa a exclusão de um veículo"""
        # Primeiro, cria um veículo
        new_vehicle = self.generate_unique_vehicle_data()
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        vehicle_id = response.json()['id']
        
        # Exclui o veículo
        response = requests.delete(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        assert response.status_code == 204
        
        # Verifica se o veículo foi realmente excluído
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        assert response.status_code == 404
    
    
    def test_delete_nonexistent_vehicle(self):
        """Testa a exclusão de um veículo que não existe"""
        response = requests.delete(f"{VEICULO_SERVICE_URL}/vehicles/999999")
        assert response.status_code == 404
        
        data = response.json()
        assert data['detail'] == 'Vehicle not found'
    
    def test_api_response_time(self):
        """Testa o tempo de resposta da API"""
        start_time = time.time()
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles")
        end_time = time.time()
        
        response_time = end_time - start_time
        assert response_time < 2.0  # Deve responder em menos de 2 segundos
        assert response.status_code == 200
    
    def test_concurrent_requests(self):
        """Testa múltiplas requisições simultâneas"""
        results = []
        errors = []
        
        def make_request():
            try:
                response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles", timeout=5)
                results.append(response.status_code)
            except Exception as e:
                errors.append(str(e))
        
        threads = []
        for i in range(5):
            thread = threading.Thread(target=make_request)
            threads.append(thread)
            thread.start()
        
        for thread in threads:
            thread.join()
        
        # Verifica se não houve erros
        assert len(errors) == 0, f"Erros encontrados: {errors}"
        
        # Todas as requisições devem ter sucesso
        assert all(status == 200 for status in results)
        assert len(results) == 5
    
    def test_vehicle_workflow_complete(self):
        """Testa um fluxo completo de operações com veículo"""
        # 1. Cria um veículo
        new_vehicle = self.generate_unique_vehicle_data()
        
        response = requests.post(
            f"{VEICULO_SERVICE_URL}/vehicles",
            json=new_vehicle,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 201
        vehicle_id = response.json()['id']
        
        # 2. Verifica se está disponível
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        assert response.status_code == 200
        assert response.json()['status'] == 'available'
        
        # 3. Reserva o veículo
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/reserve")
        assert response.status_code == 200
        
        # 4. Verifica se está reservado
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        assert response.status_code == 200
        assert response.json()['status'] == 'reserved'
        
        # 5. Libera a reserva
        response = requests.post(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}/release")
        assert response.status_code == 200
        
        # 6. Verifica se voltou a estar disponível
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        assert response.status_code == 200
        assert response.json()['status'] == 'available'
        
        # 7. Exclui o veículo
        response = requests.delete(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        assert response.status_code == 204
        
        # 8. Verifica se foi excluído
        response = requests.get(f"{VEICULO_SERVICE_URL}/vehicles/{vehicle_id}")
        assert response.status_code == 404