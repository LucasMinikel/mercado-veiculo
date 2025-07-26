#!/bin/bash

set -e

VERMELHO='\033[0;31m'
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
AZUL='\033[0;34m'
NC='\033[0m'

echo -e "${VERDE}🗄️  Configurando backend remoto do Terraform...${NC}"

if ! command -v gcloud &> /dev/null; then
    echo -e "${VERMELHO}❌ gcloud CLI não está instalado${NC}"
    echo -e "${AMARELO}💡 Instale o Google Cloud SDK: https://cloud.google.com/sdk/docs/install${NC}"
    exit 1
fi

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/infrastructure/terraform"

cd "$PROJECT_ROOT"

if [ -f "$TERRAFORM_DIR/terraform.tfvars" ]; then
    PROJECT_ID=$(grep 'project_id' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2)
    ENVIRONMENT=$(grep 'environment' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2 || echo "dev")
    REGION=$(grep 'region' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2 || echo "southamerica-east1")
else
    echo -e "${VERMELHO}❌ terraform.tfvars não encontrado. Execute 'make setup' primeiro${NC}"
    exit 1
fi

if [ -z "$PROJECT_ID" ]; then
    echo -e "${VERMELHO}❌ PROJECT_ID não encontrado no terraform.tfvars${NC}"
    exit 1
fi

echo -e "${AZUL}📋 Projeto: $PROJECT_ID${NC}"
echo -e "${AZUL}🌍 Região: $REGION${NC}"
echo -e "${AZUL}🏷️  Ambiente: $ENVIRONMENT${NC}"

gcloud config set project $PROJECT_ID

if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
    echo -e "${VERMELHO}❌ Nenhuma conta autenticada encontrada${NC}"
    echo -e "${AMARELO}💡 Execute: gcloud auth login${NC}"
    exit 1
fi

BUCKET_NAME="${PROJECT_ID}-terraform-state"

echo -e "${AZUL}🪣 Bucket: $BUCKET_NAME${NC}"

if gcloud storage buckets describe gs://$BUCKET_NAME &>/dev/null; then
    echo -e "${AMARELO}⚠️  Bucket $BUCKET_NAME já existe${NC}"
else
    echo -e "${VERDE}🔨 Criando bucket $BUCKET_NAME...${NC}"
    
    gcloud services enable storage.googleapis.com --project=$PROJECT_ID --quiet
    
    gcloud storage buckets create gs://$BUCKET_NAME \
        --project=$PROJECT_ID \
        --default-storage-class=STANDARD \
        --location=$REGION \
        --uniform-bucket-level-access \
        --public-access-prevention
    
    gcloud storage buckets update gs://$BUCKET_NAME --versioning
    
    cat > /tmp/lifecycle.json << EOF
{
  "lifecycle": {
    "rule": [
      {
        "action": {"type": "Delete"},
        "condition": {
          "numNewerVersions": 10
        }
      },
      {
        "action": {"type": "Delete"},
        "condition": {
          "age": 90
        }
      }
    ]
  }
}
EOF
    
    gcloud storage buckets update gs://$BUCKET_NAME --lifecycle-file=/tmp/lifecycle.json
    rm -f /tmp/lifecycle.json
    
    echo -e "${VERDE}✅ Bucket criado com sucesso${NC}"
fi

BACKEND_CONFIG_FILE="$TERRAFORM_DIR/backend-${ENVIRONMENT}.hcl"

cat > "$BACKEND_CONFIG_FILE" << EOF
bucket = "$BUCKET_NAME"
prefix = "environments/$ENVIRONMENT"
EOF

echo -e "${VERDE}📝 Arquivo de configuração criado: backend-${ENVIRONMENT}.hcl${NC}"

if ! grep -q "state_bucket_name" "$TERRAFORM_DIR/terraform.tfvars"; then
    echo "" >> "$TERRAFORM_DIR/terraform.tfvars"
    echo "state_bucket_name = "$BUCKET_NAME"" >> "$TERRAFORM_DIR/terraform.tfvars"
    echo -e "${VERDE}📝 Adicionada configuração do bucket ao terraform.tfvars${NC}"
else
    if [[ "$OSTYPE" == "darwin"* ]]; then
        sed -i '' 's/state_bucket_name = .*/state_bucket_name = "'"$BUCKET_NAME"'"/' "$TERRAFORM_DIR/terraform.tfvars"
    else
        sed -i 's/state_bucket_name = .*/state_bucket_name = "'"$BUCKET_NAME"'"/' "$TERRAFORM_DIR/terraform.tfvars"
    fi
    echo -e "${VERDE}📝 Atualizada configuração do bucket no terraform.tfvars${NC}"
fi

cd "$TERRAFORM_DIR"

if [ -f "terraform.tfstate" ]; then
    echo -e "${AMARELO}💾 Fazendo backup do state local...${NC}"
    cp terraform.tfstate "terraform.tfstate.backup.$(date +%Y%m%d_%H%M%S)"
fi

rm -rf .terraform
rm -f .terraform.lock.hcl

if ! command -v terraform &> /dev/null; then
    echo -e "${VERMELHO}❌ Terraform não está instalado${NC}"
    echo -e "${AMARELO}💡 Instale o Terraform: https://developer.hashicorp.com/terraform/downloads${NC}"
    exit 1
fi

echo -e "${VERDE}🔄 Inicializando Terraform com backend remoto...${NC}"
terraform init -backend-config="backend-${ENVIRONMENT}.hcl"

BACKUP_FILE=$(ls terraform.tfstate.backup.* 2>/dev/null | head -1 || echo "")
if [ -n "$BACKUP_FILE" ] && [ -f "$BACKUP_FILE" ]; then
    echo -e "${AMARELO}🔄 State local encontrado. Deseja migrar para o backend remoto? (y/n)${NC}"
    read -p "Migrar state: " migrate_choice
    if [[ "$migrate_choice" =~ ^[Yy]$ ]]; then
        echo -e "${VERDE}🔄 Migrando state local para remoto...${NC}"
        echo "yes" | terraform init -backend-config="backend-${ENVIRONMENT}.hcl" -migrate-state || {
            echo -e "${AMARELO}⚠️  Migração não foi necessária ou já foi feita${NC}"
        }
    fi
fi

echo -e "${VERDE}✅ Backend remoto configurado com sucesso!${NC}"
echo -e "${AMARELO}📋 Informações do backend:${NC}"
echo -e "   Bucket: gs://$BUCKET_NAME"
echo -e "   Prefix: environments/$ENVIRONMENT"
echo -e "   Arquivo de config: backend-${ENVIRONMENT}.hcl"