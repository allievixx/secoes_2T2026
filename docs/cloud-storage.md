# Cloud Storage e Cloud Run

## Fluxo de dados

### Descoberta da lista vigente no SIG/TSE

`changesPage` em [pipeline-config.json](../pipeline-config.json) ativa a descoberta pela página oficial de seções alteradas. `sources.changes` fica `null`: não há fallback para um ZIP antigo. O job abre uma sessão APEX nova com Playwright/Chromium, confirma ano e filtros nacionais, aciona **Gerar arquivos → CSV (pt-BR) → Gerar Arquivo** e lê o link de Download. A data/hora do caminho do ZIP deve coincidir com a última atualização exibida na página. A URL descoberta e a evidência de atualização entram nos metadados da fonte publicada.

Não guardar o parâmetro `session` de um navegador: ele expira e pode redirecionar para a página inicial. Configurações explícitas para testes/reprodução podem omitir `changesPage` e informar uma fonte local ou ZIP fixo.

Dependências: Playwright e Chromium. A imagem instala Chromium e bibliotecas de sistema durante o build; no ambiente local, use `uv sync` e `uv run playwright install chromium`. O grupo `dev` inclui o kernel do notebook.

**Validação em 21/10:** o modo headless recebeu HTTP 403 tanto com Chromium quanto com Chrome instalado. Chromium e Chrome com interface receberam HTTP 200. A descoberta completa pelo código, com Chromium com interface e perfil limpo, criou sessão APEX, gerou o arquivo e baixou o ZIP `20261021_141929/1d5a9ea9d39198eb5b3cf54312a93675`, confirmando **340 seções e 101.152 eleitores** via `--inspect`, sem publicar dados. Não há alteração de user-agent, mascaramento de automação ou reutilização de cookies do usuário.

A automação usa `headless=False`. A imagem Linux instala `xvfb`/`xauth` e inicia o comando com `xvfb-run -a`, fornecendo o display necessário mesmo sem monitor. O ambiente Cloud Run ainda precisa de validação real antes de considerar a descoberta implantada e funcional nele. Em qualquer recusa/falha, o código cancela a publicação sem recorrer ao ZIP antigo.

O dashboard do GitHub Pages não consulta BigQuery nem usa credenciais Google. A rotina busca as fontes oficiais, valida e transforma os dados e acrescenta um snapshot completo ao histórico `{"snapshots":[{"extracted_at":"...","rows":[...]}]}` diretamente em:

`gs://extracao_alteracao_locais_votacao/secoes_alteradas_2t_2026.json`

O bucket e o objeto são definidos no bloco `storage` de [pipeline-config.json](../pipeline-config.json). A rotina só faz upload depois que geração e validação terminam. Uma falha de upload deixa o objeto anterior intacto. Linhas vazias são recusadas. Cada execução guarda a extração completa com seu instante UTC, sem descartar execuções anteriores. O formato legado `{"rows":[...]}` é migrado no primeiro upload, usando a data de atualização do objeto no Cloud Storage.

O histórico já no formato `snapshots` é preservado sem reprocessar os campos antigos com o schema atual. Não há retenção por data, limite de extrações nem deduplicação por conteúdo: duas extrações em instantes diferentes são mantidas mesmo se suas linhas forem idênticas. Um retry com mesmo instante e conteúdo não duplica a publicação; conteúdo diferente no mesmo instante é recusado, nunca substituído.

Leitura e escrita usam a geração do objeto como precondição. Havendo conflito entre publicadores, a rotina relê o histórico e refaz o merge, em até cinco tentativas. Falha de leitura ou JSON inválido aborta a publicação, sem criar um histórico vazio por cima do existente.

**Atenção à migração de bucket:** trocar `storage.bucket` não copia o histórico do destino anterior. É necessário migrar e conferir o histórico antes de apontar o job e o dashboard para o novo destino. Restaurar um backup antigo por cima do objeto também remove do JSON as extrações posteriores ao backup; a rotina não consegue recuperar versões que não estão mais no objeto lido.

### Auditoria em 21/10/2026

- O objeto principal no bucket `extracao_alteracao_locais_votacao` continha 8 extrações (3 de 19/10 e 5 de 20/10), todas com 774 seções. O backup de sufixo `_bkp` tinha o mesmo histórico.
- Os logs do Cloud Run confirmavam publicações bem-sucedidas em 21/10 às 00:20:13Z, 09:33:00Z e 14:34:50Z. Nenhuma dessas extrações constava no objeto principal consultado.
- A geração atual do objeto era `1792603039644123`, criada às 17:17:19Z de 21/10, depois dessas três publicações. Isso comprova uma substituição posterior, mas não identifica sozinho seu autor ou os conteúdos removidos.
- O backup de sufixo `_antes_restauracao_1792600394311489` continha 3 registros com contagens 774, 453 e 383. Não se deve presumir que sejam as extrações originais das execuções citadas apenas com base nos horários.
- O bucket `secoes-comite-popular-tech` continha somente uma extração, em 21/10 às 14:29:45.537948Z (774 seções). A configuração local apontava para esse bucket; a imagem ativa do job (geração 8) ainda apontava para `extracao_alteracao_locais_votacao`.
- O pacote do build `806b5c8c-7edc-4180-a3ee-651e4035254d`, correspondente ao digest da imagem ativa, foi inspecionado: a rotina fazia append sem corte de histórico, mas não refazia o merge após conflito e substituía timestamps iguais.

Esta auditoria não restaurou, mesclou nem publicou dados e não implantou uma nova imagem. As correções locais não recuperam as extrações ausentes; recuperação exige cópias confiáveis ou versões anteriores disponíveis.

### Deploy das correções em 21/10/2026

### Investigação do bloqueio antes do Python

A execução `secoes-etl-cqdp8` só emitiu o BOOT anterior a `xvfb-run`. A inspeção do pacote Debian `xvfb_21.1.16-1.3+deb13u4_amd64.deb` mostrou que `xvfb-run` inicia Xvfb e usa `wait` até receber SIGUSR1. No código Xorg 21.1.16, `os/connection.c`, `NotifyParentProcess()` só envia esse sinal quando `ParentProcess > 1`. Nosso wrapper fazia `exec xvfb-run`, deixando-o como PID 1 no entrypoint sem init. Esse caminho tem condição de bloqueio permanente antes da chamada do Python, compatível com os logs observados; falta confirmação dinâmica em Linux/Cloud Run da correção.

A correção local instala `tini` e o usa como PID 1; o wrapper e `xvfb-run` tornam-se filhos com PID maior que 1. O wrapper registra seu PID e recusa iniciar como PID 1. Foram aprovados 64 testes, incluindo passagem de argumentos e diagnóstico com `xvfb-run` simulado. Esses testes não reproduzem um namespace Linux real. Não houve build, deploy, execução do job ou alteração de dados na nuvem durante essa investigação.

Após autorização de deploy, o build `d6e9ba27-7116-485a-98a8-ea6380388d22` (imagem `tse-tini-20261021`) foi implantado. A execução `secoes-etl-pjctt` confirmou o avanço real no Cloud Run: wrapper PID 10 às 19:10:42.277Z, Python ativo às 19:10:42.863Z, HTTP 200 no TSE e descoberta da publicação `20261021_152726/941357b6eb3fc71211698560980e6eaf` às 19:11:05Z. Isso confirma que a mudança removeu o bloqueio de inicialização observado.

A execução terminou com sucesso às 19:13:39.695Z (aproximadamente 2min57s desde o primeiro BOOT). A geração 13 usa digest `sha256:82e88b6c8beb1b55290f10c622055fb2ba33a2794bd4f93a4919344650dd0341`. O snapshot de 19:13:24.481013Z publicou **343 seções e 101.848 eleitores**. O histórico passou de 10 para 11 extrações, com igualdade integral dos dez snapshots anteriores. Os quatro objetos de fontes foram confirmados com SHA-256 nos metadados correspondente ao snapshot. A versão de cadastro recebida pelo job ainda gerou pendências de enriquecimento; contagem correta e publicação bem-sucedida não significam ausência de campos sem fonte.

### Histórico de imagens

- Diagnóstico de inicialização: build `06c633d9-62cb-4807-ab6f-8b0a50d5a379`, imagem `tse-boot-entrypoint-20261021`. O entrypoint `scripts/run_job.sh` escreve antes do Xvfb, encaminha seus erros ao stderr, escreve ao iniciar Python e habilita `faulthandler` para crashes nativos. O dump periódico de stack traces a cada 120 segundos foi removido: em 23/10/2026 (`secoes-etl-dn9v6`) ele causou `Segmentation fault` (exit 139) ao disparar enquanto a leitura de `votacao_secao_2026_BR.csv` calculava o CRC do zip. Há logs antes/depois do logging adicional e por etapa Playwright. Execução de validação somente leitura: `secoes-etl-cqdp8`, com override `--inspect`. CPU e memória continuam 2 vCPUs/4 GiB.
- Descoberta automática: build `84633557-fd9f-422d-87ed-7a21e7c30811`, imagem `tse-discovery-20261021`, digest `sha256:63f64bb91db0c209cf6c75771c805d01735b01f5d4326163f4c5ea37a2099ec1`, implantada na geração 10 do job. Usa Chromium com interface em Xvfb. Execução manual de validação: `secoes-etl-ltjwf`. A execução agendada `secoes-etl-pq442` começou antes dessa atualização e ainda usava a imagem anterior.
- Build `9d545a57-3004-43cb-b7ce-774d3ea0d5c2` concluído com sucesso após 53 testes Python aprovados.
- Imagem `history-all-sources-20261021`, digest `sha256:49a4d1d6f6f1b925f3f76c6521e6815da2a23b3a7a93e03221e9351574dde064`, implantada no job `secoes-etl`, geração 9, em `us-central1`.
- O destino foi mantido em `extracao_alteracao_locais_votacao`, alinhando a configuração local ao job e evitando iniciar outro histórico em um bucket diferente.
- Execução manual de validação: `secoes-etl-4jz82`. O deploy não altera o agendamento, os recursos nem a conta de serviço do job.
- Validação concluída com sucesso às 17:44:47Z: o JSON passou de 8 para 9 snapshots, com os 8 anteriores integralmente preservados. A nova extração é de 17:44:31.855417Z e contém 774 seções.
- As quatro cópias foram confirmadas no bucket, com SHA-256 nos metadados igual ao registrado no snapshot: alterações 13.577 bytes, cadastro 175.502.489 bytes, votação 161.616.519 bytes e detalhe 176.923.175 bytes. Isso valida uma execução real; os cenários de concorrência e duas cópias idênticas no mesmo instante continuam cobertos pelos testes locais.

### Cópias das fontes do TSE

O TSE sobrescreve seus ZIPs na mesma URL. Antes de publicar o snapshot, a rotina arquiva **uma nova cópia em cada execução**, mesmo se o arquivo for idêntico ao anterior ou tiver vindo do cache local. Os arquivos são definidos em `storage.archiveSources` (padrão `["changes", "registry", "votes", "details"]`: alterações, cadastro de locais, votação e detalhe da votação), sob `storage.archivePrefix` (padrão `fontes`). O JSON de municípios do IBGE não está nessa lista.

`gs://<bucket>/fontes/<fonte>/<instante da cópia UTC com microssegundos>-<UUID>-<Last-Modified em UTC>-<sha256[:12]>-<nome original>`

Não há deduplicação por SHA-256. O instante da cópia e o UUID tornam cada nome único, inclusive com fontes idênticas e execuções simultâneas. O upload usa `if_generation_match=0`, sem sobrescrever cópias anteriores. Os metadados guardam SHA-256, URL de origem, `Last-Modified`, `ETag`, instante do download e `archived_at` (instante da cópia). O caminho arquivado entra em `sources.<fonte>.archived` no snapshot e em `source_versions` no relatório. Uma falha no arquivamento é registrada em `falhas_arquivamento` no relatório e no log, mas não impede a publicação do dashboard. Como o bucket é público, as cópias também são — são dados públicos do TSE. Arquivar todas as fontes em todas as execuções aumenta armazenamento e tempo de upload: só o cadastro tem aproximadamente 170 MB por cópia.

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

O mesmo limite de três tentativas cobre transferências truncadas (`IncompleteRead`) e divergências entre o tamanho recebido e o `Content-Length`. Divergências registram os bytes esperados e recebidos. Cada tentativa reinicia o arquivo temporário e o SHA-256; nenhuma parte de um download anterior é reaproveitada. Se a terceira tentativa falhar, a execução encerra com erro, preservando o cache anterior e seus metadados e sem publicar um novo snapshot. A validação de tamanho não é relaxada.

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
