terraform {
  required_version = ">= 1.0"
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}

locals {
  repository_name = "${var.project_name}-repo"
  image_base_url  = "${var.region}-docker.pkg.dev/${var.project_id}/${local.repository_name}"

  cliente_image   = var.use_real_images ? var.cliente_image : "gcr.io/cloudrun/hello"
  veiculo_image   = var.use_real_images ? var.veiculo_image : "gcr.io/cloudrun/hello"
  pagamento_image = var.use_real_images ? var.pagamento_image : "gcr.io/cloudrun/hello"
}

resource "google_artifact_registry_repository" "main" {
  location      = var.region
  repository_id = local.repository_name
  description   = "Repository for microservices containers"
  format        = "DOCKER"
}

resource "google_service_account" "cloud_run" {
  account_id   = "${var.project_name}-cloud-run"
  display_name = "Cloud Run Service Account"
  description  = "Service account for Cloud Run services"
}

resource "google_cloud_run_v2_service" "cliente_service" {
  name     = "cliente-service"
  location = var.region

  template {
    containers {
      image = local.cliente_image

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

  depends_on = [google_artifact_registry_repository.main]
}

resource "google_cloud_run_v2_service" "veiculo_service" {
  name     = "veiculo-service"
  location = var.region

  template {
    containers {
      image = local.veiculo_image

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

  depends_on = [google_artifact_registry_repository.main]
}

resource "google_cloud_run_v2_service" "pagamento_service" {
  name     = "pagamento-service"
  location = var.region

  template {
    containers {
      image = local.pagamento_image

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

  depends_on = [google_artifact_registry_repository.main]
}

resource "google_cloud_run_v2_service_iam_member" "cliente_service_public" {
  location = google_cloud_run_v2_service.cliente_service.location
  project  = google_cloud_run_v2_service.cliente_service.project
  name     = google_cloud_run_v2_service.cliente_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "veiculo_service_public" {
  location = google_cloud_run_v2_service.veiculo_service.location
  project  = google_cloud_run_v2_service.veiculo_service.project
  name     = google_cloud_run_v2_service.veiculo_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}

resource "google_cloud_run_v2_service_iam_member" "pagamento_service_public" {
  location = google_cloud_run_v2_service.pagamento_service.location
  project  = google_cloud_run_v2_service.pagamento_service.project
  name     = google_cloud_run_v2_service.pagamento_service.name
  role     = "roles/run.invoker"
  member   = "allUsers"
}
