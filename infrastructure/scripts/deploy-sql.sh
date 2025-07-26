#!/bin/bash

set -e

# Cores para a saída
VERMELHO='\033[0;31m'
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
AZUL='\033[0;34m'
NC='\033[0m'

echo -e "${VERDE}🗄️  Iniciando deploy do Cloud SQL...${NC}"

# Obter diretório atual e configuração
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
SQL_DIR="$PROJECT_ROOT/infrastructure/terraform/sql"

cd "$PROJECT_ROOT"

if [ -f "$SQL_DIR/terraform.tfvars" ]; then
    PROJECT_ID=$(grep 'project_id' "$SQL_DIR/terraform.tfvars" | cut -d'"' -f2)
    REGION=$(grep 'region' "$SQL_DIR/terraform.tfvars" | cut -d'"' -f2 || echo "southamerica-east1")
    ENVIRONMENT=$(grep 'environment' "$SQL_DIR/terraform.tfvars" | cut -d'"' -f2 || echo "dev")
    DB_PASSWORD=$(grep 'db_password' "$SQL_DIR/terraform.tfvars" | cut -d'"' -f2 2>/dev/null || echo "")
else
    echo -e "${VERMELHO}❌ terraform.tfvars não encontrado no módulo SQL. Execute 'make setup' primeiro${NC}"
    exit 1
fi

if [ -z "$PROJECT_ID" ]; then
    echo -e "${VERMELHO}❌ PROJECT_ID não encontrado${NC}"
    exit 1
fi

# Verificar se a senha do banco existe
if [ -z "$DB_PASSWORD" ]; then
    echo -e "${AMARELO}🔐 Senha do banco de dados não encontrada${NC}"
    echo -e "${AMARELO}Por favor, defina uma senha para o banco de dados PostgreSQL:${NC}"
    read -s -p "Senha do DB: " DB_PASSWORD
    echo ""
    
    if [ -z "$DB_PASSWORD" ]; then
        echo -e "${VERMELHO}❌ Senha do banco de dados é obrigatória${NC}"
        exit 1
    fi
    
    echo "" >> "$SQL_DIR/terraform.tfvars"
    echo "db_password = "$DB_PASSWORD"" >> "$SQL_DIR/terraform.tfvars"
fi

echo -e "${AZUL}📋 Projeto: $PROJECT_ID${NC}"
echo -e "${AZUL}🌍 Região: $REGION${NC}"
echo -e "${AZUL}🏷️  Ambiente: $ENVIRONMENT${NC}"

gcloud config set project $PROJECT_ID

# Habilitar APIs necessárias
echo -e "${VERDE}🔌 Garantindo que as APIs estejam habilitadas...${NC}"
gcloud services enable \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    --project=$PROJECT_ID \
    --quiet

cd "$SQL_DIR"

# Verificar backend
BACKEND_CONFIG_FILE="backend-sql-${ENVIRONMENT}.hcl"
if [ ! -f "$BACKEND_CONFIG_FILE" ]; then
    echo -e "${AMARELO}⚠️  Backend SQL não configurado. Configurando...${NC}"
    # Criar arquivo de backend para SQL
    BUCKET_NAME="${PROJECT_ID}-terraform-state"
    cat > "$BACKEND_CONFIG_FILE" << EOF
bucket = "$BUCKET_NAME"
prefix = "sql/$ENVIRONMENT"
EOF
fi

# Inicializar se necessário
if [ ! -d ".terraform" ]; then
    echo -e "${VERDE}🔄 Inicializando Terraform para SQL...${NC}"
    terraform init -backend-config="backend-sql-${ENVIRONMENT}.hcl"
fi

# Validar e aplicar
terraform validate

echo -e "${VERDE}📋 Criando plano do SQL...${NC}"
timeout 300 terraform plan -input=false -out=tfplan \
    -var="project_id=$PROJECT_ID" \
    -var="region=$REGION" \
    -var="environment=$ENVIRONMENT" \
    -var="db_password=$DB_PASSWORD"

echo -e "${VERDE}🚀 Aplicando infraestrutura SQL...${NC}"
timeout 900 terraform apply -input=false tfplan
rm -f tfplan

# Obter outputs
SQL_INSTANCE=$(terraform output -raw sql_instance_name)
SQL_IP=$(terraform output -raw sql_public_ip)

echo -e "${VERDE}✅ Deploy do Cloud SQL concluído!${NC}"
echo -e "${AMARELO}🗄️  Informações do SQL:${NC}"
echo -e "   Instância: $SQL_INSTANCE"
echo -e "   IP Público: $SQL_IP"
echo -e ""
echo -e "${AZUL}💡 Próximo passo: make deploy-app${NC}"