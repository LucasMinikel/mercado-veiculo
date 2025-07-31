#!/bin/bash
set -e

# Cores
VERMELHO='\033[0;31m'
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
AZUL='\033[0;34m'
NC='\033[0m'

echo -e "${VERDE}🚀 Iniciando atualização de código nos serviços...${NC}"

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/infrastructure/terraform"

cd "$TERRAFORM_DIR"

# Se não houver state, falha
if [ ! -d ".terraform" ]; then
    echo -e "${VERMELHO}❌ Infraestrutura não implantada ainda (.terraform ausente)${NC}"
    exit 1
fi

# Obter valores do Terraform ou fallback para o tfvars
PROJECT_ID=$(terraform output -raw project_id 2>/dev/null || grep 'project_id' terraform.tfvars | cut -d'"' -f2)
REGION=$(terraform output -raw region 2>/dev/null || grep 'region' terraform.tfvars | cut -d'"' -f2 || echo "southamerica-east1")
REPO_URL=$(terraform output -raw repository_url 2>/dev/null)

if [ -z "$PROJECT_ID" ] || [ -z "$REGION" ]; then
    echo -e "${VERMELHO}❌ Não foi possível determinar PROJECT_ID ou REGION${NC}"
    exit 1
fi

if [ -z "$REPO_URL" ]; then
    echo -e "${VERMELHO}❌ Não foi possível determinar o repositório da imagem (repository_url)${NC}"
    exit 1
fi

echo -e "${AZUL}📋 Projeto: $PROJECT_ID${NC}"
echo -e "${AZUL}🌍 Região: $REGION${NC}"
echo -e "${AZUL}📦 Repositório: $REPO_URL${NC}"

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

SERVICES=("cliente-service" "veiculo-service" "pagamento-service" "orquestrador")

for service in "${SERVICES[@]}"; do
    SERVICE_DIR="$PROJECT_ROOT/services/$service"
    DOCKERFILE="$SERVICE_DIR/Dockerfile"
    
    if [ -f "$DOCKERFILE" ]; then
        echo -e "${VERDE}🔨 Atualizando $service...${NC}"
        cd "$PROJECT_ROOT"
        docker build -f "$DOCKERFILE" -t "${REPO_URL}/$service:latest" .
        docker push "${REPO_URL}/$service:latest"

        gcloud run services update "$service" \
            --image="${REPO_URL}/$service:latest" \
            --region="$REGION" \
            --project="$PROJECT_ID" \
            --quiet
    else
        echo -e "${AMARELO}⚠️  Dockerfile para $service não encontrado, ignorando...${NC}"
    fi
done

echo -e "${VERDE}✅ Código dos serviços atualizado com sucesso!${NC}"
