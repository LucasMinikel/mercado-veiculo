#!/bin/bash

set -e

# Cores para a saída
VERMELHO='\033[0;31m'
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
AZUL='\033[0;34m'
NC='\033[0m'

echo -e "${VERDE}🔐 Configurando IAP automaticamente...${NC}"

# Obter diretório atual
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TFVARS_FILE="$PROJECT_ROOT/infrastructure/terraform/terraform.tfvars"

# Obter email atual do gcloud
CURRENT_EMAIL=$(gcloud config get-value account 2>/dev/null)

if [ -z "$CURRENT_EMAIL" ]; then
    echo -e "${VERMELHO}❌ Erro: Não foi possível obter o email. Execute 'gcloud auth login' primeiro.${NC}"
    exit 1
fi

echo -e "${AZUL}📧 Email detectado: $CURRENT_EMAIL${NC}"

# Verificar se terraform.tfvars existe
if [ ! -f "$TFVARS_FILE" ]; then
    echo -e "${VERMELHO}❌ Arquivo terraform.tfvars não encontrado em $TFVARS_FILE${NC}"
    echo -e "${AMARELO}💡 Execute 'make setup' primeiro para criar o arquivo${NC}"
    exit 1
fi

# Verificar se configurações IAP já existem
if grep -q "support_email" "$TFVARS_FILE"; then
    echo -e "${AMARELO}⚠️  Configurações IAP já existem no terraform.tfvars${NC}"
    echo -e "${AZUL}📋 Configurações atuais:${NC}"
    grep -A 5 "support_email\|authorized_users" "$TFVARS_FILE"
    echo ""
    echo -e "${AMARELO}Deseja sobrescrever? (y/n)${NC}"
    read -p "Sobrescrever: " overwrite
    if [[ ! "$overwrite" =~ ^[Yy]$ ]]; then
        echo -e "${VERDE}✅ Mantendo configurações existentes${NC}"
        exit 0
    fi
    
    # Remover configurações existentes
    echo -e "${AMARELO}🔄 Removendo configurações antigas...${NC}"
    # Criar backup
    cp "$TFVARS_FILE" "$TFVARS_FILE.backup.$(date +%Y%m%d_%H%M%S)"
    
    # Remover linhas relacionadas ao IAP
    if [[ "$OSTYPE" == "darwin"* ]]; then
        # macOS
        sed -i '' '/^support_email/d' "$TFVARS_FILE"
        sed -i '' '/^authorized_users/d' "$TFVARS_FILE"
        sed -i '' '/^]/d' "$TFVARS_FILE"
        sed -i '' '/^  "user:/d' "$TFVARS_FILE"
        sed -i '' '/^  "group:/d' "$TFVARS_FILE"
        sed -i '' '/^# Configurações IAP/d' "$TFVARS_FILE"
    else
        # Linux
        sed -i '/^support_email/d' "$TFVARS_FILE"
        sed -i '/^authorized_users/d' "$TFVARS_FILE"
        sed -i '/^]/d' "$TFVARS_FILE"
        sed -i '/^  "user:/d' "$TFVARS_FILE"
        sed -i '/^  "group:/d' "$TFVARS_FILE"
        sed -i '/^# Configurações IAP/d' "$TFVARS_FILE"
    fi
fi

# Adicionar configurações IAP
echo -e "${VERDE}📝 Adicionando configurações IAP...${NC}"
cat >> "$TFVARS_FILE" << EOF

# Configurações IAP
support_email = "$CURRENT_EMAIL"
authorized_users = [
  "user:$CURRENT_EMAIL"
]
EOF

echo -e "${VERDE}✅ Configurações IAP adicionadas ao terraform.tfvars${NC}"
echo -e "${AZUL}📧 Support email: $CURRENT_EMAIL${NC}"
echo -e "${AZUL}👤 Usuário autorizado: $CURRENT_EMAIL${NC}"

# Validar email
if [[ "$CURRENT_EMAIL" =~ ^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]; then
    echo -e "${VERDE}✅ Email válido${NC}"
else
    echo -e "${AMARELO}⚠️  Email pode estar em formato inválido${NC}"
fi

echo ""
echo -e "${AMARELO}📝 Para adicionar mais usuários, edite manualmente:${NC}"
echo -e "   $TFVARS_FILE"
echo ""
echo -e "${AZUL}💡 Exemplos de usuários autorizados:${NC}"
echo -e "   user:outro.usuario@gmail.com"
echo -e "   group:admins@meudominio.com"
echo ""
echo -e "${VERDE}🚀 Próximo passo: execute 'make deploy' para aplicar as mudanças${NC}"