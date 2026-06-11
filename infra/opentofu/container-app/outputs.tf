output "container_app_id" {
  value = azurerm_container_app.this.id
}

output "container_app_fqdn" {
  value = azurerm_container_app.this.ingress[0].fqdn
}
