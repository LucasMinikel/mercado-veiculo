output "cliente_service_url" {
  description = "URL do serviço cliente"
  value       = google_cloud_run_v2_service.cliente_service.uri
}

output "veiculo_service_url" {
  description = "URL do serviço veículo"
  value       = google_cloud_run_v2_service.veiculo_service.uri
}

output "artifact_registry_repository_url" {
  description = "URL do repositório Artifact Registry"
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${local.repository_name}"
}

output "project_id" {
  description = "ID do projeto no Google Cloud"
  value       = var.project_id
}

output "region" {
  description = "Região do Google Cloud"
  value       = var.region
}

output "service_account_email" {
  description = "E-mail da conta de serviço para o Cloud Run"
  value       = google_service_account.cloud_run.email
}
