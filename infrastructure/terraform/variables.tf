variable "project_id" {
  description = "ID do projeto no Google Cloud"
  type        = string
}

variable "project_name" {
  description = "Nome do projeto para nomear recursos"
  type        = string
  default     = "microservices-saga"
}

variable "region" {
  description = "Região do Google Cloud"
  type        = string
  default     = "southamerica-east1"
}

variable "environment" {
  description = "Ambiente (dev, staging, prod)"
  type        = string
  default     = "dev"
}

variable "use_real_images" {
  description = "Indica se deve usar imagens reais do Docker ou placeholders"
  type        = bool
  default     = false
}

variable "cliente_image" {
  description = "Imagem Docker para o serviço cliente"
  type        = string
  default     = ""
}

variable "veiculo_image" {
  description = "Imagem Docker para o serviço veículo"
  type        = string
  default     = ""
}
