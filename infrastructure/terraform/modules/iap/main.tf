terraform {
  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 5.0"
    }
  }
}

resource "google_project_service" "iap" {
  service = "iap.googleapis.com"
  project = var.project_id
}

resource "google_project_service" "compute" {
  service            = "compute.googleapis.com"
  project            = var.project_id
  disable_on_destroy = false
}

resource "google_service_account" "api_users" {
  account_id   = "api-users-sa"
  display_name = "API Users Service Account"
  description  = "Service account for API authentication"
  project      = var.project_id
}

resource "google_service_account_key" "api_users_key" {
  service_account_id = google_service_account.api_users.name
  public_key_type    = "TYPE_X509_PEM_FILE"
}

resource "google_project_iam_member" "authorized_users" {
  count   = length(var.authorized_users)
  project = var.project_id
  role    = "roles/run.invoker"
  member  = var.authorized_users[count.index]
}

resource "google_project_iam_member" "api_admin" {
  project = var.project_id
  role    = "roles/run.admin"
  member  = "user:${var.support_email}"
}

resource "google_project_iam_member" "api_sa_invoker" {
  project = var.project_id
  role    = "roles/run.invoker"
  member  = "serviceAccount:${google_service_account.api_users.email}"
}
