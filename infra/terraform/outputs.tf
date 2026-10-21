output "job_name" {
  description = "Nome do Cloud Run Job."
  value       = google_cloud_run_v2_job.job.name
}

output "job_id" {
  description = "ID do Cloud Run Job."
  value       = google_cloud_run_v2_job.job.id
}

output "artifact_registry_repository" {
  description = "Nome do repositório Docker no Artifact Registry."
  value       = google_artifact_registry_repository.repo.name
}

output "artifact_registry_uri" {
  description = "URI base do repositório no Artifact Registry para docker push."
  value       = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.repo.repository_id}"
}

output "job_service_account" {
  description = "Email da Service Account utilizada pelo Cloud Run Job."
  value       = google_service_account.job_sa.email
}

output "scheduler_service_account" {
  description = "Email da Service Account utilizada pelo Cloud Scheduler."
  value       = google_service_account.scheduler_sa.email
}

output "scheduler_job_name" {
  description = "Nome do Cloud Scheduler Job."
  value       = google_cloud_scheduler_job.scheduler.name
}
