variable "resource_group_name" {
  type        = string
  description = "Resource group for the Container App."
}

variable "location" {
  type        = string
  description = "Azure region for the resources."
}

variable "container_app_environment_name" {
  type        = string
  description = "Existing Azure Container Apps environment name."
}

variable "container_app_name" {
  type        = string
  description = "Container App name."
}

variable "container_name" {
  type        = string
  description = "Container name inside the app."
}

variable "container_image" {
  type        = string
  description = "Container image to deploy."
}

variable "target_port" {
  type        = number
  description = "Container port exposed by ingress."
}

variable "ingress" {
  type        = string
  description = "Ingress mode: internal or external."

  validation {
    condition     = contains(["internal", "external"], var.ingress)
    error_message = "ingress must be internal or external."
  }
}

variable "revision_suffix" {
  type        = string
  description = "Optional revision suffix."
  default     = ""
}

variable "cpu" {
  type        = number
  description = "Container CPU."
  default     = 0.5
}

variable "memory" {
  type        = string
  description = "Container memory."
  default     = "1.0Gi"
}

variable "min_replicas" {
  type        = number
  description = "Minimum replicas."
  default     = 1
}

variable "max_replicas" {
  type        = number
  description = "Maximum replicas."
  default     = 1
}

variable "registry_server" {
  type        = string
  description = "Optional registry server hostname."
  default     = ""
}

variable "registry_username" {
  type        = string
  description = "Optional registry username."
  default     = ""
}

variable "registry_password" {
  type        = string
  description = "Optional registry password."
  default     = ""
  sensitive   = true
}
