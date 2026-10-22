# Cloud Storage e Cloud Run

## Fluxo de dados

O dashboard do GitHub Pages não consulta BigQuery nem usa credenciais Google. A rotina busca as fontes oficiais, valida e transforma os dados e acrescenta um snapshot completo ao histórico `{"snapshots":[{"extracted_at":"...","rows":[...]}]}` diretamente em:

`gs://extracao_alteracao_locais_votacao/secoes_alteradas_2t_2026.json`

O bucket e o objeto são definidos no bloco `storage` de [pipeline-config.json](../pipeline-config.json). A rotina só faz upload depois que geração e validação terminam. Uma falha de upload deixa o objeto anterior intacto. Linhas vazias são recusadas. Cada execução guarda a extração completa com seu instante UTC, sem descartar execuções anteriores. O formato legado `{"rows":[...]}` é migrado no primeiro upload, usando a data de atualização do objeto no Cloud Storage.

### Cópias das fontes do TSE

O TSE sobrescreve seus ZIPs na mesma URL, então a versão usada em cada carga se perderia. Antes de publicar o snapshot, a rotina arquiva no bucket uma cópia dos arquivos-fonte listados em `storage.archiveSources` (padrão `["changes"]`, a lista de seções alteradas; o cadastro de locais tem ~170 MB por versão e não é arquivado por padrão), sob `storage.archivePrefix` (padrão `fontes`):

`gs://extracao_alteracao_locais_votacao/fontes/changes/<Last-Modified em UTC>-<sha256[:12]>-secoes_eleitorais_alteradas_2t-pais_2026.csv.zip`

Há uma cópia por versão: se um objeto com o mesmo SHA-256 (metadado `sha256`) já existe na pasta, nada é reenviado. Os metadados do objeto guardam URL de origem, `Last-Modified`, `ETag` e instante do download. O caminho arquivado entra em `sources.<fonte>.archived` no snapshot e em `source_versions` no relatório. Uma falha no arquivamento é registrada em `falhas_arquivamento` no relatório e no log, mas não impede a publicação do dashboard. Como o bucket é público, as cópias também são — são dados públicos do TSE.

### Catálogo IBGE versionado

`sources.municipalities` aponta explicitamente para a cópia de 22/10/2026 no Cloud Storage, em `fontes/municipalities/20261022-d9eec8439bc8c5dc2f7db6332a8e5569f5a3f637988e26aebc513412d4069d5c-municipios.json`. O catálogo foi obtido da API oficial por HTTPS, validado com `load_ibge` (5.571 códigos únicos e 27 UFs) e publicado sem sobrescrever um objeto existente.

O SHA-256 é `d9eec8439bc8c5dc2f7db6332a8e5569f5a3f637988e26aebc513412d4069d5c`. Os metadados do objeto registram a URL oficial de origem, data de coleta, hash e contagens. O snapshot registra a URL da cópia e o hash efetivamente baixado em `sources.municipalities`.

A rotina não consulta a API do IBGE em cada execução nem faz fallback silencioso. Se a cópia estiver inacessível ou inválida, a publicação falha. A descoberta da fonte vigente do TSE permanece inalterada. Para atualizar o catálogo, obtenha uma nova cópia oficial, valide os códigos e UFs, publique em outro caminho com data e hash e altere explicitamente `sources.municipalities` antes do deploy. Não sobrescreva a versão anterior.

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
gcloud run jobs deploy secoes-etl --image $IMAGE --region $REGION --service-account $SERVICE_ACCOUNT --cpu 2 --memory 4Gi --task-timeout 1h
```

Os comandos de criação e IAM são necessários somente na primeira implantação. A conta de serviço recebe `roles/storage.objectUser` no bucket. O binding `allUsers` torna os objetos do bucket publicamente legíveis. A conta que implanta também precisa de permissão para anexar a conta de serviço ao job.
O job está configurado com `allowIncomplete: true` para publicar registros mesmo quando faltam detalhes de local; os campos sem fonte ficam `null`. Locais ambíguos também são registrados como pendências: nenhuma coordenada é escolhida arbitrariamente, os dados seguros da seção e os votos são preservados, e a distância permanece vazia quando falta uma coordenada. Com `allowIncomplete: false`, a ambiguidade continua bloqueando a publicação.

A exportação do TSE pode incluir seções sem `NM_LOCAL_VOTACAO_FINAL` (como em 22/10/2026: 517.179 linhas, das quais 326 com destino informado). Essas linhas são excluídas da lista de alterações antes de montar os índices do cadastro e consultar os votos; as contagens ficam no log. Se nenhuma alteração com destino informado restar, a rotina falha e preserva o JSON anterior.

Downloads HTTP(S) fazem até três tentativas em caso de timeout de conexão, handshake TLS ou leitura, com esperas de 2 e 4 segundos. Cada nova tentativa é registrada com a URL e o motivo; downloads parciais são removidos. A validação dos certificados continua habilitada, e erros de certificado ou respostas HTTP de erro não são repetidos. Se os timeouts persistirem, a execução falha sem publicar nem usar o cache antigo como fallback. Esse tratamento cobre a falha das 11h30 de 22/10/2026, quando o handshake HTTPS com `servicodados.ibge.gov.br` excedeu 120 segundos.

Depois do deploy, execute manualmente para validar:

```powershell
gcloud run jobs execute secoes-etl --region $REGION --wait
```

A execução baixa arquivos oficiais grandes. Em 22/10/2026, dois encerramentos com código 137 levaram a um teste com 8 GiB. A causa era a inclusão das linhas sem local final na exportação nacional: o processamento passou de centenas para mais de 500 mil seções. Após corrigir a seleção, o job `secoes-etl` em `comite-tecnologia/us-central1` voltou aos 4 GiB originais, mantendo 2 vCPUs. O filesystem gravável do Cloud Run também consome a memória do container; monitore o consumo ao mudar as fontes ou a imagem.

A imagem `fix-national-export-20261022` foi construída a partir da fonte da imagem anterior de produção, preservando a descoberta automática no TSE e o arquivamento das quatro fontes. A execução `secoes-etl-t8q27` concluiu com código 0 e publicou 326 alterações às 11:06 de 22/10/2026 (Brasília), preservando os snapshots anteriores. A maior amostra de memória disponível foi de aproximadamente 0,57 GiB. Restaram quatro pendências de local final ausente no cadastro, publicadas com os campos de enriquecimento vazios conforme `allowIncomplete`.

Para atualizar somente os recursos, sem substituir a imagem em produção:

```powershell
gcloud run jobs update secoes-etl --project=comite-tecnologia --region=us-central1 --cpu=2 --memory=4Gi
```

A execução manual acrescenta um snapshot ao histórico publicado, portanto só a faça quando quiser atualizar o dashboard.

## Agendamento

O Cloud Scheduler está configurado para **06:30, 11:30, 15:30 e 20:30**, no fuso `America/Sao_Paulo` (cron `30 6,11,15,20 * * *`). A identidade `secoes-scheduler@comite-tecnologia.iam.gserviceaccount.com` tem `roles/run.invoker` no job. Para recriar o agendamento:

```powershell
gcloud iam service-accounts create secoes-scheduler --display-name="Cloud Scheduler invoker for sections job"
gcloud run jobs add-iam-policy-binding secoes-etl --region $REGION --member="serviceAccount:secoes-scheduler@$PROJECT.iam.gserviceaccount.com" --role=roles/run.invoker
gcloud scheduler jobs create http secoes-etl-4x-daily --location=$REGION --schedule="30 6,11,15,20 * * *" --time-zone="America/Sao_Paulo" --uri="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/secoes-etl:run" --http-method=POST --oauth-service-account-email="secoes-scheduler@$PROJECT.iam.gserviceaccount.com" --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" --max-retry-attempts=1 --attempt-deadline=180s
```

Não é necessário manter um serviço HTTP ligado: o Cloud Run Job encerra ao concluir.
