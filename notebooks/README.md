# Sanidade das fontes e do JSON

Abra [sanidade_fontes_json.ipynb](sanidade_fontes_json.ipynb), selecione o kernel `.venv` e execute de cima para baixo. Na célula 3 ficam os parâmetros para escolher extração, fontes atuais/arquivadas, atualização de downloads e seção investigada.

O notebook faz somente leituras HTTP públicas e grava cache/relatórios locais em `.cache/sanidade/`. Não publica no Cloud Storage, não executa o job e não lê o CSV final local. O modo padrão `ambos` pode baixar cerca de 1 GB. Use `ATUALIZAR_DOWNLOADS = False` para reutilizar o cache.

## Verificações

- Congela o JSON de referência e lista extrações disponíveis.
- Baixa as quatro fontes TSE diretamente e as cópias vinculadas ao snapshot; recalcula SHA-256 dos bytes.
- Mostra amostras dos CSVs e registros brutos por turno do cadastro.
- Compara chaves, eleitores e locais, totais por UF, duplicatas e registros ausentes.
- Confere votos e detalhe de votação independentemente do pipeline, incluindo votos + abstenções = aptos.
- Reproduz o cruzamento com as funções locais do pipeline, explicitamente separado das verificações independentes.
- Verifica schema, coordenadas, campos nulos e pendências; exporta relatório JSON e tabelas CSV.

`INCOMPLETO` não significa aprovação. Fonte atual com SHA diferente pode ter sido republicada pelo TSE; não demonstra erro na extração antiga. A reprodução usa código/configuração locais e IBGE atual, não necessariamente a imagem/configuração histórica.

## Execução inicial, 21/10/2026

Snapshot 17:44:31.855417Z: 774 seções, 229.018 eleitores, sem divergências independentes nem erros de schema. Com as fontes arquivadas, reprodução sem diferenças, com 425 pendências de enriquecimento. O cadastro atual mudou de hash e a reprodução parou por local ambíguo em MG/AIMORÉS, zona 5, seção 4. Esse diagnóstico ficou registrado, sem alterar o pipeline nem a produção.