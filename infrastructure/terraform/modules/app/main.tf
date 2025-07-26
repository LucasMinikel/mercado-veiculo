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

resource "google_secret_manager_secret_iam_member" "db_password_access" {
  secret_id = var.db_secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.cloud_run.email}"
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
  member   = "allUsers"
}
