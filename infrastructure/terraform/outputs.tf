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