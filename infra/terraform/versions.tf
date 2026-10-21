# Infraestrutura do secoes no projeto da org, aplicada à mão por quem é dono do projeto (infra/README.md).
# O CI só publica a imagem e troca a do Job (.github/workflows/deploy.yml), com a conta de deploy daqui.
#
# Os módulos do iac-shared e o terraform.yml do pipelines-compartilhados são privados, e este repositório
# é público: o Actions daqui não os alcança. Por isso a raiz é escrita aqui, no desenho do post-to-data.

terraform {
  required_version = ">= 1.6"

  required_providers {
    google = {
      source  = "hashicorp/google"
      version = "~> 6.10"
    }
  }

  backend "gcs" {
    bucket = "comite-popular-tech-terraform"
    prefix = "secoes"
  }
}

provider "google" {
  project = var.project_id
  region  = var.region
}
