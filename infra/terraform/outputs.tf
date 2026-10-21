output "wif_provider" {
  description = "workload_identity_provider do deploy.yml."
  value       = google_iam_workload_identity_pool_provider.github.name
}

output "conta_deploy" {
  value = google_service_account.deployer.email
}

output "imagens" {
  value = "${var.region}-docker.pkg.dev/${var.project_id}/${google_artifact_registry_repository.imagens.repository_id}"
}

output "dados_url" {
  description = "URL pública do JSON."
  value       = "https://storage.googleapis.com/${google_storage_bucket.dados.name}/secoes_alteradas_2t_2026.json"
}
