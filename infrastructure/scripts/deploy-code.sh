#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/infrastructure/terraform"

cd "$TERRAFORM_DIR"

if [ ! -f "terraform.tfstate" ]; then
    echo "❌ Infraestrutura não implantada"
    exit 1
fi

PROJECT_ID=$(terraform output -raw project_id 2>/dev/null)
REGION=$(terraform output -raw region 2>/dev/null)
REPO_URL=$(terraform output -raw repository_url 2>/dev/null)

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

for service in cliente-service veiculo-service pagamento-service; do
    echo "🔨 Atualizando $service..."
    cd "$PROJECT_ROOT/services/$service"
    docker build -t "${REPO_URL}/$service:latest" .
    docker push "${REPO_URL}/$service:latest"
    
    gcloud run services update $service \
        --image="${REPO_URL}/$service:latest" \
        --region="$REGION" \
        --project="$PROJECT_ID" \
        --quiet
done

echo "✅ Código atualizado!"