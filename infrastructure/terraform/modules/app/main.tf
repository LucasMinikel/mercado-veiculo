terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_artifact_registry_repository" "main" {
  location      = var.region
  repository_id = var.repository_name
  description   = "Repository for microservices containers"
  format        = "DOCKER"
}

resource "google_service_account" "cloud_run" {
  account_id   = "${var.short_name}-${var.environment}-run"
  display_name = "Cloud Run Service Account"
}

resource "google_project_iam_member" "cloud_run_sql_client" {
  project = var.project_id
  role    = "roles/cloudsql.client"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
}

resource "google_service_account" "api_gateway" {
  account_id   = "${var.short_name}-${var.environment}-gateway"
  display_name = "API Gateway Service Account"
  description  = "Service account used by API Gateway to invoke Cloud Run services"
}

# Permissão para o API Gateway invocar os serviços
resource "google_project_iam_member" "api_gateway_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.api_gateway.email}"
}

resource "google_secret_manager_secret_iam_member" "db_password_access" {
  secret_id = var.db_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
}

locals {
  pubsub_topics_map = {
    "commands.credit.reserve"               = null
    "commands.credit.release"               = null
    "commands.vehicle.reserve"              = null
    "commands.vehicle.release"              = null
    "commands.payment.generate_code"        = null
    "commands.payment.process"              = null
    "commands.payment.refund"               = null
    "events.credit.reserved"                = null
    "events.credit.reservation_failed"      = null
    "events.credit.released"                = null
    "events.vehicle.reserved"               = null
    "events.vehicle.reservation_failed"     = null
    "events.vehicle.released"               = null
    "events.payment.code_generated"         = null
    "events.payment.code_generation_failed" = null
    "events.payment.processed"              = null
    "events.payment.failed"                 = null
    "events.payment.refunded"               = null
    "events.payment.refund_failed"          = null
  }

  pubsub_subscriptions_map = {
    "cliente-service-reserve-credit-sub"              = "commands.credit.reserve"
    "cliente-service-release-credit-sub"              = "commands.credit.release"
    "veiculo-service-reserve-vehicle-sub"             = "commands.vehicle.reserve"
    "veiculo-service-release-vehicle-sub"             = "commands.vehicle.release"
    "pagamento-service-generate-code-sub"             = "commands.payment.generate_code"
    "pagamento-service-process-payment-sub"           = "commands.payment.process"
    "pagamento-service-refund-payment-sub"            = "commands.payment.refund"
    "orquestrador-credit-reserved-sub"                = "events.credit.reserved"
    "orquestrador-credit-reservation-failed-sub"      = "events.credit.reservation_failed"
    "orquestrador-credit-released-sub"                = "events.credit.released"
    "orquestrador-vehicle-reserved-sub"               = "events.vehicle.reserved"
    "orquestrador-vehicle-reservation-failed-sub"     = "events.vehicle.reservation_failed"
    "orquestrador-vehicle-released-sub"               = "events.vehicle.released"
    "orquestrador-payment-code-generated-sub"         = "events.payment.code_generated"
    "orquestrador-payment-code-generation-failed-sub" = "events.payment.code_generation_failed"
    "orquestrador-payment-processed-sub"              = "events.payment.processed"
    "orquestrador-payment-failed-sub"                 = "events.payment.failed"
    "orquestrador-payment-refunded-sub"               = "events.payment.refunded"
    "orquestrador-payment-refund-failed-sub"          = "events.payment.refund_failed"
  }
}

resource "google_pubsub_topic" "topics" {
  for_each = local.pubsub_topics_map
  name     = each.key
  project  = var.project_id
}

resource "google_pubsub_subscription" "subscriptions" {
  for_each             = local.pubsub_subscriptions_map
  name                 = each.key
  topic                = google_pubsub_topic.topics[each.value].id
  ack_deadline_seconds = 10
  project              = var.project_id
}

resource "google_project_iam_member" "cloud_run_pubsub_editor" {
  project = var.project_id
  role    = "roles/pubsub.editor"
  member  = "serviceAccount:${google_service_account.cloud_run.email}"
  depends_on = [
    google_pubsub_topic.topics,
    google_pubsub_subscription.subscriptions
  ]
}

resource "google_cloud_run_v2_service" "services" {
  for_each = var.services
  name     = each.key
  location = var.region

  template {
    containers {
      image = each.value.image
      ports {
        container_port = 8080
      }

      env {
        name  = "DEBUG"
        value = "0"
      }
      env {
        name  = "ENVIRONMENT"
        value = var.environment
      }
      env {
        name  = "DB_HOST"
        value = var.db_public_ip
      }
      env {
        name  = "DB_USER"
        value = var.db_user
      }
      env {
        name  = "DB_NAME"
        value = var.db_name
      }
      env {
        name  = "DATABASE_URL"
        value = ""
      }
      env {
        name  = "PROJECT_ID"
        value = var.project_id
      }
      env {
        name = "DB_PASSWORD"
        value_source {
          secret_key_ref {
            secret  = var.db_secret_id
            version = "latest"
          }
        }
      }

      resources {
        limits = {
          cpu    = "1000m"
          memory = "512Mi"
        }
      }
    }

    scaling {
      min_instance_count = var.use_real_images ? 1 : 0
      max_instance_count = 10
    }

    service_account = google_service_account.cloud_run.email
  }
}

resource "google_cloud_run_v2_service_iam_member" "public_access" {
  for_each = var.services
  location = google_cloud_run_v2_service.services[each.key].location
  project  = google_cloud_run_v2_service.services[each.key].project
  name     = google_cloud_run_v2_service.services[each.key].name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.api_gateway.email}"
}
