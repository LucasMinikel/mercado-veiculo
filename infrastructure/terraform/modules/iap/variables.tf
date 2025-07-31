variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "support_email" {
  type        = string
  description = "Email de suporte para OAuth consent screen"
}

variable "authorized_users" {
  type        = list(string)
  description = "Lista de usuários autorizados a acessar via IAP"
  default     = []
}
