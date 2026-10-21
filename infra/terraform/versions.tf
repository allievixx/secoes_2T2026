# Infraestrutura de secoes_2T2026 gerenciada pelo Terraform.
# Integrada com o workflow reutilizável comite-popular-tech/pipelines-compartilhados.
#
# O estado fica no Google Cloud Storage (backend "gcs"), recebendo
# bucket e prefixo dinamicamente pelo pipeline via -backend-config.

terraform {
  required_version = ">= 1.6.0"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.0"
    }
  }

  backend "gcs" {}
}

provider "google" {
  project = var.project_id
  region  = var.region
}
