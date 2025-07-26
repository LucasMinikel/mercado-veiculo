variable "project_id" {
  type = string
}

variable "region" {
  type = string
}

variable "environment" {
  type = string
}

variable "short_name" {
  type = string
}

variable "repository_name" {
  type = string
}

variable "use_real_images" {
  type = bool
}

variable "services" {
  type = map(object({
    image = string
  }))
}

variable "db_public_ip" {
  type = string
}

variable "db_user" {
  type = string
}

variable "db_name" {
  type = string
}

variable "db_secret_id" {
  type = string
}
