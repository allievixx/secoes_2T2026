# Implementação Completa: Granularidade por Carga

## 🎯 Objetivo

Mudar a granularidade da visualização de **dia inteiro** para **dia + carga (horário)**, permitindo que o usuário veja múltiplas extrações do mesmo dia em um dropdown.

## ✅ O que foi implementado

### 1. **Agrupamento de Snapshots** (app.js, linhas 253-289)
- Snapshots agrupados por **dia** (chave: YYYY-MM-DD)
- Dentro de cada dia, múltiplas "cargas" ordenadas por **hora (mais recente primeiro)**
- Mantém retrocompatibilidade com snapshots sem `extractedAt`

### 2. **Interface com Dropdown** (app.js, linhas 304-359)
- Aba por dia (botão)
- **Dropdown de cargas** renderizado apenas quando há múltiplas cargas
- Transição suave entre cargas do mesmo dia
- Dropdown aparece visualmente ao lado da aba do dia

### 3. **Styling** (styles.css)
- `.snapshot-load-select` com design coerente com o resto da interface
- Dropdown integrado ao container de abas (flex layout com `align-items: center`)
- Suporte a hover e focus states

### 4. **Testes** (tests/snapshot-tabs.test.js)
- ✓ Agrupa snapshots por dia
- ✓ Ordena cargas por hora (mais recente primeiro)
- ✓ Suporta snapshot sem extractedAt

### 5. **Documentação**
- `CHANGELOG-snapshot-tabs.md` - Guia de mudanças
- `preview-snapshot-tabs.html` - Preview visual da nova interface

## 📊 Estrutura de Dados

```
byDay: Map(
  "2026-10-19" → { key, label: "19/10/2026", loads: [snapshot1, snapshot2, snapshot3] },
  "2026-10-18" → { key, label: "18/10/2026", loads: [snapshot1, snapshot2] },
  ...
)

days: [
  { key: "2026-10-19", label: "19/10/2026", loads: [...] },
  { key: "2026-10-18", label: "18/10/2026", loads: [...] },
  ...
]
```

## 🔧 Mudanças no Código

### app.js - Antes vs Depois

**Antes:**
```js
// Uma aba por dia, apenas a mais recente era exibida
byDay.set(key, { ...snapshot, key, label: dayLabel(snapshot) });
// Quando ativava uma aba, carregava snapshot.data diretamente
```

**Depois:**
```js
// Uma aba por dia, múltiplas cargas dentro
byDay.set(key, { key, label: dayLabel(snapshot), loads: [] });
// Cada dia tem um array de cargas ordenadas
day.loads.push(snapshot);
// Quando ativa uma aba, especifica qual carga (loadIndex)
activate(day.key, 0); // ativa o dia com a carga 0 (mais recente)
```

## 🎨 Interface

```html
<!-- Renderizado dinamicamente para cada dia -->
<div style="display: contents;">
  <button class="snapshot-tab" role="tab" data-day="2026-10-19">
    19/10/2026
  </button>
  <!-- Dropdown aparece se houver múltiplas cargas -->
  <select class="snapshot-load-select" data-day="2026-10-19">
    <option value="0">14:00</option>
    <option value="1">12:00</option>
    <option value="2">10:00</option>
  </select>
</div>
```

## 📱 Accessibility

- ✓ `aria-label` descritivo para dropdowns
- ✓ Navegação por teclado entre dias (Arrow Keys)
- ✓ Suporte a Home/End keys
- ✓ Focus management
- ✓ Rótulo de extração no dashboard mostra horário quando múltiplas cargas

## 🧪 Testes

```bash
# Todos os testes passam
$ node --test
✔ 12 tests, all passed

# Rodar apenas os novos testes
$ node --test tests/snapshot-tabs.test.js
✔ 3 tests, all passed
```

## 🚀 Como Usar

Nenhuma mudança no como o usuário usa a aplicação:

1. Abra a aplicação
2. Veja as abas de dias
3. Se um dia tiver múltiplas cargas, um dropdown aparece
4. Selecione uma carga no dropdown para carregar aquela extração
5. Navegue entre dias com os botões/teclado

## 📝 Retrocompatibilidade

- ✓ Dados com um único snapshot funcionam normalmente
- ✓ Dados sem `extractedAt` são tratados como "Carga atual"
- ✓ API existente não foi alterada
- ✓ Todos os testes existentes passam

## 🔍 Edge Cases Tratados

- ✗ Múltiplas cargas mesmo dia
- ✗ Cargas desordenadas (são reordenadas)
- ✗ Snapshot sem `extractedAt`
- ✗ Um único snapshot
- ✗ Dias sem cargas (impossível, estrutura previne)

## 📦 Arquivos Modificados

| Arquivo | Tipo | Linhas | Descrição |
|---------|------|--------|-----------|
| app.js | Modificado | 253-359 | Lógica de agrupamento e renderização |
| styles.css | Modificado | 49 | Estilos para dropdown |
| tests/snapshot-tabs.test.js | Novo | - | Testes da nova funcionalidade |
| CHANGELOG-snapshot-tabs.md | Novo | - | Documentação de mudanças |
| preview-snapshot-tabs.html | Novo | - | Preview visual |

## ✨ Resultado Final

A aplicação agora permite visualizar e alternar entre **múltiplas cargas no mesmo dia**, com uma interface intuitiva e acessível que mantém a granularidade de dias como contexto principal.
