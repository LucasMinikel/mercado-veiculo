#!/bin/bash

set -e

# Cores para a saída
VERMELHO='\033[0;31m'
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
AZUL='\033[0;34m'
NC='\033[0m'

echo -e "${VERDE}🚀 Iniciando o deploy com correção de DNS...${NC}"

# Obter diretório atual e carregar configuração
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/infrastructure/terraform"

cd "$PROJECT_ROOT"

# ETAPA 0: Executar correção de DNS
echo -e "${VERDE}🔧 ETAPA 0: Corrigindo problemas de DNS...${NC}"
chmod +x infrastructure/scripts/fix-dns.sh
source infrastructure/scripts/fix-dns.sh

# Carregar configuração do projeto
if [ -f "$TERRAFORM_DIR/terraform.tfvars" ]; then
    PROJECT_ID=$(grep 'project_id' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2)
    REGION=$(grep 'region' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2 || echo "southamerica-east1")
else
    PROJECT_ID=${PROJECT_ID:-}
    REGION=${REGION:-"southamerica-east1"}
fi

if [ -z "$PROJECT_ID" ]; then
    echo -e "${VERMELHO}❌ PROJECT_ID não encontrado${NC}"
    exit 1
fi

echo -e "${AZUL}📋 Projeto: $PROJECT_ID${NC}"
echo -e "${AZUL}🌍 Região: $REGION${NC}"

# Definir projeto atual no gcloud
gcloud config set project $PROJECT_ID

# Garantir que as APIs estejam habilitadas via gcloud
echo -e "${VERDE}🔌 Garantindo que as APIs estejam habilitadas...${NC}"
timeout 180 gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    iam.googleapis.com \
    workflows.googleapis.com \
    --project=$PROJECT_ID \
    --quiet

echo -e "${VERDE}⏳ Aguardando APIs ficarem prontas...${NC}"
sleep 45

# ETAPA 1: Terraform - Deploy da infraestrutura com imagens falsas
echo -e "${VERDE}🏗️  ETAPA 1: Fazendo deploy da infraestrutura...${NC}"
cd "$TERRAFORM_DIR"

# Limpar planos e locks antigos
rm -f tfplan
rm -f .terraform.lock.hcl

# Inicializar terraform com timeout
timeout 300 terraform init -input=false

# Validar configuração
terraform validate

# Criar plano do terraform
timeout 600 terraform plan -input=false -out=tfplan \
    -var="project_id=$PROJECT_ID" \
    -var="region=$REGION" \
    -var="use_real_images=false"

# Aplicar plano do terraform
timeout 900 terraform apply -input=false tfplan
rm -f tfplan

# Obter URL do repositório do terraform
REPO_URL=$(terraform output -raw artifact_registry_repository_url)

# ETAPA 2: Construir e enviar imagens Docker
echo -e "${VERDE}🐳 ETAPA 2: Construindo e enviando imagens Docker...${NC}"

# Configurar autenticação do Docker
timeout 60 gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

# Construir e enviar cliente-service
echo -e "${AMARELO}🔨 Construindo cliente-service...${NC}"
cd "$PROJECT_ROOT/services/cliente-service"
docker build -t "${REPO_URL}/cliente-service:latest" .
docker push "${REPO_URL}/cliente-service:latest"

# Construir e enviar veiculo-service
echo -e "${AMARELO}🔨 Construindo veiculo-service...${NC}"
cd "$PROJECT_ROOT/services/veiculo-service"
docker build -t "${REPO_URL}/veiculo-service:latest" .
docker push "${REPO_URL}/veiculo-service:latest"

# Construir e enviar pagamento-service
echo -e "${AMARELO}🔨 Construindo pagamento-service...${NC}"
cd "$PROJECT_ROOT/services/pagamento-service"
docker build -t "${REPO_URL}/pagamento-service:latest" .
docker push "${REPO_URL}/pagamento-service:latest"

# ETAPA 3: Atualizar serviços Cloud Run com imagens reais
echo -e "${VERDE}🔄 ETAPA 3: Atualizando serviços Cloud Run com imagens reais...${NC}"
cd "$TERRAFORM_DIR"

timeout 600 terraform plan -input=false -out=tfplan \
    -var="project_id=$PROJECT_ID" \
    -var="region=$REGION" \
    -var="cliente_image=${REPO_URL}/cliente-service:latest" \
    -var="veiculo_image=${REPO_URL}/veiculo-service:latest" \
    -var="pagamento_image=${REPO_URL}/pagamento-service:latest" \
    -var="use_real_images=true"

timeout 900 terraform apply -input=false tfplan
rm -f tfplan

# Obter URLs dos serviços
echo -e "${VERDE}📋 Obtendo informações dos serviços...${NC}"
CLIENTE_URL=$(terraform output -raw cliente_service_url)
VEICULO_URL=$(terraform output -raw veiculo_service_url)
PAGAMENTO_URL=$(terraform output -raw pagamento_service_url)

echo -e "${VERDE}✅ Deploy concluído com sucesso!${NC}"
echo -e "${AMARELO}🌐 URLs dos serviços:${NC}"
echo -e "   Cliente Service: $CLIENTE_URL"
echo -e "   Veiculo Service: $VEICULO_URL"
echo -e "   Pagamento Service: $PAGAMENTO_URL"
echo -e ""
echo -e "${AMARELO}🔍 URLs para Health Check:${NC}"
echo -e "   Cliente Health: $CLIENTE_URL/health"
echo -e "   Veiculo Health: $VEICULO_URL/health"
echo -e "   Pagamento Health: $PAGAMENTO_URL/health"

# Health check simples
echo -e "${VERDE}🧪 Testando endpoints de saúde...${NC}"
sleep 30

if timeout 30 curl -f -s "$CLIENTE_URL/health" > /dev/null; then
    echo -e "${VERDE}✅ Cliente service saudável${NC}"
else
    echo -e "${AMARELO}⚠️  Cliente service pode precisar de mais alguns minutos${NC}"
fi

if timeout 30 curl -f -s "$VEICULO_URL/health" > /dev/null; then
    echo -e "${VERDE}✅ Veiculo service saudável${NC}"
else
    echo -e "${AMARELO}⚠️  Veiculo service pode precisar de mais alguns minutos${NC}"
fi

if timeout 30 curl -f -s "$PAGAMENTO_URL/health" > /dev/null; then
    echo -e "${VERDE}✅ Pagamento service saudável${NC}"
else
    echo -e "${AMARELO}⚠️  Pagamento service pode precisar de mais alguns minutos${NC}"
fi

echo -e "${VERDE}🎉 Processo de deploy concluído!${NC}"
