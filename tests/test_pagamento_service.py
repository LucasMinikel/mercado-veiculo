import requests
import time
import uuid
import threading

PAGAMENTO_SERVICE_URL = "http://pagamento-service:8080"


class TestPagamentoService:
    def generate_unique_payment_data(self):
        unique_id = int(str(uuid.uuid4().int)[:8])
        return {
            "customer_id": unique_id % 1000 + 1,
            "vehicle_id": unique_id % 100 + 1,
            "amount": 50000.00 + (unique_id % 50000)
        }

    def test_health_check(self):
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/health")

        assert response.status_code == 200
        data = response.json()
        assert data['status'] == 'healthy'
        assert data['service'] == 'payment-service'
        assert data['version'] == '1.0.0'
        assert 'timestamp' in data

    def test_generate_payment_code_success(self):
        payment_data = self.generate_unique_payment_data()

        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 201
        data = response.json()

        required_fields = ['payment_code', 'customer_id',
                           'vehicle_id', 'amount', 'expires_at', 'status', 'created_at']
        for field in required_fields:
            assert field in data

        assert data['customer_id'] == payment_data['customer_id']
        assert data['vehicle_id'] == payment_data['vehicle_id']
        assert data['amount'] == payment_data['amount']
        assert data['status'] == 'pending'
        assert data['payment_code'].startswith('PAY-')
        assert len(data['payment_code']) == 12

    def test_generate_payment_code_validation_errors(self):
        incomplete_data = {
            "customer_id": 1,
            "amount": 50000.00
        }

        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=incomplete_data,
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 422

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
        payment_data = self.generate_unique_payment_data()

        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        payment_code = response.json()['payment_code']

        response = requests.get(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes/{payment_code}")

        assert response.status_code == 200
        data = response.json()
        assert data['payment_code'] == payment_code
        assert data['customer_id'] == payment_data['customer_id']
        assert data['vehicle_id'] == payment_data['vehicle_id']
        assert data['amount'] == payment_data['amount']
        assert data['status'] == 'pending'

    def test_get_nonexistent_payment_code(self):
        response = requests.get(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes/PAY-INVALIDNONEXIST")

        assert response.status_code == 404
        data = response.json()
        assert data['detail'] == 'Payment code not found'

    def test_process_payment_success(self):
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

        assert processed_successfully, f"Failed to process payment after {max_attempts} attempts: {response.json()}"

        data = response.json()
        required_fields = ['payment_id', 'payment_code', 'customer_id',
                           'vehicle_id', 'amount', 'payment_method', 'status', 'processed_at']
        for field in required_fields:
            assert field in data

        assert data['payment_code'] == payment_code
        assert data['payment_method'] == 'pix'
        assert data['status'] == 'completed'
        assert data['payment_id'].startswith('TXN-')

    def test_process_payment_with_invalid_code(self):
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

        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payments",
            json=payment_request,
            headers={'Content-Type': 'application/json'}
        )

        assert response.status_code == 400
        data = response.json()
        assert data['detail'] == 'Payment code already processed or expired'

    def test_get_payments_list(self):
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

        if payment_id:
            response = requests.post(
                f"{PAGAMENTO_SERVICE_URL}/payments/{payment_id}/refund")

            assert response.status_code == 200
            data = response.json()
            assert data['payment_id'] == payment_id
            assert data['status'] == 'refunded'
            assert 'refunded_at' in data

    def test_refund_nonexistent_payment(self):
        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payments/TXN-INVALIDNONEXIST/refund")

        assert response.status_code == 404
        data = response.json()
        assert data['detail'] == 'Payment not found'

    def test_payment_workflow_complete(self):
        payment_data = self.generate_unique_payment_data()

        response = requests.post(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes",
            json=payment_data,
            headers={'Content-Type': 'application/json'}
        )
        assert response.status_code == 201
        payment_code = response.json()['payment_code']

        response = requests.get(
            f"{PAGAMENTO_SERVICE_URL}/payment-codes/{payment_code}")
        assert response.status_code == 200
        assert response.json()['status'] == 'pending'

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

        if payment_id:
            response = requests.get(
                f"{PAGAMENTO_SERVICE_URL}/payment-codes/{payment_code}")
            assert response.status_code == 200
            assert response.json()['status'] == 'used'

            response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payments")
            assert response.status_code == 200
            payments = response.json()['payments']
            payment_ids = [p['payment_id'] for p in payments]
            assert payment_id in payment_ids

    def test_concurrent_payment_generation(self):
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

        assert len(errors) == 0, f"Erros encontrados: {errors}"

        assert all(status == 201 for status in results)
        assert len(results) == 5

    def test_api_response_time(self):
        start_time = time.time()
        response = requests.get(f"{PAGAMENTO_SERVICE_URL}/payments")
        end_time = time.time()

        response_time = end_time - start_time
        assert response_time < 2.0
        assert response.status_code == 200
