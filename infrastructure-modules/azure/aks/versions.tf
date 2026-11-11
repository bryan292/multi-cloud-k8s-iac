terraform {
  required_version = ">= 1.10, < 2.0"
  required_providers {
    azurerm = {
      source  = "hashicorp/azurerm"
      version = "4.81.0"
    }
    local = {
      source  = "hashicorp/local"
      version = "2.6.1"
    }
  }
}
