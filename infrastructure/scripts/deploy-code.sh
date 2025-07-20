#!/bin/bash

set -e

# Cores para a saída
VERMELHO='\033[0;31m'
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
AZUL='\033[0;34m'
NC='\033[0m'

echo -e "${VERDE}🚀 Iniciando deploy apenas do código...${NC}"

# Obter diretório atual e configuração
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/infrastructure/terraform"

cd "$PROJECT_ROOT"

if [ -f "$TERRAFORM_DIR/terraform.tfvars" ]; then
    PROJECT_ID=$(grep 'project_id' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2)
    REGION=$(grep 'region' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2 || echo "southamerica-east1")
else
    echo -e "${VERMELHO}❌ terraform.tfvars não encontrado. Execute 'make setup' primeiro${NC}"
    exit 1
fi

if [ -z "$PROJECT_ID" ]; then
    echo -e "${VERMELHO}❌ PROJECT_ID não encontrado${NC}"
    exit 1
fi

echo -e "${AZUL}📋 Projeto: $PROJECT_ID${NC}"
echo -e "${AZUL}🌍 Região: $REGION${NC}"

gcloud config set project $PROJECT_ID

cd "$TERRAFORM_DIR"
if [ ! -f "terraform.tfstate" ]; then
    echo -e "${VERMELHO}❌ Infraestrutura não implantada. Execute 'make deploy' primeiro${NC}"
    exit 1
fi

REPO_URL=$(terraform output -raw artifact_registry_repository_url 2>/dev/null)
if [ -z "$REPO_URL" ]; then
    echo -e "${VERMELHO}❌ Não foi possível obter a URL do repositório${NC}"
    exit 1
fi

echo -e "${AZUL}📦 Repositório: $REPO_URL${NC}"

# Configurar Docker
echo -e "${VERDE}🐳 Configurando autenticação do Docker...${NC}"
gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Construir e enviar cliente-service
echo -e "${VERDE}🔨 Construindo e enviando cliente-service...${NC}"
cd "$PROJECT_ROOT/services/cliente-service"
docker build -t "${REPO_URL}/cliente-service:latest" .
docker push "${REPO_URL}/cliente-service:latest"

# Construir e enviar veiculo-service
echo -e "${VERDE}🔨 Construindo e enviando veiculo-service...${NC}"
cd "$PROJECT_ROOT/services/veiculo-service"
docker build -t "${REPO_URL}/veiculo-service:latest" .
docker push "${REPO_URL}/veiculo-service:latest"

# Construir e enviar pagamento-service
echo -e "${VERDE}🔨 Construindo e enviando pagamento-service...${NC}"
cd "$PROJECT_ROOT/services/pagamento-service"
docker build -t "${REPO_URL}/pagamento-service:latest" .
docker push "${REPO_URL}/pagamento-service:latest"

# Atualizar serviços Cloud Run diretamente
echo -e "${VERDE}🔄 Atualizando serviços Cloud Run...${NC}"

echo -e "${AMARELO}📱 Atualizando cliente-service...${NC}"
gcloud run services update cliente-service \
    --image="${REPO_URL}/cliente-service:latest" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --quiet

echo -e "${AMARELO}📱 Atualizando veiculo-service...${NC}"
gcloud run services update veiculo-service \
    --image="${REPO_URL}/veiculo-service:latest" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --quiet

echo -e "${AMARELO}📱 Atualizando pagamento-service...${NC}"
gcloud run services update pagamento-service \
    --image="${REPO_URL}/pagamento-service:latest" \
    --region="$REGION" \
    --project="$PROJECT_ID" \
    --quiet

# URLs
echo -e "${VERDE}📋 Obtendo URLs dos serviços...${NC}"
cd "$TERRAFORM_DIR"
CLIENTE_URL=$(terraform output -raw cliente_service_url 2>/dev/null)
VEICULO_URL=$(terraform output -raw veiculo_service_url 2>/dev/null)
PAGAMENTO_URL=$(terraform output -raw pagamento_service_url 2>/dev/null)

echo -e "${VERDE}✅ Deploy do código concluído com sucesso!${NC}"
echo -e "${AMARELO}🌐 URLs dos serviços:${NC}"
echo -e "   Cliente: $CLIENTE_URL"
echo -e "   Veiculo: $VEICULO_URL"
echo -e "   Pagamento: $PAGAMENTO_URL"
echo -e ""
echo -e "${AMARELO}🔍 URLs para Health Check:${NC}"
echo -e "   Cliente: $CLIENTE_URL/health"
echo -e "   Veiculo: $VEICULO_URL/health"
echo -e "   Pagamento: $PAGAMENTO_URL/health"

echo -e "${VERDE}🧪 Testando endpoints de saúde...${NC}"
sleep 15

if timeout 30 curl -f -s "$CLIENTE_URL/health" > /dev/null; then
    echo -e "${VERDE}✅ Cliente saudável${NC}"
else
    echo -e "${AMARELO}⚠️  Cliente em atualização... (pode levar alguns instantes)${NC}"
fi

if timeout 30 curl -f -s "$VEICULO_URL/health" > /dev/null; then
    echo -e "${VERDE}✅ Veiculo saudável${NC}"
else
    echo -e "${AMARELO}⚠️  Veiculo em atualização... (pode levar alguns instantes)${NC}"
fi

if timeout 30 curl -f -s "$PAGAMENTO_URL/health" > /dev/null; then
    echo -e "${VERDE}✅ Pagamento saudável${NC}"
else
    echo -e "${AMARELO}⚠️  Pagamento em atualização... (pode levar alguns instantes)${NC}"
fi

echo -e "${VERDE}🎉 Deploy do código concluído!${NC}"
echo -e "${AZUL}💡 Dica: os serviços podem levar 1–2 minutos para atualizar completamente${NC}"