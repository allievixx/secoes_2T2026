# Registros DNS do secoes em boralula.org: o endereço do site, na conta kadu da Cloudflare (a de produção).
# A zona e o DNS compartilhado são do iac-shared (terraform/cloudflare-kadu); aqui entra só o que é deste repositório.
# Desenho em README.md.
#
# Autenticação, toda por variável de ambiente (nunca no Git):
#   CLOUDFLARE_API_TOKEN  token da conta kadu com DNS (Zone DNS) na zona boralula.org (README.md)
#   TF_VAR_zone_id        id da zona boralula.org (segredo CLOUDFLARE_KADU_ZONE_ID)
#   credencial do Google com acesso ao prefixo do estado (gcloud auth application-default login,
#   ou Workload Identity Federation no workflow .github/workflows/infra-cloudflare-kadu.yml)

terraform {
  required_version = ">= 1.9"

  required_providers {
    cloudflare = {
      source  = "cloudflare/cloudflare"
      version = "~> 5.0"
    }
  }

  # O bucket e o prefixo entram no init (README.md). A conta que o iac cria para este repositório
  # (segredo TF_ESTADO_CONTA) só alcança objetos sob secoes/, e cada raiz usa um prefixo dentro dele:
  #   terraform init -backend-config="bucket=<bucket>" -backend-config="prefix=secoes/cloudflare-kadu"
  backend "gcs" {}
}

# O token vem de CLOUDFLARE_API_TOKEN: não entra em variável nem no estado.
provider "cloudflare" {}
