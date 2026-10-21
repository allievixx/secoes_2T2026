variable "project_id" {
  type    = string
  default = "thech-against-bozo"
}

variable "region" {
  type    = string
  default = "us-central1"
}

variable "name" {
  description = "Prefixo do Job, do repositório de imagens, das contas e do provider de WIF."
  type        = string
  default     = "secoes"
}

variable "github_repo" {
  type    = string
  default = "comite-popular-tech/secoes"
}

variable "schedule" {
  description = "Horários da rotina (cron do Cloud Scheduler)."
  type        = string
  default     = "30 6,11,15,20 * * *"
}

variable "agendar" {
  description = "Liga o Scheduler. Deixe desligado até a rotina gerar a lista atual do TSE: cada execução fica no histórico do JSON."
  type        = bool
  default     = false
}

variable "bucket" {
  description = "Bucket onde a rotina publica o JSON; o mesmo de storage.bucket no pipeline-config.json."
  type        = string
  default     = "secoes-comite-popular-tech"
}

variable "image_keep_count" {
  type    = number
  default = 3
}

variable "loki_url" {
  description = "URL do endpoint de push do Loki no Grafana Cloud. Se vazio, o envio fica desligado."
  type        = string
  default     = ""
}

variable "loki_user" {
  description = "Usuário / ID da instância do Loki no Grafana Cloud."
  type        = string
  default     = ""
}
