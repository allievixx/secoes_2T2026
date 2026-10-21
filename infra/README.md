# Infraestrutura da rotina de dados (GCP + Cloudflare R2)

A rotina (`scripts/gerar_dados.py`) roda como Cloud Run Job no projeto `thech-against-bozo` e grava o JSON num
bucket R2. O front continua no GitHub Pages.

```
Cloud Scheduler (06:30, 11:30, 15:30, 20:30, America/Sao_Paulo)
  └─> Cloud Run Job "secoes" (1 vCPU, 2 GiB, até 1 h; credenciais do R2 pelo Secret Manager)
        └─> R2 "secoes": secoes_alteradas_2t_2026.json e fontes/
              └─> domínio público de leitura, com CORS para o Pages
```

| Onde | O que | Quem aplica |
| --- | --- | --- |
| `infra/terraform/` | Artifact Registry, Job, Scheduler, segredos (sem valor), contas e o provider de WIF | à mão, dono do projeto |
| `.github/workflows/deploy.yml` | build da imagem, troca da imagem do Job e uma execução | à mão (workflow_dispatch) |
| Cloudflare (painel) | bucket R2, domínio de leitura, CORS e o token de escrita | à mão, conta da Cloudflare |

Por que a raiz não roda no CI: os módulos do `iac-shared` e o `terraform.yml` do `pipelines-compartilhados` são
privados, e este repositório é público. O Actions daqui só usa a conta de deploy, que não mexe em IAM.

## Primeira vez

1. **Cloudflare:** crie o bucket R2 `secoes`, ligue um domínio público de leitura a ele e a regra de CORS (GET da
   origem do Pages). Gere um token de API do R2 com *Object Read & Write* só nesse bucket.
2. **Segredos (vazios):**
   `terraform -chdir=infra/terraform init && terraform -chdir=infra/terraform apply -target=google_secret_manager_secret.r2`
3. **Valores dos segredos**, um por vez, colando o valor quando o terminal pedir (nada vai para o estado nem para o
   histórico do shell):
   `gcloud secrets versions add secoes-r2-account-id --project=thech-against-bozo --data-file=-`
   (o mesmo para `secoes-r2-access-key-id` e `secoes-r2-secret-access-key`; termine cada um com Ctrl+D).
4. **O resto:** `terraform -chdir=infra/terraform apply`. O Job nasce com uma imagem pública de exemplo e o
   Scheduler nasce pausado.
5. **Deploy:** rode o workflow *Deploy da rotina* na `main`. Ele publica a imagem, troca a do Job e roda a rotina
   uma vez.
6. **Agendamento:** quando a rotina gerar a lista atual do TSE, aplique com `-var agendar=true`.

## Depois

- Código da rotina mudou: rode o *Deploy da rotina* (vazio = topo da `main`; um commit antigo volta atrás).
- Infra mudou: `terraform plan` e `apply` à mão, por quem é dono do projeto.
- Token do R2 trocado: só o passo 3, com o valor novo; a próxima execução já usa a versão `latest`.
