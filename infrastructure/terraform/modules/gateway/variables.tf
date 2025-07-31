variable "project_id" {
  type        = string
  description = "GCP Project ID"
}

variable "region" {
  type        = string
  description = "GCP Region"
}

variable "environment" {
  type        = string
  description = "Environment (dev, staging, prod)"
}

variable "short_name" {
  type        = string
  description = "Short name for resources"
}

variable "service_urls" {
  type        = map(string)
  description = "Map of service names to their URLs"
}
