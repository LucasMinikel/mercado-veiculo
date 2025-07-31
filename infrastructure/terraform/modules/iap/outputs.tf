output "api_service_account_email" {
  description = "Email do service account para autenticação da API"
  value       = google_service_account.api_users.email
}

output "api_service_account_key" {
  description = "Chave do service account para autenticação"
  value       = google_service_account_key.api_users_key.private_key
  sensitive   = true
}

output "authorized_users_count" {
  description = "Número de usuários autorizados configurados"
  value       = length(var.authorized_users)
}

output "support_email" {
  description = "Email de suporte configurado"
  value       = var.support_email
}

output "auth_enabled" {
  description = "Indica se autenticação foi configurada"
  value       = true
}
