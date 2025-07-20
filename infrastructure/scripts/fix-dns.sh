#!/bin/bash

set -e

# Cores para a saída
VERMELHO='\033[0;31m'
VERDE='\033[0;32m'
AMARELO='\033[1;33m'
NC='\033[0m'

echo -e "${VERDE}🔍 Diagnosticando e corrigindo problemas de DNS...${NC}"

# Função para testar conectividade
testar_conectividade() {
    local host=$1
    echo -e "${AMARELO}Testando conectividade com $host...${NC}"

    if ping -c 3 -W 5 "$host" &>/dev/null; then
        echo -e "${VERDE}✅ $host acessível${NC}"
        return 0
    else
        echo -e "${VERMELHO}❌ $host não acessível${NC}"
        return 1
    fi
}

# Função para testar resolução DNS
testar_dns() {
    local host=$1
    echo -e "${AMARELO}Testando resolução DNS para $host...${NC}"

    if nslookup "$host" &>/dev/null; then
        echo -e "${VERDE}✅ DNS resolve $host${NC}"
        return 0
    else
        echo -e "${VERMELHO}❌ Falha na resolução DNS para $host${NC}"
        return 1
    fi
}

# Corrigir DNS de forma robusta
corrigir_dns_robusto() {
    echo -e "${AMARELO}🔧 Aplicando correção robusta de DNS...${NC}"

    sudo cp /etc/resolv.conf /etc/resolv.conf.backup 2>/dev/null || true
    sudo systemctl stop systemd-resolved 2>/dev/null || true
    sudo systemctl stop NetworkManager 2>/dev/null || true

    cat << EOF | sudo tee /etc/resolv.conf > /dev/null
nameserver 8.8.8.8
nameserver 8.8.4.4
nameserver 1.1.1.1
nameserver 1.0.0.1
options timeout:2
options attempts:3
options rotate
EOF

    sudo systemctl flush-dns 2>/dev/null || true
    export RESOLV_CONF=/etc/resolv.conf
    sudo systemctl start systemd-resolved 2>/dev/null || true
    sudo systemctl start NetworkManager 2>/dev/null || true

    sleep 10

    if command -v systemd-resolve &>/dev/null; then
        sudo systemd-resolve --flush-caches 2>/dev/null || true
    fi

    if command -v resolvectl &>/dev/null; then
        sudo resolvectl flush-caches 2>/dev/null || true
    fi
}

# Testes básicos
echo -e "${VERDE}🔍 Executando testes básicos...${NC}"
testar_conectividade "8.8.8.8"

# Hosts críticos
HOSTS_CRITICOS=(
    "oauth2.googleapis.com"
    "cloudresourcemanager.googleapis.com"
    "serviceusage.googleapis.com"
    "run.googleapis.com"
    "artifactregistry.googleapis.com"
    "iam.googleapis.com"
)

PROBLEMAS_DNS=false
for host in "${HOSTS_CRITICOS[@]}"; do
    if ! testar_dns "$host"; then
        PROBLEMAS_DNS=true
    fi
done

if [ "$PROBLEMAS_DNS" = true ]; then
    echo -e "${AMARELO}⚠️  Problemas de DNS detectados. Aplicando correções...${NC}"
    corrigir_dns_robusto
else
    echo -e "${VERDE}✅ DNS funcionando corretamente${NC}"
fi

echo -e "${VERDE}🏁 Diagnóstico e correção concluídos${NC}"

# Exportar variáveis
export DNS_CORRIGIDO=true
