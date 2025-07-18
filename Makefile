.PHONY: help build up down test health logs clean dev restart

help: ## Mostra os comandos disponíveis
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "\033[36m%-15s\033[0m %s\n", $$1, $$2}'

build: ## Constrói as imagens
	docker-compose build

up: ## Inicia os serviços
	docker-compose up -d cliente-service veiculo-service

down: ## Para os serviços
	docker-compose down

test: ## Executa os testes (presume que os serviços já estão rodando)
	@echo "Aguardando serviços estarem prontos..."
	@until curl -sf http://localhost:8080/health >/dev/null; do echo "⏳ Cliente aguardando..."; sleep 2; done
	@until curl -sf http://localhost:8081/health >/dev/null; do echo "⏳ Veículo aguardando..."; sleep 2; done
	docker-compose run --rm tests

health: ## Verifica saúde dos serviços
	@curl -f http://localhost:8080/health && echo "✅ Cliente OK" || echo "❌ Cliente com problema"
	@curl -f http://localhost:8081/health && echo "✅ Veículo OK" || echo "❌ Veículo com problema"

logs: ## Mostra logs dos serviços
	docker-compose logs -f cliente-service veiculo-service

clean: ## Para e remove containers/volumes
	docker-compose down -v
	docker system prune -f

dev: up logs ## Modo desenvolvimento

restart: down up ## Reinicia os serviços
