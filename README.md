# seções que mudaram de local no 2º turno - eleições 2026

mapa e lista das seções eleitorais que vão votar em outro local no 2º turno (25/10/2026), com o resultado de cada uma no 1º turno para presidente.

a página é o `index.html` (abre direto no navegador ou pelo GitHub Pages). os dados que ela usa estão em `data/secoes_alteradas_2t_2026.csv`.

## números

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
- em notícia de 16/10, o TSE informou 4.352 seções alteradas entre o 1º e o 2º turno, com números por estado (SP 982, MG 514, RJ 431, BA 312) que não batem com a lista seção por seção

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
