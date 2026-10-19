# Linha do Tempo (Timeline) - Documentação da Funcionalidade

## Visão Geral

A aba "Linha do tempo" permite visualizar como os dados de seções que mudaram de local evoluem ao longo das diferentes extrações (cargas) realizadas. Através de gráficos de série temporal, é possível acompanhar variações nas seguintes métricas:

1. **Seções que mudam de local**: Total de seções eleitorais com endereço alterado
2. **Eleitores nelas**: Quantidade de eleitores nas seções que mudaram
3. **Aptos**: Número de eleitores aptos no 1º turno (nas seções que mudaram)

## Como Funciona

### Estrutura de Dados

A funcionalidade utiliza `globalThis.allSnapshots`, um array contendo todos os snapshots de dados carregados. Cada snapshot tem:

```javascript
{
  extractedAt: "2026-10-19T14:00:00Z",  // ISO 8601 timestamp (UTC)
  data: {
    g: [                                 // Array de grupos (locais)
      {
        s: [                             // Array de seções neste local
          [section_id, eleitores, aptos, ...]
        ]
      }
    ]
  }
}
```

### Agregação de Métricas

Para cada snapshot, a função `renderTimeline()` calcula:

- **sections**: Total de seções (iterando todos os `s` em todos os `g`)
- **voters**: Soma de `s[1]` (eleitores) para todas as seções
- **eligible**: Soma de `s[2]` (aptos) para todas as seções

### Renderização do Gráfico

1. **Validação**: Se houver menos de 2 snapshots, exibe mensagem de aviso
2. **Extração de rótulos de tempo**: Formata horários em pt-BR com timezone "America/Sao_Paulo"
3. **Criação de escalas D3**:
   - Eixo X: índice linear de 0 a (nSnapshots - 1)
   - Eixo Y: escala linear de 0 ao valor máximo do metric
4. **Desenho de linhas**: Linha contínua com stroke width 2.5px
5. **Marcadores**: Círculos com raio 4px e opacity 0.7 em cada ponto

### Cores Utilizadas

- **Seções que mudam**: `var(--l3)` (vermelho-escuro, #930708 em light mode)
- **Eleitores nelas**: `var(--accent)` (vermelho-bright, #C3090A em light mode)
- **Aptos**: `var(--muted)` (cinza, #6b5f5d em light mode)

Estas cores seguem o design system do dashboard e adaptam-se automaticamente em dark mode.

## Implementação Técnica

### Função `renderTimeline(snapshots)`

Localização: [app.js:60](/app.js:60)

```javascript
function renderTimeline(snapshots) {
  if (!snapshots || snapshots.length < 2) {
    // Mensagem de aviso se menos de 2 snapshots
    return;
  }
  // Mapear snapshots para dados de série temporal
  // Criar 3 gráficos D3 com linhas e pontos
  // Apender ao container #timeline-charts
}
```

### Integração com Navegação

Em `initializeNavigation()`:
- Ao clicar no link de "Linha do tempo", a função checa se `globalThis.allSnapshots` existe
- Se existir, chama `renderTimeline(globalThis.allSnapshots)`
- Garante que os gráficos sejam atualizados sempre que navegamos para a aba

### Armazenamento Global

Em `start()` (função de inicialização):
- Após processar snapshots, salva em `globalThis.allSnapshots = snapshots`
- Permite acesso à lista completa de snapshots em qualquer momento

## Estilo CSS

Adicionado em [styles.css](/styles.css):

```css
.timeline-chart {
  margin: 20px 0;
  border: 1px solid var(--line);
  border-radius: 10px;
  padding: 16px;
  background: var(--bg);
  overflow-x: auto;
}

.timeline-svg {
  width: 100%;
  height: auto;
  min-width: 600px;
}

.timeline-title {
  font-weight: 600;
  font-size: 0.95rem;
  margin-bottom: 12px;
  color: var(--fg);
}
```

Características:
- Responsivo com `overflow-x: auto` para mobile
- Espaçamento consistente com o design system
- Cores adaptáveis entre light/dark mode

## Casos de Uso

### Cenário 1: Uma única carga
Exibe mensagem: "Necessário mínimo 2 cargas para comparação temporal."

### Cenário 2: Múltiplas cargas no mesmo dia
- Cada dropdown de carga em um dia agrupa múltiplos snapshots
- Timeline mostra evolução intradiária (ex: 14h, 15h, 16h)
- Útil para detectar variações rápidas em tempo real

### Cenário 3: Múltiplas cargas em múltiplos dias
- Timeline abrange toda a história do monitoramento
- Permite ver tendências de longo prazo
- Identifica saltos ou anomalias entre dias

## Melhorias Futuras

1. **Tooltips interativos**: Mostrar valores ao passar o mouse
2. **Filtros de data**: Selecionar faixa de tempo para zoom
3. **Comparação de métricas**: Normalizar e mostrar múltiplas em um gráfico
4. **Export**: Baixar dados ou imagem dos gráficos
5. **Estatísticas**: Calcular taxa de mudança, desvio padrão, etc.

## Testes

Os testes de grouping de snapshots cobrem:
- ✓ Agrupamento por dia
- ✓ Ordenação de cargas por extractedAt
- ✓ Suporte a snapshots legados sem extractedAt

Localização: [tests/snapshot-tabs.test.js](/tests/snapshot-tabs.test.js)

Executar: `node --test tests/snapshot-tabs.test.js`

## Troubleshooting

### Gráficos não aparecem
- Verificar se há pelo menos 2 snapshots carregados
- Verificar se D3 foi carregado (deve estar em `globalThis.d3`)
- Abrir DevTools e verificar console para erros

### Horários incorretos
- Verificar timezone do sistema (deve ser "America/Sao_Paulo")
- Timestamps precisam estar em ISO 8601 com Z ou offset +/-HH:MM

### Dados estranhos
- Verificar se `snapshot.data.g` existe e é um array
- Verificar se cada `g.s` é um array com pelo menos `[id, eleitores, aptos]`
