#!/bin/bash

set -e

VERMELHO='\033[0;31m'
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
NC='\033[0m'

echo -e "${VERDE}🚀 Configuração rápida para o projeto Google Cloud...${NC}"

for ferramenta in gcloud terraform docker; do
    if ! command -v $ferramenta &> /dev/null; then
        echo -e "${VERMELHO}❌ $ferramenta não está instalado${NC}"
        case $ferramenta in
            gcloud)
                echo -e "${AMARELO}💡 Instale o Google Cloud SDK: https://cloud.google.com/sdk/docs/install${NC}"
                ;;
            terraform)
                echo -e "${AMARELO}💡 Instale o Terraform: https://developer.hashicorp.com/terraform/downloads${NC}"
                ;;
            docker)
                echo -e "${AMARELO}💡 Instale o Docker: https://docs.docker.com/get-docker/${NC}"
                ;;
        esac
        exit 1
    fi
done

PROJECT_ID=${1:-$PROJECT_ID}
if [ -z "$PROJECT_ID" ]; then
    echo -e "${AMARELO}📝 Por favor, informe o ID do seu projeto Google Cloud:${NC}"
    read -p "ID do Projeto: " PROJECT_ID
fi

echo -e "${VERDE}🔧 Usando ID do Projeto: $PROJECT_ID${NC}"

if [ -z "$CI" ] && [ -z "$GITHUB_ACTIONS" ]; then
    echo -e "${VERDE}🔐 Configurando autenticação...${NC}"
    
    if ! gcloud auth list --filter=status:ACTIVE --format="value(account)" | grep -q .; then
        echo -e "${AMARELO}🔑 Fazendo login no gcloud...${NC}"
        gcloud auth login --no-launch-browser
        gcloud auth application-default login --no-launch-browser
    else
        echo -e "${VERDE}✅ Já autenticado no gcloud${NC}"
    fi
fi

gcloud config set project $PROJECT_ID

if ! gcloud projects describe $PROJECT_ID &>/dev/null; then
    echo -e "${VERMELHO}❌ Não foi possível acessar o projeto $PROJECT_ID${NC}"
    echo -e "${AMARELO}💡 Verifique se:${NC}"
    echo -e "   - O projeto existe"
    echo -e "   - Você tem permissões no projeto"
    echo -e "   - Está autenticado corretamente"
    exit 1
fi

echo -e "${VERDE}🔌 Habilitando APIs necessárias...${NC}"
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    storage.googleapis.com \
    vpcaccess.googleapis.com \
    --project=$PROJECT_ID \
    --quiet

echo -e "${VERDE}🐳 Configurando autenticação do Docker...${NC}"
gcloud auth configure-docker southamerica-east1-docker.pkg.dev --quiet

echo -e "${VERDE}📝 Criando configuração do terraform...${NC}"
cd infrastructure/terraform

if [ -f "terraform.tfvars" ]; then
    echo -e "${AMARELO}⚠️  terraform.tfvars já existe. Deseja sobrescrever? (y/n)${NC}"
    read -p "Sobrescrever: " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        echo -e "${VERDE}✅ Mantendo configuração existente${NC}"
        exit 0
    fi
fi

echo -e "${AMARELO}🔐 Por favor, defina uma senha para o banco de dados PostgreSQL:${NC}"
echo -e "${AMARELO}(A senha deve ter pelo menos 8 caracteres)${NC}"
while true; do
    read -s -p "Senha do DB: " DB_PASSWORD
    echo ""
    if [ ${#DB_PASSWORD} -ge 8 ]; then
        break
    else
        echo -e "${VERMELHO}❌ A senha deve ter pelo menos 8 caracteres${NC}"
    fi
done

cat > terraform.tfvars << EOF
project_id   = "$PROJECT_ID"
project_name = "microservices-saga"
region       = "southamerica-east1"
environment  = "dev"
db_password  = "$DB_PASSWORD"
EOF

echo -e "${VERDE}✅ Configuração concluída!${NC}"
echo -e "${AMARELO}📋 Próximos passos:${NC}"
echo -e "1. Execute: make deploy"
echo -e "2. Para desenvolvimento local: make dev"