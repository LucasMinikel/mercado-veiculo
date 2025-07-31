terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

# API Gateway API
resource "google_api_gateway_api" "vehicle_sales_api" {
  provider = google-beta
  api_id   = "${var.short_name}-${var.environment}-api"
  project  = var.project_id
}

# OpenAPI Spec
locals {
  openapi_spec = templatefile("${path.module}/openapi.yaml", {
    cliente_service_url   = var.service_urls["cliente-service"]
    veiculo_service_url   = var.service_urls["veiculo-service"]
    pagamento_service_url = var.service_urls["pagamento-service"]
    orquestrador_url      = var.service_urls["orquestrador"]
  })
}

# API Config
resource "google_api_gateway_api_config" "vehicle_sales_config" {
  provider      = google-beta
  api           = google_api_gateway_api.vehicle_sales_api.api_id
  api_config_id = "${var.short_name}-${var.environment}-config-v2"
  project       = var.project_id

  openapi_documents {
    document {
      path     = "openapi.yaml"
      contents = base64encode(local.openapi_spec)
    }
  }

  lifecycle {
    create_before_destroy = true
  }
}

# Gateway
resource "google_api_gateway_gateway" "vehicle_sales_gateway" {
  provider   = google-beta
  api_config = google_api_gateway_api_config.vehicle_sales_config.id
  gateway_id = "${var.short_name}-${var.environment}-gateway"
  region     = var.region
  project    = var.project_id
}
