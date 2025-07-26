.PHONY: help setup setup-backend deploy deploy-sql deploy-app destroy destroy-sql destroy-app dev test stop clean info build up down

# ==============================================================================
# Variáveis de configuração
# ==============================================================================

-include .env

PROJECT_ID  ?= $(shell grep 'project_id' infrastructure/terraform/terraform.tfvars 2>/dev/null | cut -d'"' -f2)
REGION      ?= $(shell grep 'region' infrastructure/terraform/terraform.tfvars 2>/dev/null | cut -d'"' -f2 || echo "southamerica-east1")
ENVIRONMENT ?= $(shell grep 'environment' infrastructure/terraform/terraform.tfvars 2>/dev/null | cut -d'"' -f2 || echo "dev")

# ==============================================================================
# Comandos
# ==============================================================================

help: ## Mostra os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-20s\033[0m %s\n", $$1, $$2}'

setup: ## Configura projeto inicial
	@chmod +x infrastructure/scripts/*.sh
	@./infrastructure/scripts/setup-gcp.sh $(PROJECT_ID)

setup-backend: ## Configura backend remoto
	@chmod +x infrastructure/scripts/setup-backend.sh
	@./infrastructure/scripts/setup-backend.sh

deploy: ## Deploy completo
	@chmod +x infrastructure/scripts/deploy.sh
	@./infrastructure/scripts/deploy.sh

deploy-sql: ## Deploy apenas SQL
	@cd infrastructure/terraform && \
	terraform apply -target=module.sql -auto-approve \
		-var="project_id=$(PROJECT_ID)" \
		-var="region=$(REGION)" \
		-var="environment=$(ENVIRONMENT)" \
		-var="db_password=$(shell grep 'db_password' infrastructure/terraform/terraform.tfvars | cut -d'"' -f2)"

deploy-app: ## Deploy apenas aplicações
	@chmod +x infrastructure/scripts/deploy-code.sh
	@./infrastructure/scripts/deploy-code.sh

destroy: ## Destroi toda a infraestrutura
	@cd infrastructure/terraform && \
	terraform destroy -auto-approve \
		-var="project_id=$(PROJECT_ID)" \
		-var="region=$(REGION)" \
		-var="environment=$(ENVIRONMENT)" \
		-var="db_password=dummy" \
		-var="use_real_images=false"

destroy-sql: ## Destroi apenas SQL
	@cd infrastructure/terraform && \
	terraform destroy -target=module.sql -auto-approve \
		-var="project_id=$(PROJECT_ID)" \
		-var="region=$(REGION)" \
		-var="environment=$(ENVIRONMENT)" \
		-var="db_password=dummy"

destroy-app: ## Destroi apenas aplicações
	@cd infrastructure/terraform && \
	terraform destroy -target=module.app -auto-approve \
		-var="project_id=$(PROJECT_ID)" \
		-var="region=$(REGION)" \
		-var="environment=$(ENVIRONMENT)" \
		-var="use_real_images=false"

# ==============================================================================
# Desenvolvimento local
# ==============================================================================

build: ## Constrói as imagens localmente
	@docker-compose build

up: ## Inicia os serviços localmente
	@docker-compose up -d cliente-service veiculo-service pagamento-service

down: ## Para os serviços locais
	@docker-compose down

dev: up ## Modo desenvolvimento local com logs
	@echo "🚀 Iniciando modo desenvolvimento..."
	@echo "📋 Serviços disponíveis:"
	@echo "   Cliente:   http://localhost:8080"
	@echo "   Veículo:   http://localhost:8081"
	@echo "   Pagamento: http://localhost:8082"
	@echo ""
	@echo "📝 Logs em tempo real (Ctrl+C para sair):"
	@docker-compose logs -f cliente-service veiculo-service pagamento-service

test: up ## Executa os testes localmente
	@echo "⏳ Aguardando serviços..."
	@until curl -sf http://localhost:8080/health >/dev/null 2>&1; do sleep 2; done
	@until curl -sf http://localhost:8081/health >/dev/null 2>&1; do sleep 2; done
	@until curl -sf http://localhost:8082/health >/dev/null 2>&1; do sleep 2; done
	@docker-compose run --rm tests

stop: ## Para desenvolvimento local
	@docker-compose down

clean: ## Limpa recursos locais
	@docker-compose down -v
	@docker system prune -f

info: ## Mostra informações do projeto
	@echo "📋 Informações do projeto:"
	@echo "   Project ID:   $(PROJECT_ID)"
	@echo "   Region:       $(REGION)"
	@echo "   Environment:  $(ENVIRONMENT)"
