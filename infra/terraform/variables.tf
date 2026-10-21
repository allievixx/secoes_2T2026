variable "project_id" {
  description = "ID do projeto GCP de destino (padrão: thech-against-bozo)."
  type        = string
  default     = "thech-against-bozo"
}

variable "region" {
  description = "Região do GCP (padrão: us-central1)."
  type        = string
  default     = "us-central1"
}

variable "job_name" {
  description = "Nome do Cloud Run Job e prefixo das Service Accounts."
  type        = string
  default     = "secoes-etl"
}

variable "repository_id" {
  description = "ID do repositório no Artifact Registry para as imagens Docker."
  type        = string
  default     = "secoes"
}

variable "image" {
  description = "URI completa da imagem Docker. Se omitida, deriva a tag :latest do Artifact Registry."
  type        = string
  default     = ""
}

variable "schedule_cron" {
  description = "Expressão cron para o Cloud Scheduler (padrão: 4x ao dia)."
  type        = string
  default     = "30 6,11,15,20 * * *"
}

variable "time_zone" {
  description = "Fuso horário do Cloud Scheduler."
  type        = string
  default     = "America/Sao_Paulo"
}

variable "cpu" {
  description = "CPU alocada para o container do Cloud Run Job."
  type        = string
  default     = "1"
}

variable "memory" {
  description = "Memória alocada para o container do Cloud Run Job."
  type        = string
  default     = "2Gi"
}

variable "timeout_seconds" {
  description = "Timeout máximo de execução do job em segundos."
  type        = number
  default     = 3600
}

variable "deletion_protection" {
  description = "Protege o Cloud Run Job contra destruição acidental."
  type        = bool
  default     = true
}

variable "r2_account_id" {
  description = "Cloudflare Account ID para acesso ao R2."
  type        = string
  default     = ""
  sensitive   = true
}

variable "r2_access_key_id" {
  description = "Cloudflare R2 Access Key ID."
  type        = string
  default     = ""
  sensitive   = true
}

variable "r2_secret_access_key" {
  description = "Cloudflare R2 Secret Access Key."
  type        = string
  default     = ""
  sensitive   = true
}

variable "r2_bucket_name" {
  description = "Nome do bucket Cloudflare R2 onde o JSON do dashboard será gravado."
  type        = string
  default     = ""
  sensitive   = true
}
