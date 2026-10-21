locals {
  labels = { app = var.name }

  apis = toset([
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "secretmanager.googleapis.com",
  ])

  # Credenciais do R2: o Terraform cria só o segredo, sem valor; a versão entra à mão (infra/README.md),
  # para a chave não passar pelo estado.
  r2_secrets = {
    R2_ACCOUNT_ID        = "${var.name}-r2-account-id"
    R2_ACCESS_KEY_ID     = "${var.name}-r2-access-key-id"
    R2_SECRET_ACCESS_KEY = "${var.name}-r2-secret-access-key"
  }
}

resource "google_project_service" "apis" {
  for_each           = local.apis
  project            = var.project_id
  service            = each.value
  disable_on_destroy = false
}

# --- Imagens -------------------------------------------------------------------

resource "google_artifact_registry_repository" "imagens" {
  project       = var.project_id
  repository_id = var.name
  location      = var.region
  format        = "DOCKER"
  labels        = local.labels

  cleanup_policy_dry_run = false
  cleanup_policies {
    id     = "manter-recentes"
    action = "KEEP"
    most_recent_versions {
      keep_count = var.image_keep_count
    }
  }
  cleanup_policies {
    id     = "apagar-antigas"
    action = "DELETE"
    condition {
      tag_state  = "ANY"
      older_than = "86400s"
    }
  }

  depends_on = [google_project_service.apis]
}

# --- Segredos ------------------------------------------------------------------

resource "google_secret_manager_secret" "r2" {
  for_each  = local.r2_secrets
  project   = var.project_id
  secret_id = each.value
  labels    = local.labels

  replication {
    auto {}
  }

  depends_on = [google_project_service.apis]
}

resource "google_secret_manager_secret_iam_member" "job_le_r2" {
  for_each  = google_secret_manager_secret.r2
  project   = var.project_id
  secret_id = each.value.secret_id
  role      = "roles/secretmanager.secretAccessor"
  member    = google_service_account.job.member
}

# --- Job e agendamento ---------------------------------------------------------

resource "google_service_account" "job" {
  project      = var.project_id
  account_id   = "${var.name}-job"
  display_name = "${var.name}: Cloud Run Job"
  depends_on   = [google_project_service.apis]
}

resource "google_service_account" "scheduler" {
  project      = var.project_id
  account_id   = "${var.name}-scheduler"
  display_name = "${var.name}: Cloud Scheduler que dispara o Job"
  depends_on   = [google_project_service.apis]
}

resource "google_cloud_run_v2_job" "job" {
  project             = var.project_id
  name                = var.name
  location            = var.region
  labels              = local.labels
  deletion_protection = false

  template {
    task_count  = 1
    parallelism = 1

    template {
      service_account = google_service_account.job.email
      timeout         = "3600s"
      max_retries     = 0

      containers {
        # Imagem pública só para criar o Job: o deploy.yml troca pela do Artifact Registry.
        image = "us-docker.pkg.dev/cloudrun/container/job:latest"

        resources {
          limits = {
            cpu    = "1"
            memory = "2Gi"
          }
        }

        env {
          name  = "R2_BUCKET_NAME"
          value = var.r2_bucket
        }

        dynamic "env" {
          for_each = google_secret_manager_secret.r2
          content {
            name = env.key
            value_source {
              secret_key_ref {
                secret  = env.value.secret_id
                version = "latest"
              }
            }
          }
        }
      }
    }
  }

  lifecycle {
    ignore_changes = [
      template[0].template[0].containers[0].image,
      client,
      client_version,
    ]
  }

  depends_on = [google_secret_manager_secret_iam_member.job_le_r2]
}

resource "google_cloud_scheduler_job" "job" {
  project          = var.project_id
  region           = var.region
  name             = var.name
  schedule         = var.schedule
  time_zone        = "America/Sao_Paulo"
  attempt_deadline = "180s"
  paused           = !var.agendar

  retry_config {
    retry_count = 1
  }

  http_target {
    http_method = "POST"
    uri         = "https://run.googleapis.com/v2/${google_cloud_run_v2_job.job.id}:run"

    oauth_token {
      service_account_email = google_service_account.scheduler.email
      scope                 = "https://www.googleapis.com/auth/cloud-platform"
    }
  }
}

resource "google_cloud_run_v2_job_iam_member" "scheduler_dispara" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.job.name
  role     = "roles/run.invoker"
  member   = google_service_account.scheduler.member
}
