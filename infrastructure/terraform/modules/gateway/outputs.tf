output "gateway_url" {
  description = "URL do API Gateway"
  value       = google_api_gateway_gateway.vehicle_sales_gateway.default_hostname
}

output "gateway_id" {
  description = "ID do Gateway"
  value       = google_api_gateway_gateway.vehicle_sales_gateway.gateway_id
}

output "api_id" {
  description = "ID da API"
  value       = google_api_gateway_api.vehicle_sales_api.api_id
}
