.PHONY: help setup deploy deploy-code destroy health logs clean dev test build push auth-check up down status fix-dns

# Carregar configuração
-include .env

PROJECT_ID ?= $(shell grep 'project_id' infrastructure/terraform/terraform.tfvars 2>/dev/null | cut -d'"' -f2)
REGION     ?= $(shell grep 'region' infrastructure/terraform/terraform.tfvars 2>/dev/null | cut -d'"' -f2 || echo "southamerica-east1")

## Ajuda
help: ## Mostra os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

## DNS
fix-dns: ## Corrige problemas de DNS
	@echo "🔧 Corrigindo problemas de DNS..."
	@chmod +x infrastructure/scripts/fix-dns.sh
	@sudo ./infrastructure/scripts/fix-dns.sh

## Autenticação
auth-check: ## Verifica se a autenticação está configurada
	@echo "🔍 Verificando autenticação..."
	@if [ -z "$$GOOGLE_APPLICATION_CREDENTIALS" ] && [ -z "$$GCLOUD_SERVICE_KEY" ]; then \
		if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then \
			echo "❌ Nenhuma autenticação ativa encontrada."; \
			echo "Execute: make setup PROJECT_ID=your-project-id"; \
			exit 1; \
		fi; \
	fi
	@echo "✅ Autenticação configurada."

setup: ## Configura o projeto GCP rapidamente
	@if [ -z "$(PROJECT_ID)" ] && [ -z "$$PROJECT_ID" ]; then \
		echo "❌ PROJECT_ID é obrigatório. Use: make setup PROJECT_ID=your-project-id"; \
		exit 1; \
	fi
	@chmod +x infrastructure/scripts/*.sh
	@./infrastructure/scripts/setup-gcp.sh $(PROJECT_ID)

## Deploy
deploy: auth-check ## Deploy completo (infraestrutura + código)
	@if [ -z "$(PROJECT_ID)" ]; then \
		echo "❌ Execute 'make setup' primeiro ou defina PROJECT_ID"; \
		exit 1; \
	fi
	@echo "🚀 Iniciando deploy completo..."
	@export PROJECT_ID=$(PROJECT_ID) && export REGION=$(REGION) && \
		chmod +x infrastructure/scripts/deploy.sh && \
		sudo -E ./infrastructure/scripts/deploy.sh

deploy-code: auth-check ## Deploy apenas do código (rápido)
	@if [ -z "$(PROJECT_ID)" ]; then \
		echo "❌ Execute 'make setup' primeiro ou defina PROJECT_ID"; \
		exit 1; \
	fi
	@echo "🚀 Iniciando deploy de código..."
	@export PROJECT_ID=$(PROJECT_ID) && export REGION=$(REGION) && \
		chmod +x infrastructure/scripts/deploy-code.sh && \
		./infrastructure/scripts/deploy-code.sh

destroy: auth-check ## Destrói toda a infraestrutura
	@echo "⚠️  Isso irá destruir TODA a infraestrutura!"
	@read -p "Tem certeza? (yes/no): " confirm && [ "$$confirm" = "yes" ] || { echo "🚫 Cancelado."; exit 1; }
	@cd infrastructure/terraform && terraform destroy -auto-approve \
		-var="project_id=$(PROJECT_ID)" \
		-var="region=$(REGION)" \
		-var="use_real_images=false"

## Monitoramento
health: ## Verifica saúde dos serviços
	@cd infrastructure/terraform && \
	CLIENTE_URL=$$(terraform output -raw cliente_service_url 2>/dev/null) && \
	VEICULO_URL=$$(terraform output -raw veiculo_service_url 2>/dev/null) && \
	PAGAMENTO_URL=$$(terraform output -raw pagamento_service_url 2>/dev/null) && \
	echo "🔍 Verificando saúde dos serviços..." && \
	curl -fsS "$$CLIENTE_URL/health" && echo "✅ Cliente OK" || echo "❌ Cliente com problema"; \
	curl -fsS "$$VEICULO_URL/health" && echo "✅ Veículo OK" || echo "❌ Veículo com problema"; \
	curl -fsS "$$PAGAMENTO_URL/health" && echo "✅ Pagamento OK" || echo "❌ Pagamento com problema"

logs: auth-check ## Mostra logs dos serviços no Cloud Run
	@echo "📋 Logs do Cliente Service:"
	@gcloud run services logs read cliente-service --region=$(REGION) --limit=50 --project=$(PROJECT_ID)
	@echo ""
	@echo "📋 Logs do Veículo Service:"
	@gcloud run services logs read veiculo-service --region=$(REGION) --limit=50 --project=$(PROJECT_ID)
	@echo ""
	@echo "📋 Logs do Pagamento Service:"
	@gcloud run services logs read pagamento-service --region=$(REGION) --limit=50 --project=$(PROJECT_ID)

status: ## Mostra status dos serviços
	@echo "🌐 Status dos serviços:"
	@if [ -f "infrastructure/terraform/terraform.tfvars" ]; then \
		cd infrastructure/terraform && \
		echo "🔗 Cliente Service: $$(terraform output -raw cliente_service_url 2>/dev/null || echo 'Não deployado')" && \
		echo "🔗 Veículo Service: $$(terraform output -raw veiculo_service_url 2>/dev/null || echo 'Não deployado')" && \
		echo "🔗 Pagamento Service: $$(terraform output -raw pagamento_service_url 2>/dev/null || echo 'Não deployado')"; \
	else \
		echo "❌ Serviços não deployados"; \
	fi

## Desenvolvimento local
build: ## Constrói as imagens localmente
	@docker-compose build

up: ## Inicia os serviços localmente
	@docker-compose up -d cliente-service veiculo-service pagamento-service

down: ## Para os serviços locais
	@docker-compose down

test: up ## Executa os testes localmente
	@echo "⏳ Aguardando serviços..."
	@until curl -sf http://localhost:8080/health >/dev/null 2>&1; do sleep 2; done
	@until curl -sf http://localhost:8081/health >/dev/null 2>&1; do sleep 2; done
	@until curl -sf http://localhost:8082/health >/dev/null 2>&1; do sleep 2; done
	@docker-compose run --rm tests

dev: up ## Modo desenvolvimento local com logs
	@echo "🚀 Iniciando modo desenvolvimento..."
	@echo "📋 Serviços disponíveis:"
	@echo "   Cliente:   http://localhost:8080"
	@echo "   Veículo:   http://localhost:8081"
	@echo "   Pagamento: http://localhost:8082"
	@echo ""
	@echo "📝 Logs em tempo real (Ctrl+C para sair):"
	@docker-compose logs -f cliente-service veiculo-service pagamento-service

clean: ## Limpa recursos locais
	@docker-compose down -v
	@docker system prune -f
