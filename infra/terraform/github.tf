# Deploy pelo GitHub Actions sem chave JSON: Workload Identity Federation.
# O pool "github" é do Terraform do rapa-agenda; aqui só entra um provider para este repositório.
# Só a main vira a conta de deploy, que publica a imagem e troca a do Job; nada aqui aplica Terraform.

data "google_iam_workload_identity_pool" "github" {
  project                   = var.project_id
  workload_identity_pool_id = "github"
}

resource "google_iam_workload_identity_pool_provider" "github" {
  project                            = var.project_id
  workload_identity_pool_id          = data.google_iam_workload_identity_pool.github.workload_identity_pool_id
  workload_identity_pool_provider_id = var.name

  attribute_mapping = {
    "google.subject"       = "assertion.sub"
    "attribute.repository" = "assertion.repository"
    "attribute.ref"        = "assertion.ref"
    "attribute.repo_ref"   = "assertion.repository + '@' + assertion.ref"
  }
  attribute_condition = "assertion.repository == '${var.github_repo}'"

  oidc {
    issuer_uri = "https://token.actions.githubusercontent.com"
  }
}

resource "google_service_account" "deployer" {
  project      = var.project_id
  account_id   = "${var.name}-deployer"
  display_name = "${var.name}: deploy via GitHub Actions"
}

# O pool é compartilhado: o vínculo nomeia o repositório e a main, senão outro repositório do pool vira a conta.
resource "google_service_account_iam_member" "github_usa_deployer" {
  service_account_id = google_service_account.deployer.name
  role               = "roles/iam.workloadIdentityUser"
  member             = "principalSet://iam.googleapis.com/${data.google_iam_workload_identity_pool.github.name}/attribute.repo_ref/${var.github_repo}@refs/heads/main"
}

resource "google_artifact_registry_repository_iam_member" "deployer_publica" {
  project    = var.project_id
  location   = var.region
  repository = google_artifact_registry_repository.imagens.repository_id
  role       = "roles/artifactregistry.writer"
  member     = google_service_account.deployer.member
}

resource "google_cloud_run_v2_job_iam_member" "deployer_atualiza_job" {
  project  = var.project_id
  location = var.region
  name     = google_cloud_run_v2_job.job.name
  role     = "roles/run.developer"
  member   = google_service_account.deployer.member
}

# As execuções não herdam o IAM do Job; sem isto o `jobs execute --wait` não acompanha a execução.
resource "google_project_iam_member" "deployer_acompanha_execucoes" {
  project = var.project_id
  role    = "roles/run.viewer"
  member  = google_service_account.deployer.member
}

resource "google_service_account_iam_member" "deployer_usa_conta_do_job" {
  service_account_id = google_service_account.job.name
  role               = "roles/iam.serviceAccountUser"
  member             = google_service_account.deployer.member
}
