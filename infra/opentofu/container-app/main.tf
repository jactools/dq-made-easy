data "azurerm_container_app_environment" "this" {
  name                = var.container_app_environment_name
  resource_group_name = var.resource_group_name
}

locals {
  use_registry              = var.registry_server != ""
  registry_password_secret  = "registry-password"
  revision_mode             = "Single"
  ingress_external_enabled   = var.ingress == "external"
}

resource "azurerm_container_app" "this" {
  name                         = var.container_app_name
  resource_group_name          = var.resource_group_name
  container_app_environment_id = data.azurerm_container_app_environment.this.id
  revision_mode                = local.revision_mode
  revision_suffix              = var.revision_suffix == "" ? null : var.revision_suffix

  dynamic "secret" {
    for_each = local.use_registry ? [1] : []

    content {
      name  = local.registry_password_secret
      value = var.registry_password
    }
  }

  dynamic "registry" {
    for_each = local.use_registry ? [1] : []

    content {
      server               = var.registry_server
      username             = var.registry_username
      password_secret_name = local.registry_password_secret
    }
  }

  ingress {
    external_enabled = local.ingress_external_enabled
    target_port      = var.target_port
    transport        = "auto"

    traffic_weight {
      latest_revision = true
      percentage      = 100
    }
  }

  template {
    container {
      name   = var.container_name
      image  = var.container_image
      cpu    = var.cpu
      memory = var.memory
    }

    min_replicas = var.min_replicas
    max_replicas = var.max_replicas
  }
}
