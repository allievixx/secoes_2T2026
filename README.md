# seções que mudaram de local no 2º turno - eleições 2026

mapa e lista das seções eleitorais que vão votar em outro local no 2º turno (25/10/2026), com o resultado de cada uma no 1º turno para presidente.

a aplicação mantém o mapa, resumo, filtros, lista e tabela por estado. os dados não ficam mais embutidos no HTML: são buscados por HTTP a cada abertura.

## executar

Requer Node.js 20 ou superior. Instale as dependências com `npm install` e inicie com `npm start`. Abra http://localhost:8080. Para executar os testes, use `npm test`.

Para consultar **BigQuery** em vez do CSV, use `npm run start:bq` (requer Python 3.11+ e CLI `bq` já autenticada). Esse modo serve o dashboard e uma API local em http://127.0.0.1:8080. Veja [docs/bigquery.md](docs/bigquery.md).

Também funciona no GitHub Pages, sem backend ou etapa de build: publique os arquivos da raiz junto com a pasta de dados. Abrir o HTML diretamente por `file://` não funciona, pois o navegador restringe o carregamento de módulos e requisições locais.

## fontes dinâmicas e atualização

- [dashboard-config.json](dashboard-config.json) configura a URL do CSV, as URLs das malhas geográficas e os metadados de publicação.
- `dataUrl` aponta inicialmente para o CSV existente na pasta de dados. Basta substituir a base mantendo o esquema abaixo e recarregar a página; não é necessário alterar o código nem gerar outro HTML. A requisição usa `cache: no-store`.
- Para buscar de outro servidor, altere `dataUrl` para uma URL HTTP(S) que retorne o mesmo CSV UTF-8 separado por ponto e vírgula. Fontes externas precisam permitir CORS. Nunca inclua chaves privadas no frontend.
- Datas de publicação, versão do cadastro e datas dos turnos ficam em `metadata`; atualize-as junto com a base.
- Municípios e estados são carregados da API pública de malhas do IBGE. As URLs podem ser trocadas por arquivos GeoJSON hospedados localmente; mantenha `FeatureCollection` e `properties.codarea` com o código IBGE. As malhas usam o cache HTTP normal.
- Totais, agrupamentos e indicadores são calculados a partir do CSV recebido, com validação de colunas, números, coordenadas e seções duplicadas. Valores vazios de votos e coordenadas são tratados como ausentes.
- O carregamento mostra estado de espera, erros e opção de tentar novamente. CSV/configuração/mapa têm limite de 30 segundos por requisição.

### organização

- [index.html](index.html): estrutura da página, sem dados embutidos.
- [styles.css](styles.css): visual e responsividade.
- [app.js](app.js): inicialização, mapa e interações.
- [dashboard-data.js](dashboard-data.js): leitura e transformação do CSV.
- [tests/dashboard-data.test.js](tests/dashboard-data.test.js): testes com dados sintéticos; não leem a base real.

As bibliotecas D3 e fontes tipográficas continuam vindo de CDNs. A aplicação precisa de acesso às fontes configuradas. Não existe sincronização automática com o TSE: a fonte CSV deve ser atualizada por quem mantém os dados.

## gerar a base com Python

A rotina [scripts/gerar_dados.py](scripts/gerar_dados.py) baixa a lista de alterações indicada, cruza cadastro de locais, resultados do 1º turno e municípios IBGE, e gera as mesmas 25 colunas do dashboard. Usa Python 3.11+ sem dependências externas.

Fontes e candidatos ficam em [pipeline-config.json](pipeline-config.json). O destino padrão agora é a tabela `comite-tecnologia.alteracao_locais_votacao.secoes_alteradas_2t_2026`, em **US**. Execute `python3 scripts/gerar_dados.py` para gerar e publicar o snapshot no BQ, usando a CLI já autenticada, sem ler nem substituir o CSV existente. Cada execução substitui o conteúdo da tabela.

Para inspecionar apenas o ZIP: `python3 scripts/gerar_dados.py --inspect`. Para exportar CSV: `python3 scripts/gerar_dados.py --destination csv --output data/secoes_novas.csv`.

Os enriquecimentos “Longe da urna” e snapshot de 15/10 estão **adiados**: não bloqueiam mais a geração e ficam NULL no BQ (vazios no CSV). As demais validações continuam ativas. A distância da mudança é calculada normalmente quando existem as coordenadas dos dois locais.

Veja [docs/geracao-dados.md](docs/geracao-dados.md) para fontes, configuração, critérios de cruzamento, cache, publicação e testes.
Veja [docs/bigquery.md](docs/bigquery.md) para carga BigQuery, esquema, API e leitura pelo JavaScript.

## números da versão original (referência estática)

| | |
|---|---|
| seções que mudam de local | 4.288 |
| eleitores nelas | 1.578.731 |
| municípios | 577 |
| Lula no 1º turno (votos válidos) | 49,2% |
| Flávio no 1º turno (votos válidos) | 43,7% |
| abstenção no 1º turno | 19,9% (Brasil: 20,8%) |
| seções que mudaram 2 km ou mais | 583 |
| seções em região longe da urna | 179 |

estados com mais seções alteradas: PA 841, RN 366, CE 299, MG 280, SC 245, PB 224, GO 204, SP 200.

## fontes

- **seções alteradas:** lista de seções eleitorais alteradas no 2º turno publicada pelo TSE (`secoes_eleitorais_alteradas_2t-pais_2026`), gerada em 15/10/2026. "eleitores" é a coluna `qt_eleitores` dessa lista
- **endereços e coordenadas:** base de locais de votação do TSE (`eleitorado_local_votacao_2026`), versão de 17/10/2026 às 06:28. nela, as mesmas seções somam menos eleitores aptos (1.292.895), e a lista do TSE não explica a diferença
- **resultado do 1º turno (presidente) por seção:** TSE, votação por seção e detalhe da votação por seção. "aptos" é o número de aptos no 1º turno, tirado do resultado por seção
- **região longe da urna:** critério do mapa Longe da urna, em que quem mora em volta do local está, em média, a 5 km ou mais dele

## como ler

- a distância é em linha reta entre o local original e o novo. quando o local original não tem mais nenhuma seção no cadastro, não há como medir
- o tempo a pé usa 5 km/h
- em notícia de 16/10, o TSE informou 4.352 seções alteradas entre o 1º e o 2º turno, com números por estado que não batem com a lista seção por seção

## colunas do CSV

UTF-8, separado por `;`, uma linha por seção.

| coluna | descrição |
|---|---|
| `uf`, `municipio`, `cd_ibge`, `zona`, `secao` | identificação da seção |
| `eleitores` | `qt_eleitores` da lista de seções alteradas |
| `local_1t`, `endereco_1t`, `lat_1t`, `lon_1t` | local de votação original |
| `local_2t`, `endereco_2t`, `bairro_2t`, `lat_2t`, `lon_2t` | local de votação no 2º turno |
| `distancia_km` | distância em linha reta entre os dois locais (vazio quando não dá para medir) |
| `regiao_longe_da_urna` | `True` quando o local fica em região longe da urna |
| `entrou_desde_15_10` | `True` quando a seção entrou na lista depois de 15/10 |
| `aptos_1t`, `abstencao_1t` | aptos e abstenção no 1º turno |
| `lula_1t`, `flavio_1t`, `outros_1t`, `brancos_1t`, `nulos_1t` | votos para presidente no 1º turno |
