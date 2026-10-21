locals {
  labels = { app = var.name }

  apis = toset([
    "artifactregistry.googleapis.com",
    "cloudscheduler.googleapis.com",
    "iam.googleapis.com",
    "run.googleapis.com",
    "storage.googleapis.com",
  ])
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

# --- Dados ---------------------------------------------------------------------
# O JSON que a rotina publica (pipeline-config.json, storage.bucket), com leitura pública e o CORS do
# storage-cors.json, como o bucket de antes.

resource "google_storage_bucket" "dados" {
  project                     = var.project_id
  name                        = var.bucket
  location                    = var.region
  uniform_bucket_level_access = true
  public_access_prevention    = "inherited"
  labels                      = local.labels

  dynamic "cors" {
    for_each = jsondecode(file("${path.module}/../../storage-cors.json"))
    content {
      origin          = cors.value.origin
      method          = cors.value.method
      response_header = cors.value.responseHeader
      max_age_seconds = cors.value.maxAgeSeconds
    }
  }

  depends_on = [google_project_service.apis]
}

resource "google_storage_bucket_iam_member" "leitura_publica" {
  bucket = google_storage_bucket.dados.name
  role   = "roles/storage.objectViewer"
  member = "allUsers"
}

resource "google_storage_bucket_iam_member" "job_publica" {
  bucket = google_storage_bucket.dados.name
  role   = "roles/storage.objectUser"
  member = google_service_account.job.member
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

  depends_on = [google_storage_bucket_iam_member.job_publica]
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
