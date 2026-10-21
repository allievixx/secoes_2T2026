# PRODUÇÃO: o endereço do site do secoes na zona boralula.org (conta kadu). O site continua no GitHub Pages
# (workflow .github/workflows/pages.yml); a Cloudflare só aponta o nome para ele. Sem ambiente de dev hoje.
#
# O que não é daqui:
#   - a zona boralula.org, as configurações dela e o DNS compartilhado: iac-shared, terraform/cloudflare-kadu;
#   - o domínio personalizado no GitHub Pages (Settings > Pages): configuração do repositório, não da Cloudflare.
#
# A rotina de dados (Cloud Run Job e o bucket dela) entra depois da eleição de 25/10/2026, em outra raiz.

variable "zone_id" {
  description = "ID da zona boralula.org na conta kadu (a zona é do iac-shared). Vem do segredo CLOUDFLARE_KADU_ZONE_ID (TF_VAR_zone_id)."
  type        = string
}

variable "zona" {
  description = "O domínio da produção."
  type        = string
  default     = "boralula.org"
}

variable "endereco" {
  description = "O endereço do site (sem o domínio)."
  type        = string
  default     = "secoes"
}

variable "pages_host" {
  description = "Onde o GitHub Pages da organização responde: <organização>.github.io, sem o nome do repositório."
  type        = string
  default     = "comite-popular-tech.github.io"
}

# CNAME para o Pages da organização. O GitHub escolhe o site pelo domínio personalizado do repositório, não pelo caminho.
resource "cloudflare_dns_record" "site" {
  zone_id = var.zone_id
  name    = "${var.endereco}.${var.zona}"
  type    = "CNAME"
  content = var.pages_host
  # Sem o proxy da Cloudflare: o GitHub Pages emite e renova o próprio certificado (Let's Encrypt) e precisa
  # ver o CNAME apontando para ele. Com o proxy ligado, o nome passa a resolver para a Cloudflare e o GitHub não consegue emitir nem renovar o certificado.
  proxied = false
  ttl     = 1
  comment = "secoes: site no GitHub Pages (repositório comite-popular-tech/secoes)"
}

output "endereco" {
  description = "O endereço criado por este repositório."
  value       = "https://${var.endereco}.${var.zona}"
}
