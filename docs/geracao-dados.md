# Geração do CSV com Python

A rotina [scripts/gerar_dados.py](../scripts/gerar_dados.py) gera as mesmas **25 colunas** descritas no README, usando as fontes oficiais configuradas em [pipeline-config.json](../pipeline-config.json). Requer Python **3.11 ou superior**, apenas com biblioteca padrão; não há pacotes pip a instalar. O destino padrão é **BigQuery**, em `comite-tecnologia.alteracao_locais_votacao.secoes_alteradas_2t_2026`, localização **US**, usando a CLI `bq` já autenticada. Veja [bigquery.md](bigquery.md).

## Execução

- Inspecionar o arquivo novo do TSE sem gerar saída: `python3 scripts/gerar_dados.py --inspect`.
- Gerar e publicar o snapshot no BigQuery: `python3 scripts/gerar_dados.py`.
- Gerar CSV separado, sem publicar no BQ: `python3 scripts/gerar_dados.py --destination csv --output data/secoes_novas.csv`.
- Publicar sobre o CSV existente, explicitamente: `python3 scripts/gerar_dados.py --destination csv --overwrite`.
- Testes isolados: `python3 -m unittest discover -s tests -p 'test_*.py' -v`.

Os comandos pressupõem execução na raiz do repositório. `--config`, `--output`, `--report` e `--cache-dir` aceitam outros caminhos. Caminhos das fontes dentro da configuração são relativos ao diretório dela; podem ser arquivos locais ou URLs HTTP(S).

A saída CSV existente **não é lida**, nem é usada como entrada ou referência. No modo CSV, a rotina recusa substituição sem `--overwrite` e usa gravação atômica. No modo BigQuery, cada carga bem-sucedida substitui atomicamente o snapshot da tabela; não lê nem grava o CSV. A validação anterior com fontes reais gerou uma cópia separada no cache, preservando o CSV original. A integração BQ foi testada apenas com mocks, sem executar carga real.

## Fontes e cruzamentos

| Entrada | Finalidade |
|---|---|
| `changes` | ZIP exato indicado, gerado em 19/10/2026, com município, zona, seção, local inicial/final e `qt_eleitores`. |
| `registry` | Cadastro `eleitorado_local_votacao_2026`: código municipal TSE, endereço, bairro, coordenadas, identificadores de local e campos do local original. |
| `votes` | `votacao_secao_2026_BR`: votos por seção, filtrados para ano configurado, 1º turno e presidente (`CD_CARGO=1`). |
| `details` | `detalhe_votacao_secao_2026`: aptos, abstenções, brancos e nulos, com os mesmos filtros. |
| `municipalities` | API de localidades do IBGE: nome + UF → código IBGE de sete dígitos. O código TSE **não é** o código IBGE. |
| `baseline` | Snapshot de alterações de **15/10**, com o mesmo esquema de `changes`, para identificar seções que entraram depois. Não foi localizada uma URL histórica a partir do README. |
| `longDistance` | Base externa de distância média dos moradores até o local final de votação, para aplicar o critério “Longe da urna”. O README não informa URL nem metodologia suficiente para reconstruí-la. |

Os cabeçalhos das quatro fontes TSE foram verificados nos arquivos oficiais. A fonte de alterações usa nomes minúsculos e CP1252; o leitor normaliza os cabeçalhos e aceita CSV ou ZIP. O restante dos arquivos TSE também é lido como CP1252, configurável em `encoding`. A saída é UTF-8, separada por `;`, com `True`/`False` para booleanos conhecidos e campos vazios para valores desconhecidos.

### Identificadores e locais

1. Identifica a seção da lista de alterações pelo município normalizado, UF, zona e seção no cadastro TSE. Correspondências ausentes ou ambíguas causam erro, mesmo no modo parcial.
2. Cruza a seção com votos/detalhe por UF, **código municipal TSE**, zona e seção.
3. Associa o município ao IBGE por nome normalizado e UF. Divergências conhecidas usam `ibgeOverrides`, por exemplo `GO:BOM JESUS` → `5203500` (Bom Jesus de Goiás). Não faz aproximações por similaridade de nomes.
4. Resolve os locais inicial e final na mesma zona e município. Quando disponíveis, os campos de identificação e endereço do local original também são usados. Locais ambíguos causam erro; não se escolhe uma coordenada arbitrária.
5. Se o local original não tiver mais seções no cadastro, conserva o endereço original quando disponível, mas deixa suas coordenadas e a distância vazias, conforme o README.
6. Calcula `distancia_km` pela fórmula de Haversine com raio médio da Terra de 6.371,0088 km, arredondando para três casas decimais. Não usa rotas viárias.

### Votos e integridade

`candidates` define os números associados a Lula e Flávio (13 e 22 na configuração inicial). Confira-os ao mudar de eleição. Outros códigos de candidato são somados em `outros_1t`; 95 e 96 representam brancos e nulos. Brancos/nulos são conferidos contra o detalhe de votação; votos + abstenção devem fechar com aptos. A contagem de `eleitores` vem exclusivamente da lista de alterações, não é substituída por aptos.

O leitor evita processar simultaneamente o arquivo nacional e os arquivos por UF dentro de um mesmo ZIP. Resultados idênticos repetidos não são somados duas vezes; conflitos e duplicatas na lista de alterações causam erro. Não se usa resultado do segundo turno, de outro cargo ou de outro ano.

## Duas informações que não podem ser inferidas dessas fontes

**“Longe da urna” não é a distância da mudança.** O README define esse indicador pela distância média de quem mora ao redor de um local até a urna. Apenas duas coordenadas de locais de votação não fornecem população residencial, distribuição espacial nem essa média. Não é correto substituir isso por `distancia_km >= 5`.

Para fornecer o enriquecimento, configure `sources.longDistance` como CSV UTF-8 (ou ZIP de CSV) separado por `;`, com cabeçalho:

| Coluna | Descrição |
|---|---|
| `uf` | Sigla da UF. |
| `cd_municipio` | Código municipal **TSE**. |
| `zona` | Número da zona eleitoral. |
| `nr_local_votacao` | Número do local **final** no cadastro TSE. |
| `distancia_media_km` | Distância média de moradores até esse local, em km, previamente obtida pelo método da fonte original. |

A rotina aplica `distancia_media_km >= 5`. Não calcula essa média sem os dados necessários.

Para `entrou_desde_15_10`, configure `sources.baseline` com o snapshot daquela data. A comparação é feita por UF, município, zona e seção, independentemente de a seção ter mudado de endereço novamente. O arquivo atual não revela a data de entrada de cada seção.

**Essas duas entradas foram adiadas e não são mais obrigatórias.** Sem elas, os indicadores ficam NULL no BigQuery (vazios no CSV), sem impedir publicação. `--allow-incomplete` permite outras lacunas, como resultados ausentes ou local final não localizado. Não transforma desconhecido em `False`, zero, “perto” ou “seção antiga”. O dashboard preserva indicadores desconhecidos e sinaliza cobertura incompleta; não os apresenta como medidos.

## Download, cache e relatório

Os ZIPs nacionais são grandes (aproximadamente 506 MB somados, nas versões verificadas). São baixados em streaming para `.cache/tse/`, e os CSVs internos também são percorridos em streaming; não são extraídos para o projeto nem carregados inteiros na memória. O índice em memória mantém apenas municípios/zonas relevantes. Downloads incompletos não são promovidos ao cache.

O cache é identificado pela URL e reutilizado. Como as URLs de cadastro e resultados são mutáveis, use `--refresh` para buscar uma versão nova. Para reproduzir exatamente uma geração, preserve os arquivos baixados e configure suas cópias locais; a versão do cadastro de 17/10 citada no README não é garantida pela URL atual.

O relatório (por padrão, no diretório de dados, com nome `geracao-relatorio.json`) registra URLs, instante UTC, candidatos, totais, cobertura dos campos, destino, enriquecimentos adiados e pendências por seção. Com outras falhas de enriquecimento, ele é escrito, mas a saída não é publicada sem `--allow-incomplete`. O relatório só marca `publicado: true` depois de concluir a escrita/carga. Erros estruturais interrompem antes da publicação.

O ZIP de alterações indicado retornou **774 seções e 229.018 eleitores** na validação. Isso não coincide com as 4.288 seções/1.578.731 eleitores da versão original: a rotina reproduz o **contrato e os cruzamentos**, não força números antigos nem promete igualdade byte a byte entre snapshots diferentes.

Após publicar uma nova base, atualize também as datas em [dashboard-config.json](../dashboard-config.json). O gerador não altera automaticamente metadados editoriais nem a configuração do dashboard.