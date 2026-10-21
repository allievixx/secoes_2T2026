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
  description = "Liga o Scheduler. Ligado desde 21/10, quando a rotina gerou a lista atual do TSE. Numa instalação nova, use false até isso acontecer: cada execução fica no histórico do JSON."
  type        = bool
  default     = true
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
