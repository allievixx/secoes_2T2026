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

output "segredos_r2" {
  description = "Segredos que recebem a versão à mão (infra/README.md)."
  value       = { for nome, s in google_secret_manager_secret.r2 : nome => s.secret_id }
}
