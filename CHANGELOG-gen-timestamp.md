# Mudança: Mostrar Horário na Data de Publicação

## ✅ O que foi arrumado

O texto que dizia:
```
"Lista de seções alteradas no 2º turno publicada pelo TSE em 15/10/2026"
```

Agora mostra:
```
"Lista de seções alteradas no 2º turno publicada pelo TSE em 15/10/2026 às 14:00"
```

## 🔧 Implementação

### Modificação em app.js (linhas 300-313)

**Antes:**
```js
const displayLabel = dayData.loads.length > 1 
  ? `${dayData.label} - ${timeLabel(snapshot)}`
  : dayData.label;
initializeDashboard({
  ...snapshot.data,
  meta: { ...snapshot.data.meta, extractionDate:displayLabel },
}, municipalities, states);
```

**Depois:**
```js
const displayLabel = dayData.loads.length > 1 
  ? `${dayData.label} - ${timeLabel(snapshot)}`
  : dayData.label;
const genLabel = snapshot.extractedAt
  ? `${dayData.label} às ${timeLabel(snapshot)}`
  : snapshot.data.meta.gen;
initializeDashboard({
  ...snapshot.data,
  meta: { ...snapshot.data.meta, extractionDate:displayLabel, gen:genLabel },
}, municipalities, states);
```

## 📊 Exemplos

### Com múltiplas cargas
```
Usuário está visualizando: 19/10/2026, carga 14:00
meta.gen mostra: "19/10/2026 às 14:00"
Texto do dashboard: "... publicada pelo TSE em 19/10/2026 às 14:00"
```

### Com uma única carga
```
Usuário está visualizando: 18/10/2026 (única carga)
meta.gen mostra: "18/10/2026" (sem horário, pois não há extractedAt)
Texto do dashboard: "... publicada pelo TSE em 18/10/2026"
```

## ✨ Benefícios

- ✓ Usuário sabe exatamente quando os dados foram extraídos
- ✓ Informação consistente em toda a interface
- ✓ Funciona automaticamente quando há múltiplas cargas
- ✓ Mantém retrocompatibilidade com dados sem horário

## 🧪 Testes

```bash
$ node --test
✔ 12/12 testes passando
✔ Sintaxe válida
✔ Sem quebra de funcionalidades
```

## 🎯 Impacto

- Linha de resumo no dashboard agora mostra o horário específico da extração
- Usuário tem melhor contexto temporal dos dados que está vendo
- Especialmente útil quando há múltiplas extrações no mesmo dia
