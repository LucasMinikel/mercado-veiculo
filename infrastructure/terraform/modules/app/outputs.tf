output "service_urls" {
  value = {
    for k, v in google_cloud_run_v2_service.services : k => v.uri
  }
}

output "repository_url" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.main.repository_id}"
}

output "service_account_email" {
  value = google_service_account.cloud_run.email
}

output "api_gateway_service_account" {
  description = "Email do service account do API Gateway"
  value       = google_service_account.api_gateway.email
}
