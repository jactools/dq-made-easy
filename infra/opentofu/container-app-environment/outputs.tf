output "resource_group_name" {
  value = azurerm_resource_group.this.name
}

output "log_analytics_workspace_id" {
  value = azurerm_log_analytics_workspace.this.id
}

output "container_app_environment_id" {
  value = azurerm_container_app_environment.this.id
}
