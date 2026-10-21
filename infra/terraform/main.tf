locals {
  job_sa_id       = substr("${replace(var.job_name, "_", "-")}-sa", 0, 30)
  scheduler_sa_id = substr("${replace(var.job_name, "_", "-")}-sch", 0, 30)

  image = var.image != "" ? var.image : "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}/${var.job_name}:latest"
}

# -----------------------------------------------------------------------------
# 1. Artifact Registry (Repositório Docker)
# -----------------------------------------------------------------------------
resource "google_artifact_registry_repository" "repo" {
  project       = var.project_id
  location      = var.region
  repository_id = var.repository_id
  description   = "Docker repository para imagens do ${var.job_name}"
  format        = "DOCKER"
}

# -----------------------------------------------------------------------------
# 2. Contas de Serviço (Job ETL e Scheduler)
# -----------------------------------------------------------------------------
resource "google_service_account" "job_sa" {
  project      = var.project_id
  account_id   = local.job_sa_id
  display_name = "Service Account para execucao do Cloud Run Job ${var.job_name}"
}

resource "google_service_account" "scheduler_sa" {
  project      = var.project_id
  account_id   = local.scheduler_sa_id
  display_name = "Service Account do Cloud Scheduler para invocar ${var.job_name}"
}

# -----------------------------------------------------------------------------
# 3. Secret Manager (Credenciais do Cloudflare R2)
# -----------------------------------------------------------------------------
resource "google_secret_manager_secret" "r2_account_id" {
  project   = var.project_id
  secret_id = "${var.job_name}-r2-account-id"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "r2_account_id" {
  count       = var.r2_account_id != "" ? 1 : 0
  secret      = google_secret_manager_secret.r2_account_id.id
  secret_data = var.r2_account_id
}

resource "google_secret_manager_secret" "r2_access_key_id" {
  project   = var.project_id
  secret_id = "${var.job_name}-r2-access-key-id"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "r2_access_key_id" {
  count       = var.r2_access_key_id != "" ? 1 : 0
  secret      = google_secret_manager_secret.r2_access_key_id.id
  secret_data = var.r2_access_key_id
}

resource "google_secret_manager_secret" "r2_secret_access_key" {
  project   = var.project_id
  secret_id = "${var.job_name}-r2-secret-access-key"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "r2_secret_access_key" {
  count       = var.r2_secret_access_key != "" ? 1 : 0
  secret      = google_secret_manager_secret.r2_secret_access_key.id
  secret_data = var.r2_secret_access_key
}

resource "google_secret_manager_secret" "r2_bucket_name" {
  project   = var.project_id
  secret_id = "${var.job_name}-r2-bucket-name"

  replication {
    auto {}
  }
}

resource "google_secret_manager_secret_version" "r2_bucket_name" {
  count       = var.r2_bucket_name != "" ? 1 : 0
  secret      = google_secret_manager_secret.r2_bucket_name.id
  secret_data = var.r2_bucket_name
}

# Permissões para o Job ler os segredos
resource "google_secret_manager_secret_iam_member" "job_sa_r2_account_id" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.r2_account_id.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.job_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "job_sa_r2_access_key_id" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.r2_access_key_id.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.job_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "job_sa_r2_secret_access_key" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.r2_secret_access_key.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.job_sa.email}"
}

resource "google_secret_manager_secret_iam_member" "job_sa_r2_bucket_name" {
  project   = var.project_id
  secret_id = google_secret_manager_secret.r2_bucket_name.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = "serviceAccount:${google_service_account.job_sa.email}"
}

# -----------------------------------------------------------------------------
# 4. Cloud Run Job (v2)
# -----------------------------------------------------------------------------
resource "google_cloud_run_v2_job" "job" {
  project             = var.project_id
  location            = var.region
  name                = var.job_name
  deletion_protection = var.deletion_protection

  template {
    template {
      service_account = google_service_account.job_sa.email
      timeout         = "${var.timeout_seconds}s"

      containers {
        image = local.image

        resources {
          limits = {
            cpu    = var.cpu
            memory = var.memory
          }
        }

        env {
          name = "R2_ACCOUNT_ID"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.r2_account_id.secret_id
              version = "latest"
            }
          }
        }

        env {
          name = "R2_ACCESS_KEY_ID"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.r2_access_key_id.secret_id
              version = "latest"
            }
          }
        }

        env {
          name = "R2_SECRET_ACCESS_KEY"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.r2_secret_access_key.secret_id
              version = "latest"
            }
          }
        }

        env {
          name = "R2_BUCKET_NAME"
          value_source {
            secret_key_ref {
              secret  = google_secret_manager_secret.r2_bucket_name.secret_id
              version = "latest"
            }
          }
        }
      }
    }
  }

  depends_on = [
    google_secret_manager_secret_iam_member.job_sa_r2_account_id,
    google_secret_manager_secret_iam_member.job_sa_r2_access_key_id,
    google_secret_manager_secret_iam_member.job_sa_r2_secret_access_key,
    google_secret_manager_secret_iam_member.job_sa_r2_bucket_name,
  ]
}

# -----------------------------------------------------------------------------
# 5. Cloud Scheduler Job (Disparo 4x ao dia)
# -----------------------------------------------------------------------------
resource "google_cloud_scheduler_job" "scheduler" {
  project          = var.project_id
  region           = var.region
  name             = "${var.job_name}-scheduler"
  description      = "Executa periodicamente o Cloud Run Job ${var.job_name}"
  schedule         = var.schedule_cron
  time_zone        = var.time_zone
  attempt_deadline = "320s"

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/projects/${var.project_id}/locations/${var.region}/jobs/${google_cloud_run_v2_job.job.name}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler_sa.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
}

# Permite ao Cloud Scheduler invocar o Cloud Run Job
resource "google_cloud_run_v2_job_iam_member" "scheduler_invoker" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.job.name
  role     = "roles/run.invoker"
  member   = "serviceAccount:${google_service_account.scheduler_sa.email}"
}
