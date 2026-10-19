# BigQuery: geração e visualização

## Destino configurado

- Projeto: `comite-tecnologia`.
- Dataset existente: `alteracao_locais_votacao`.
- Tabela: `secoes_alteradas_2t_2026`.
- Localização: **US**.

Esses valores ficam no bloco `bigquery` de [pipeline-config.json](../pipeline-config.json). A rotina usa a CLI `bq` e a autenticação **já existente** do Google Cloud CLI. Não executa login, não verifica a conta previamente e não solicita credenciais. Não cria nem muda a localização do dataset.

## Publicar

Execute `python3 scripts/gerar_dados.py`. **O destino padrão agora é BigQuery**, não CSV.

A rotina baixa/reutiliza as fontes oficiais, realiza os mesmos cruzamentos e submete um load job em `US` para `comite-tecnologia.alteracao_locais_votacao.secoes_alteradas_2t_2026`. O comando efetivo usa `bq load --replace`, com esquema explícito e NDJSON temporário; não usa autodetecção de tipos nem inserções linha a linha.

**Cada execução bem-sucedida substitui o snapshot completo dessa tabela.** A publicação do load job é atômica; erros não deixam uma tabela parcialmente carregada. Cargas vazias são recusadas. Se a tabela ainda não existir, o load job a cria no dataset existente. A rotina aguarda a conclusão antes de marcar o relatório como publicado. Em caso de timeout, confira o job antes de repetir a carga.

As 25 colunas mantêm seus nomes. Contagens/códigos usam `INTEGER`, coordenadas/distâncias usam `FLOAT`, indicadores usam `BOOLEAN` e textos usam `STRING`; valores ausentes viram **NULL**, não string vazia, zero ou `False`.

Os dois enriquecimentos adiados (`baseline` e `longDistance`) **não bloqueiam mais a publicação**. Sem eles, `entrou_desde_15_10` e `regiao_longe_da_urna` ficam NULL. `--allow-incomplete` continua disponível apenas para tolerar outras lacunas detectadas, como resultados ausentes.

O CSV original não é usado como entrada e não é aberto nem sobrescrito no modo BigQuery. Para exportar somente CSV, use `--destination csv --output data/secoes_novas.csv`. Para publicar no BQ e também exportar CSV, use `--destination both --output data/secoes_novas.csv`. A proteção `--overwrite` aplica-se ao arquivo CSV, não à tabela de snapshot.

## Dashboard consultando o BigQuery

Execute `npm run start:bq` (ou `python3 -m scripts.servir_dashboard`) e abra http://127.0.0.1:8080.

O fluxo é: **JavaScript → API local `/api/secoes` → BigQuery**. O servidor devolve automaticamente uma configuração do dashboard com `dataFormat: json` e `dataUrl: ./api/secoes`. Os arquivos da configuração estática original não são alterados.

- A API executa somente uma consulta fixa às 25 colunas da tabela configurada; não aceita SQL do cliente.
- As credenciais e o acesso à CLI ficam no backend. O navegador nunca recebe tokens Google nem chama a API BigQuery diretamente.
- O servidor mantém cache de 60 segundos por processo, com uma consulta por vez. Após uma carga, aguarde a expiração ou reinicie o servidor para ver o snapshot novo.
- A consulta usa a localização `US`, limite de faturamento de 100 MB por query e limite de 100 mil linhas. Se houver mais linhas, retorna erro, em vez de truncar silenciosamente o dashboard. Consultas podem gerar custos conforme a política do projeto.
- O servidor só disponibiliza os arquivos necessários ao frontend. Não publica o diretório de dados, caches ou configuração do pipeline.
- `npm start` continua sendo o modo estático/CSV anterior. GitHub Pages pode hospedar o frontend, mas **não executa esse backend**.

Este servidor é para **desenvolvimento local**, escutando apenas em `127.0.0.1`. Para uma aplicação pública, hospede uma API em um serviço adequado (por exemplo, Cloud Run), com identidade de serviço, HTTPS, política de autenticação/acesso, CORS restrito se houver outra origem, limites de tráfego e monitoramento de custos. O frontend pode apontar `dataFormat: json`/`dataUrl` para essa API; não coloque credenciais no cliente nem exponha uma consulta irrestrita na internet.

## Permissões e testes

A identidade da carga precisa criar jobs no projeto e escrever na tabela/dataset (normalmente BigQuery Job User + BigQuery Data Editor no escopo adequado). A identidade da API precisa criar jobs e ler a tabela (Job User + Data Viewer). Nenhuma alteração de IAM é feita por esta implementação.

`python3 -m unittest discover -s tests -p 'test_*.py' -v` e `npm test` cobrem esquema, NULLs, comandos de carga/consulta, cache, API e leitura JSON. **Os testes simulam a CLI: não consultam autenticação, não enviam jobs e não executam cargas reais.**