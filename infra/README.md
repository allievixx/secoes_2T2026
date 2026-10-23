# Infraestrutura da rotina de dados (GCP)

## Produção

A rotina (`scripts/gerar_dados.py`) roda como Cloud Run Job no projeto `comite-tecnologia`. O front continua no
GitHub Pages (`.github/workflows/pages.yml`).

```
Cloud Scheduler "secoes-etl-4x-daily" (06:30, 11:30, 15:30, 20:30, America/Sao_Paulo)
  └─> Cloud Run Job "secoes-etl" (us-central1, 2 vCPU, 4 GiB, até 1 h, SA secoes-etl@)
        └─> gs://extracao_alteracao_locais_votacao/secoes_alteradas_2t_2026.json e fontes/
```

Esses recursos foram criados à mão e não estão no Terraform deste repositório.

## Deploy (só manual)

Não há deploy pelo GitHub Actions. O deploy sai sempre de um commit da `main`, empacotado com `git archive`: assim a
imagem tem exatamente o que está no git, sem arquivos locais soltos. A tag da imagem é o SHA do commit.

```bash
git fetch origin && git switch --detach origin/main      # ou o commit a publicar / voltar atrás
SHA=$(git rev-parse --short HEAD)
IMAGEM=us-central1-docker.pkg.dev/comite-tecnologia/secoes/secoes-etl:$SHA
git archive --format=tar.gz -o /tmp/secoes-$SHA.tgz HEAD
gcloud builds submit /tmp/secoes-$SHA.tgz --tag "$IMAGEM" --project=comite-tecnologia
gcloud run jobs update secoes-etl --image="$IMAGEM" --region=us-central1 --project=comite-tecnologia
gcloud run jobs execute secoes-etl --region=us-central1 --project=comite-tecnologia --wait   # opcional: roda agora
```

Para rodar a rotina fora do agendamento, com a imagem atual, use só o último comando.

## Terraform (`infra/terraform/`)

O Terraform daqui descreve uma instalação anterior no projeto `thech-against-bozo` (Job `secoes`, bucket
`secoes-comite-popular-tech`, Scheduler, conta `secoes-deployer` e provider de WIF), **não** a produção acima.
Ele é aplicado à mão, por quem é dono daquele projeto: `terraform plan` e `apply`.

Por que a raiz não roda no CI: os módulos do `iac-shared` e o `terraform.yml` do `pipelines-compartilhados` são
privados, e este repositório é público.

## Logs no Grafana Cloud (Loki)

O Terraform habilita a API do Secret Manager, provisiona o segredo `secoes-loki-token` (sem versão) e concede `roles/secretmanager.secretAccessor` à service account do Job (`secoes-job`).

### Como ativar:

1. **Adicionar o valor do token no Secret Manager:**
   ```bash
   echo -n "<token_do_grafana>" | gcloud secrets versions add secoes-loki-token \
     --project thech-against-bozo \
     --data-file=-
   ```

2. **Aplicar o Terraform com as variáveis do Loki:**
   ```bash
   terraform -chdir=infra/terraform apply \
     -var loki_url="https://logs-prod-xxx.grafana.net/loki/api/v1/push" \
     -var loki_user="123456"
   ```

Se `loki_url` estiver vazia (padrão), o Job não monta as variáveis e o Loki permanece desligado.

*Nota:* O envio é fail-safe: se as variáveis estiverem ausentes ou o Grafana Cloud oscilar, a rotina continua normalmente logando no `stdout`/Cloud Logging sem interromper o pipeline.
