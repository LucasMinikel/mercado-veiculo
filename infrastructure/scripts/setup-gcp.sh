#!/bin/bash

set -e

# Cores para a saída
VERMELHO='\033[0;31m'
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
NC='\033[0m'

echo -e "${VERDE}🚀 Configuração rápida para o projeto Google Cloud...${NC}"

# Verificar ferramentas necessárias
for ferramenta in gcloud terraform docker; do
    if ! command -v $ferramenta &> /dev/null; then
        echo -e "${VERMELHO}❌ $ferramenta não está instalado${NC}"
        exit 1
    fi
done

# Obter ID do projeto
PROJECT_ID=${1:-$PROJECT_ID}
if [ -z "$PROJECT_ID" ]; then
    echo -e "${AMARELO}📝 Por favor, informe o ID do seu projeto Google Cloud:${NC}"
    read -p "ID do Projeto: " PROJECT_ID
fi

echo -e "${VERDE}📋 Usando ID do Projeto: $PROJECT_ID${NC}"

# Só autenticar se não estiver em CI/CD
if [ -z "$CI" ] && [ -z "$GITHUB_ACTIONS" ]; then
    echo -e "${VERDE}🔐 Configurando autenticação...${NC}"
    gcloud auth login --no-launch-browser
    gcloud auth application-default login --no-launch-browser
fi

# Definir projeto atual no gcloud
gcloud config set project $PROJECT_ID

# Verificar acesso ao projeto
if ! gcloud projects describe $PROJECT_ID &>/dev/null; then
    echo -e "${VERMELHO}❌ Não foi possível acessar o projeto $PROJECT_ID${NC}"
    exit 1
fi

# Habilitar APIs necessárias
echo -e "${VERDE}🔌 Habilitando APIs necessárias...${NC}"
gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    --project=$PROJECT_ID \
    --quiet

# Configurar autenticação do Docker
gcloud auth configure-docker southamerica-east1-docker.pkg.dev --quiet

# Criar arquivo terraform.tfvars
echo -e "${VERDE}📝 Criando configuração do terraform...${NC}"
cd infrastructure/terraform

cat > terraform.tfvars << EOF
project_id   = "$PROJECT_ID"
project_name = "microservices-saga"
region       = "southamerica-east1"
environment  = "dev"
EOF

echo -e "${VERDE}✅ Configuração concluída!${NC}"
echo -e "${AMARELO}📋 Próximos passos:${NC}"
echo -e "1. Execute: make deploy"
echo -e "2. Ou para CI/CD, configure estas variáveis de ambiente:"
echo -e "   - PROJECT_ID=$PROJECT_ID"
echo -e "   - REGION=southamerica-east1"
