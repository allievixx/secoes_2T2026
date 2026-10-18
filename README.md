# seções com local de votação alterado no 2º turno - eleições 2026

comparação, seção por seção, do local de votação no 1º turno (04/10) e no 2º turno (25/10) das eleições 2026, a partir dos dados abertos do TSE.

## fonte

- portal de dados abertos do TSE, conjunto [Eleitorado - 2026](https://dadosabertos.tse.jus.br/dataset/eleitorado-2026), recurso "Eleitorado por local de votação - 2026"
- arquivo: `https://cdn.tse.jus.br/estatistica/sead/odsele/eleitorado_locais_votacao/eleitorado_local_votacao_2026.zip`
- versão usada: gerada em **16/10/2026 às 06:29** (campo `DT_GERACAO`). o catálogo mostra data de julho, mas o arquivo na CDN foi substituído nessa data

## método

a base traz cada seção duas vezes (`NR_TURNO` 1 e 2). as seções são pareadas por UF + município + zona + seção, e são marcadas como alteradas quando muda o código do local (`NR_LOCAL_VOTACAO`) ou o endereço.

a coluna `TIPO_MUDANCA` separa:
- **novo local**: o código do local mudou entre os turnos
- **mesmo local - nome/endereco editado**: mesmo código, só o texto do nome ou endereço mudou (geralmente limpeza de cadastro)

## resultados (base de 16/10)

| | seções | eleitores |
|---|---|---|
| novo local | 2.507 | ~735 mil |
| mesmo local, texto editado | 230 | - |

seções com novo local por UF (top 8): PE 324, SP 309, PR 308, PI 227, MG 204, MA 179, BA 155, AP 142.

nenhuma seção mudou de zona eleitoral entre os turnos.

## limitações

- o número divulgado pelo TSE (4.352 seções até 16/10) é maior que o encontrado aqui, provavelmente porque a base foi gerada antes do fim do dia ou porque o tribunal usa outro critério de contagem
- em 5 seções o código do local mudou mas nome e endereço continuam iguais (possível renumeração), e em 7 o nome é o mesmo e só o endereço mudou
- é um retrato da base em 16/10: novas alterações podem aparecer até o dia 25. para atualizar, rode o script de novo

## como rodar

```bash
pip install pandas
python scripts/compara_turnos.py
```

o CSV de saída fica em `data/` (UTF-8, separado por `;`).
