# Infraestrutura da rotina de dados (GCP)

A rotina (`scripts/gerar_dados.py`) roda como Cloud Run Job no projeto `thech-against-bozo` e publica o JSON
num bucket do Cloud Storage do mesmo projeto, como já fazia antes. O front continua no GitHub Pages.

```
Cloud Scheduler (06:30, 11:30, 15:30, 20:30, America/Sao_Paulo; nasce pausado)
  └─> Cloud Run Job "secoes" (1 vCPU, 2 GiB, até 1 h)
        └─> gs://secoes-comite-popular-tech/secoes_alteradas_2t_2026.json e fontes/
              (leitura pública, CORS de storage-cors.json)
```

| Onde | O que | Quem aplica |
| --- | --- | --- |
| `infra/terraform/` | bucket, Artifact Registry, Job, Scheduler, contas e o provider de WIF | à mão, dono do projeto |
| `.github/workflows/deploy.yml` | build da imagem, troca da imagem do Job e uma execução | à mão (workflow_dispatch) |

Por que a raiz não roda no CI: os módulos do `iac-shared` e o `terraform.yml` do `pipelines-compartilhados` são
privados, e este repositório é público. O Actions daqui só usa a conta de deploy, que não mexe em IAM.

## Primeira vez

1. `terraform -chdir=infra/terraform init && terraform -chdir=infra/terraform apply`. O Job nasce com uma imagem
   pública de exemplo e o Scheduler nasce pausado.
2. Rode o workflow *Deploy da rotina* na `main`: ele publica a imagem, troca a do Job e roda a rotina uma vez.
3. Quando a rotina gerar a lista atual do TSE, ligue o agendamento: `apply -var agendar=true`.

## Depois

- Código da rotina mudou: rode o *Deploy da rotina* (vazio = topo da `main`; um commit antigo volta atrás).
- Infra mudou: `terraform plan` e `apply` à mão, por quem é dono do projeto.

## Logs no Grafana Cloud (Loki)

A rotina envia logs automaticamente para o Grafana Cloud Loki caso as variáveis de ambiente estejam configuradas:

| Variável | Descrição | Exemplo |
| --- | --- | --- |
| `LOKI_URL` | URL do endpoint de push do Loki | `https://logs-prod-xxx.grafana.net/loki/api/v1/push` |
| `LOKI_USER` | Usuário / ID da instância do Loki | `123456` |
| `LOKI_TOKEN` | Token com permissão `logs:write` | `glc_...` |
| `LOKI_LABELS` | *(Opcional)* Labels adicionais | `app=secoes,job=secoes` |

Para configurar no Cloud Run Job existente:

```bash
gcloud run jobs update secoes \
  --region us-central1 \
  --project thech-against-bozo \
  --set-env-vars LOKI_URL="https://logs-prod-xxx.grafana.net/loki/api/v1/push",LOKI_USER="123456" \
  --set-secrets LOKI_TOKEN=secoes-loki-token:latest
```

*Nota:* O envio é fail-safe: se as variáveis estiverem ausentes ou o Grafana Cloud oscilar, a execução continua normalmente logando no `stdout`/Cloud Logging sem interromper o pipeline.
