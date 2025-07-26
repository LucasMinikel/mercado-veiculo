output "instance_name" {
  value = google_sql_database_instance.main.name
}

output "connection_name" {
  value = google_sql_database_instance.main.connection_name
}

output "public_ip" {
  value = google_sql_database_instance.main.public_ip_address
}

output "secret_id" {
  value = google_secret_manager_secret.db_password.secret_id
}
