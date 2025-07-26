#!/bin/bash
set -e

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"
TERRAFORM_DIR="$PROJECT_ROOT/infrastructure/terraform"

cd "$PROJECT_ROOT"

if [ -f "$TERRAFORM_DIR/terraform.tfvars" ]; then
    PROJECT_ID=$(grep 'project_id' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2)
    REGION=$(grep 'region' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2 || echo "southamerica-east1")
    ENVIRONMENT=$(grep 'environment' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2 || echo "dev")
    DB_PASSWORD=$(grep 'db_password' "$TERRAFORM_DIR/terraform.tfvars" | cut -d'"' -f2 2>/dev/null || echo "")
else
    echo "❌ terraform.tfvars não encontrado"
    exit 1
fi

if [ -z "$DB_PASSWORD" ]; then
    read -s -p "Senha do DB: " DB_PASSWORD
    echo ""
    echo "db_password = "$DB_PASSWORD"" >> "$TERRAFORM_DIR/terraform.tfvars"
fi

gcloud config set project $PROJECT_ID

gcloud services enable \
    run.googleapis.com \
    cloudbuild.googleapis.com \
    artifactregistry.googleapis.com \
    sqladmin.googleapis.com \
    secretmanager.googleapis.com \
    vpcaccess.googleapis.com \
    servicenetworking.googleapis.com \
    --project=$PROJECT_ID \
    --quiet

cd "$TERRAFORM_DIR"

if [ ! -d ".terraform" ]; then
    terraform init
fi

terraform validate

terraform apply -auto-approve \
    -var="project_id=$PROJECT_ID" \
    -var="region=$REGION" \
    -var="environment=$ENVIRONMENT" \
    -var="db_password=$DB_PASSWORD" \
    -var="use_real_images=false"

REPO_URL=$(terraform output -raw repository_url)

gcloud auth configure-docker "${REGION}-docker.pkg.dev" --quiet

for service in cliente-service veiculo-service pagamento-service; do
    echo "🔨 Construindo $service..."
    cd "$PROJECT_ROOT/services/$service"
    docker build -t "${REPO_URL}/$service:latest" .
    docker push "${REPO_URL}/$service:latest"
done

cd "$TERRAFORM_DIR"

terraform apply -auto-approve \
    -var="project_id=$PROJECT_ID" \
    -var="region=$REGION" \
    -var="environment=$ENVIRONMENT" \
    -var="db_password=$DB_PASSWORD" \
    -var="cliente_image=${REPO_URL}/cliente-service:latest" \
    -var="veiculo_image=${REPO_URL}/veiculo-service:latest" \
    -var="pagamento_image=${REPO_URL}/pagamento-service:latest" \
    -var="use_real_images=true"

echo "✅ Deploy concluído!"
terraform output -json service_urls | jq -r 'to_entries[] | "\(.key): \(.value)"'