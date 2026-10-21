# Infraestrutura e CI/CD de Seções 2º Turno 2026 (GCP + Cloudflare R2)

Infraestrutura como código (**Terraform**) e automação (**GitHub Actions**) para hospedar e executar a rotina de dados de seções eleitorais alteradas no 2º turno das Eleições 2026.

Integrado ao ecossistema corporativo da organização **[`comite-popular-tech/pipelines-compartilhados`](https://github.com/comite-popular-tech/pipelines-compartilhados)**:
- **IaC versionado** em `infra/terraform/` (`>= 1.6`, Google Provider `~> 6.0`).
- **Workflow reutilizável de Terraform:** Chama diretamente `comite-popular-tech/pipelines-compartilhados/.github/workflows/terraform.yml@v1`.
- **Autenticação segura via Workload Identity Federation (WIF):** Sem necessidade de chaves JSON estáticas de contas de serviço.
- **Proteção de Forks:** Em pull requests de forks, apenas a validação offline (`fmt` e `validate`) executa; a infraestrutura real e os segredos nunca são expostos.
- **Segredos fora do Git:** As credenciais do Cloudflare R2 residem com segurança no **GCP Secret Manager** e são montadas como variáveis de ambiente no container.

---

## Arquitetura

```
┌────────────────────────────────────────┐
│ Cloudflare (R2)                        │
│   • Bucket R2 Privado                  │
│   • Custom Domain / CDN Proxy          │
└───────────────────▲────────────────────┘
                    │ Grava JSON via S3 API
┌───────────────────┴────────────────────┐      ┌─────────────────────────┐
│ GCP (Cloud Run Jobs: thech-against-bozo│◄─────│ Cloud Scheduler         │
│   • Imagem Docker (Python 3.11 + uv)   │      │   • 4x ao dia           │
│   • 2 GiB RAM / 1 vCPU                 │      │   • America/Sao_Paulo   │
│   • Segredos R2 via Secret Manager     │      └─────────────────────────┘
└────────────────────────────────────────┘
```

---

## Estrutura de Pastas

```
infra/
  README.md            este documento
  terraform/           definição dos recursos (Cloud Run Job, Scheduler, Secret Manager, Artifact Registry)
    main.tf
    variables.tf
    outputs.tf
    versions.tf
    .terraform.lock.hcl (sempre versionado no Git)
tools/
  conferir_isolamento.py   trava de segurança contra targets de produção indevidos
tests/
  test_conferir_isolamento.py   testes unitários da trava
.github/workflows/
  testes.yml           action tamanho-do-pr + lint + typecheck + testes frontend e python (sem segredos)
  infra.yml            chama o workflow reutilizável terraform.yml de pipelines-compartilhados
  pages.yml            deploy contínuo do frontend estático no GitHub Pages
```

---

## O que o Terraform cria (`infra/terraform/`)

| Recurso | Arquivo | Descrição |
|---|---|---|
| Artifact Registry | `main.tf` | Repositório Docker para as imagens do job `secoes-etl` |
| Service Account Job | `main.tf` | Identidade do container com permissão `roles/secretmanager.secretAccessor` |
| Service Account Scheduler | `main.tf` | Identidade do agendador com permissão `roles/run.invoker` |
| Secret Manager | `main.tf` | 4 segredos (`r2-account-id`, `r2-access-key-id`, `r2-secret-access-key`, `r2-bucket-name`) |
| Cloud Run Job v2 | `main.tf` | Job com 2 GiB de memória, timeout de 1h e segredos montados como variáveis de ambiente |
| Cloud Scheduler | `main.tf` | Agendamento às 06:30, 11:30, 15:30 e 20:30 (`America/Sao_Paulo`) via HTTP POST autenticado |

---

## Variáveis e Segredos (Configuração no GitHub)

O pipeline usa as variáveis corporativas da organização `comite-popular-tech`:
- `TF_ESTADO_BUCKET`: Nome do bucket GCS para armazenar o estado do Terraform (`prefix=secoes`).
- `GCP_WIF_PROVIDER`: Provider do Workload Identity Federation (`projects/.../locations/global/workloadIdentityPools/.../providers/...`).
- `GCP_SA_TERRAFORM_PLANO`: Conta de serviço para executar o plano em PRs.
- `GCP_SA_TERRAFORM`: Conta de serviço com permissão de escrita para o apply na branch `main`.

No Environment **`producao`**:
- `R2_ACCOUNT_ID`
- `R2_ACCESS_KEY_ID`
- `R2_SECRET_ACCESS_KEY`
- `R2_BUCKET_NAME`

---

## Validações Locais

```bash
# Validar formatação do Terraform
terraform fmt -check -recursive infra/terraform

# Validar sintaxe
terraform -chdir=infra/terraform init -backend=false
terraform -chdir=infra/terraform validate

# Testar a trava de isolamento
python3 -m unittest tests/test_conferir_isolamento.py
```
