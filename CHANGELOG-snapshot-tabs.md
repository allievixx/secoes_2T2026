# Mudança de Granularidade das Abas: Dia → Dia + Cargas

## O que mudou

A granularidade de visualização dos dados agora é **por carga (horário)** em vez de por dia inteiro.

### Antes
- Uma aba por dia inteiro (ex: "17/10/2026")
- Quando havia múltiplas extrações no mesmo dia, apenas a mais recente era exibida

### Depois
- Uma aba por **dia**
- Dentro de cada dia, um **dropdown** mostrando as cargas/horários disponíveis
- Você pode alternar rapidamente entre cargas do mesmo dia

## Implementação

### Arquivos modificados

1. **app.js** (linhas 253-359)
   - Nova lógica de agrupamento: snapshots agrupados por dia (chave: YYYY-MM-DD)
   - Dentro de cada dia, múltiplas "cargas" ordenadas por hora de extração (mais recente primeiro)
   - Função `activate()` agora recebe `(day, loadIndex)` para ativar um dia e uma carga específica
   - Novo elemento `<select>` renderizado apenas quando há múltiplas cargas no dia

2. **styles.css** (linha 49)
   - Novo estilo `.snapshot-load-select` para o dropdown de cargas
   - Padding, border, border-radius e styling em sintonia com o design existente
   - `.snapshot-tabs` agora tem `align-items: center` para alinhar com o dropdown

3. **tests/snapshot-tabs.test.js** (novo arquivo)
   - Testes que validam o agrupamento de snapshots por dia
   - Verificam a ordenação de cargas por hora de extração

## Como funciona

```
Dia 1 (19/10/2026)
  ├─ Carga 1 (14:00)  ← Mais recente, selecionada por padrão
  ├─ Carga 2 (12:00)
  └─ Carga 3 (10:00)

Dia 2 (18/10/2026)
  ├─ Carga 1 (09:00)
  └─ Carga 2 (08:00)
```

Quando você clica em um dia, o dashboard mostra a carga mais recente daquele dia.
Se houver múltiplas cargas, você pode selecionar outra usando o dropdown.

## Accessibility

- O dropdown tem um `aria-label` descritivo
- Os dropdowns aparecem apenas quando necessário (múltiplas cargas)
- A navegação por teclado (arrows, Home, End) continua funcionando entre dias
- O rótulo de extração no dashboard mostra o horário quando há múltiplas cargas

## Testes

Rode os novos testes com:

```bash
node --test tests/snapshot-tabs.test.js
```

Resultado esperado:
- ✔ agrupa snapshots por dia
- ✔ mantém ordem de cargas por data de extração
- ✔ suporta snapshot sem extractedAt (carga atual)
