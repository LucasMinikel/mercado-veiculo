terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_sql_database_instance" "main" {
  database_version    = "POSTGRES_14"
  project             = var.project_id
  region              = var.region
  name                = "${var.short_name}-${var.environment}-sql"
  deletion_protection = false

  settings {
    tier      = "db-f1-micro"
    disk_size = 20
    disk_type = "PD_HDD"
    backup_configuration {
      enabled = false
    }
    ip_configuration {
      ipv4_enabled = true
      authorized_networks {
        value = "0.0.0.0/0"
      }
      ssl_mode = "ENCRYPTED_ONLY"
    }
  }
}

resource "google_sql_database" "main" {
  name      = var.db_name
  instance  = google_sql_database_instance.main.name
  project   = var.project_id
  charset   = "UTF8"
  collation = "en_US.UTF8"
}

resource "google_sql_user" "main" {
  name     = var.db_user
  instance = google_sql_database_instance.main.name
  project  = var.project_id
  password = var.db_password
}

resource "google_secret_manager_secret" "db_password" {
  secret_id = "${var.short_name}-${var.environment}-db-pass"
  project   = var.project_id
  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "db_password_version" {
  secret      = google_secret_manager_secret.db_password.id
  secret_data = var.db_password
}
