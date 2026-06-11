variable "resource_group_name" {
  type        = string
  description = "Resource group for the dq-made-easy Azure resources."
}

variable "location" {
  type        = string
  description = "Azure region for the resources."
}

variable "container_app_environment_name" {
  type        = string
  description = "Azure Container Apps environment name."
}

variable "log_analytics_workspace_name" {
  type        = string
  description = "Log Analytics workspace name."
}

variable "tags" {
  type        = map(string)
  description = "Optional resource tags."
  default     = {}
}
