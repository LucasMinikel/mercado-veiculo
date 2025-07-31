output "service_urls" {
  value = module.app.service_urls
}

output "repository_url" {
  value = module.app.repository_url
}

output "sql_instance_name" {
  value = module.sql.instance_name
}

output "sql_public_ip" {
  value = module.sql.public_ip
}

output "gateway_url" {
  description = "URL do API Gateway"
  value       = module.gateway.gateway_url
}

output "api_endpoints" {
  description = "Endpoints principais da API"
  value = {
    base_url = "https://${module.gateway.gateway_url}"
  }
}

output "api_gateway_service_account" {
  description = "Service account do API Gateway"
  value       = module.app.api_gateway_service_account
}

output "api_authentication" {
  description = "Configurações de autenticação da API"
  value = {
    support_email          = module.iap.support_email
    authorized_users_count = module.iap.authorized_users_count
    auth_enabled           = module.iap.auth_enabled
    service_account_email  = module.iap.api_service_account_email
  }
}

output "api_service_account_key" {
  description = "Chave do service account para autenticação (use com cuidado)"
  value       = module.iap.api_service_account_key
  sensitive   = true
}

output "access_instructions" {
  description = "Instruções para acessar a API"
  value = {
    gateway_url   = "https://${module.gateway.gateway_url}"
    health_check  = "https://${module.gateway.gateway_url}/health"
    auth_required = "Use: gcloud auth print-access-token"
    example_curl  = "curl -H 'Authorization: Bearer $(gcloud auth print-access-token)' https://${module.gateway.gateway_url}/vehicles"
  }
}
