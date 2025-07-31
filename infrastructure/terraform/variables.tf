variable "project_id" {
  type = string
}

variable "project_name" {
  type    = string
  default = "microservices-saga"
}

variable "region" {
  type    = string
  default = "southamerica-east1"
}

variable "environment" {
  type    = string
  default = "dev"
}

variable "use_real_images" {
  type    = bool
  default = false
}

variable "cliente_image" {
  type    = string
  default = ""
}

variable "veiculo_image" {
  type    = string
  default = ""
}

variable "pagamento_image" {
  type    = string
  default = ""
}

variable "orquestrador_image" {
  type    = string
  default = ""
}

variable "db_name" {
  type    = string
  default = "main_db"
}

variable "db_user" {
  type    = string
  default = "user"
}

variable "db_password" {
  type      = string
  sensitive = true
}

variable "state_bucket_name" {
  type = string
}

variable "support_email" {
  type        = string
  description = "Email de suporte para OAuth consent screen"
  default     = ""
}

variable "authorized_users" {
  type        = list(string)
  description = "Lista de usuários autorizados (emails ou grupos)"
  default     = []
}
