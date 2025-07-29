terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  short_name      = "ms-saga"
  repository_name = "${replace(var.project_name, "_", "-")}-repo"

  services = {
    cliente-service   = { image = var.use_real_images ? var.cliente_image : "gcr.io/cloudrun/hello" }
    veiculo-service   = { image = var.use_real_images ? var.veiculo_image : "gcr.io/cloudrun/hello" }
    pagamento-service = { image = var.use_real_images ? var.pagamento_image : "gcr.io/cloudrun/hello" }
    orquestrador      = { image = var.use_real_images ? var.orquestrador_image : "gcr.io/cloudrun/hello" }
  }
}

module "sql" {
  source = "./modules/sql"

  project_id  = var.project_id
  region      = var.region
  environment = var.environment
  short_name  = local.short_name
  db_name     = var.db_name
  db_user     = var.db_user
  db_password = var.db_password
}

module "app" {
  source = "./modules/app"

  project_id      = var.project_id
  region          = var.region
  environment     = var.environment
  short_name      = local.short_name
  repository_name = local.repository_name
  use_real_images = var.use_real_images
  services        = local.services
  db_public_ip    = module.sql.public_ip
  db_user         = var.db_user
  db_name         = var.db_name
  db_secret_id    = module.sql.secret_id

  depends_on = [module.sql]
}
