# Cloud Storage e Cloud Run

## Fluxo de dados

O dashboard do GitHub Pages não consulta BigQuery nem usa credenciais Google. A rotina busca as fontes oficiais, valida e transforma os dados e acrescenta um snapshot completo ao histórico `{"snapshots":[{"extracted_at":"...","rows":[...]}]}` diretamente em:

`gs://extracao_alteracao_locais_votacao/secoes_alteradas_2t_2026.json`

O bucket e o objeto são definidos no bloco `storage` de [pipeline-config.json](../pipeline-config.json). A rotina só faz upload depois que geração e validação terminam. Uma falha de upload deixa o objeto anterior intacto. Linhas vazias são recusadas. Cada execução guarda a extração completa com seu instante UTC, sem descartar execuções anteriores. O formato legado `{"rows":[...]}` é migrado no primeiro upload, usando a data de atualização do objeto no Cloud Storage.

### Cópias das fontes do TSE

O TSE sobrescreve seus ZIPs na mesma URL, então a versão usada em cada carga se perderia. Antes de publicar o snapshot, a rotina arquiva no bucket uma cópia dos arquivos-fonte listados em `storage.archiveSources` (padrão `["changes"]`, a lista de seções alteradas; o cadastro de locais tem ~170 MB por versão e não é arquivado por padrão), sob `storage.archivePrefix` (padrão `fontes`):

`gs://extracao_alteracao_locais_votacao/fontes/changes/<Last-Modified em UTC>-<sha256[:12]>-secoes_eleitorais_alteradas_2t-pais_2026.csv.zip`

Há uma cópia por versão: se um objeto com o mesmo SHA-256 (metadado `sha256`) já existe na pasta, nada é reenviado. Os metadados do objeto guardam URL de origem, `Last-Modified`, `ETag` e instante do download. O caminho arquivado entra em `sources.<fonte>.archived` no snapshot e em `source_versions` no relatório. Uma falha no arquivamento é registrada em `falhas_arquivamento` no relatório e no log, mas não impede a publicação do dashboard. Como o bucket é público, as cópias também são — são dados públicos do TSE.

[dashboard-config.json](../dashboard-config.json) aponta para a URL pública do objeto. O bucket permite leitura pública e CORS `GET` para o GitHub Pages e para os servidores locais `http://localhost:8080` e `http://127.0.0.1:8080`, configurados em [storage-cors.json](../storage-cors.json). A configuração atual do bucket informa `public_access_prevention: inherited`; a política efetiva do projeto não impõe prevenção, mas confirme esse estado se a política da organização mudar. Não publique dados que não possam ser públicos.

## Ambiente local

Instale [uv](https://docs.astral.sh/uv/) e rode na raiz do repositório:

```sh
uv sync
uv run python scripts/gerar_dados.py
```

O ambiente local precisa de Application Default Credentials com permissão `roles/storage.objectUser` no bucket. Para autenticar com a conta de usuário local, use `gcloud auth application-default login`; isso é independente do `gcloud auth login`.

## Deploy como Cloud Run Job

O [Dockerfile](../Dockerfile) usa Python 3.11 e `uv sync --locked`. A imagem não instala nem usa a CLI `bq`. Os comandos abaixo usam o projeto ativo do `gcloud`; informe uma região válida para Cloud Run:

```powershell
$PROJECT = "comite-tecnologia"
$REGION = "us-central1"
$REPOSITORY = "secoes"
$IMAGE = "$REGION-docker.pkg.dev/$PROJECT/$REPOSITORY/secoes-etl"
$SERVICE_ACCOUNT = "secoes-etl@$PROJECT.iam.gserviceaccount.com"

gcloud config set project $PROJECT
gcloud services enable run.googleapis.com cloudbuild.googleapis.com artifactregistry.googleapis.com cloudscheduler.googleapis.com
gcloud artifacts repositories create $REPOSITORY --repository-format=docker --location=$REGION
gcloud iam service-accounts create secoes-etl --display-name="Cloud Run sections snapshot job"
gcloud storage buckets add-iam-policy-binding gs://extracao_alteracao_locais_votacao --member="serviceAccount:$SERVICE_ACCOUNT" --role=roles/storage.objectUser
gcloud storage buckets add-iam-policy-binding gs://extracao_alteracao_locais_votacao --member=allUsers --role=roles/storage.objectViewer
gcloud storage buckets update gs://extracao_alteracao_locais_votacao --cors-file=storage-cors.json
gcloud builds submit --tag $IMAGE .
gcloud run jobs deploy secoes-etl --image $IMAGE --region $REGION --service-account $SERVICE_ACCOUNT --task-timeout 1h
```

Os comandos de criação e IAM são necessários somente na primeira implantação. A conta de serviço recebe `roles/storage.objectUser` no bucket. O binding `allUsers` torna os objetos do bucket publicamente legíveis. A conta que implanta também precisa de permissão para anexar a conta de serviço ao job.
O job está configurado com `allowIncomplete: true` para publicar registros mesmo quando faltam detalhes de local; os campos sem fonte ficam `null`.

Depois do deploy, execute manualmente para validar:

```powershell
gcloud run jobs execute secoes-etl --region $REGION --wait
```

A execução baixa arquivos oficiais grandes; aumente memória e tempo limite do job conforme necessário depois de observar o primeiro run. A execução manual substitui o JSON publicado, portanto só a faça quando quiser atualizar o dashboard.

## Agendamento

O Cloud Scheduler está configurado para **06:30, 11:30, 15:30 e 20:30**, no fuso `America/Sao_Paulo` (cron `30 6,11,15,20 * * *`). A identidade `secoes-scheduler@comite-tecnologia.iam.gserviceaccount.com` tem `roles/run.invoker` no job. Para recriar o agendamento:

```powershell
gcloud iam service-accounts create secoes-scheduler --display-name="Cloud Scheduler invoker for sections job"
gcloud run jobs add-iam-policy-binding secoes-etl --region $REGION --member="serviceAccount:secoes-scheduler@$PROJECT.iam.gserviceaccount.com" --role=roles/run.invoker
gcloud scheduler jobs create http secoes-etl-4x-daily --location=$REGION --schedule="30 6,11,15,20 * * *" --time-zone="America/Sao_Paulo" --uri="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/secoes-etl:run" --http-method=POST --oauth-service-account-email="secoes-scheduler@$PROJECT.iam.gserviceaccount.com" --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" --max-retry-attempts=1 --attempt-deadline=180s
```

Não é necessário manter um serviço HTTP ligado: o Cloud Run Job encerra ao concluir.
