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
  description = "Liga o Scheduler. Deixe desligado até a rotina gerar a lista atual do TSE: cada execução fica no histórico do R2."
  type        = bool
  default     = false
}

variable "r2_bucket" {
  description = "Bucket R2 onde a rotina grava o JSON (não é segredo)."
  type        = string
  default     = "secoes"
}

variable "image_keep_count" {
  type    = number
  default = 3
}
