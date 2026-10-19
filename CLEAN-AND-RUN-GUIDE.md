# 🧹 Limpando a Base e Executando Manualmente

## Situação Atual
```
Abas no dashboard: 15:33, 15:06, 14:02 (execuções manuais/testes)
Objetivo: Deletar tudo e fazer uma execução limpa
```

## 📋 Passo a Passo

### Passo 1: Deletar o arquivo JSON do Cloud Storage

```powershell
gcloud storage rm gs://extracao_alteracao_locais_votacao/secoes_alteradas_2t_2026.json --project=comite-tecnologia
```

**O que faz:**
- Remove o arquivo JSON histórico
- Próxima execução criará um arquivo novo com apenas 1 snapshot

**Resultado esperado:**
```
Removed gs://extracao_alteracao_locais_votacao/secoes_alteradas_2t_2026.json
```

---

### Passo 2: Executar o Job Manualmente

```powershell
gcloud run jobs execute secoes-etl --region=us-central1 --wait --project=comite-tecnologia
```

**O que faz:**
- Executa o job imediatamente (não espera o cronjob agendado)
- Baixa as fontes oficiais do TSE
- Valida e transforma os dados
- Publica um novo JSON com 1 snapshot único

**Tempo estimado:** 2-5 minutos

**Resultado esperado:**
```
Job execution attempt 1 started.
Waiting for execution to complete...
Job execution attempt 1 completed successfully.
```

---

## ✅ Depois de Pronto

O dashboard terá:
- ✓ 1 aba única (data + horário da execução)
- ✓ Sem histórico anterior
- ✓ Dados frescos do TSE

Acesse: **http://localhost:8080/**

---

## 🚀 Automatizar (Script PowerShell)

Ou execute o script que faz os dois passos:

```powershell
.\clean-and-run.ps1
```

---

## 📊 Estrutura do JSON Após Limpeza

```json
{
  "snapshots": [
    {
      "extracted_at": "2026-10-19T15:42:00Z",
      "rows": [
        { "uf": "SP", "municipio": "...", ... },
        { "uf": "MG", "municipio": "...", ... },
        ...
      ]
    }
  ]
}
```

1 snapshot = 1 aba no dashboard

---

## ⚠️ Considerações

1. **Perda de Histórico**: Você perderá as execuções anteriores (15:33, 15:06, 14:02)
   - Se quer manter, pule o Passo 1

2. **Primeira Execução**: Pode demorar pois precisa baixar arquivos do TSE (~100 MB)

3. **Próximas Execuções**: O cronjob agendado continuará rodando:
   - 06:30, 11:30, 15:30, 20:30 (São Paulo)
   - Cada uma adicionará um snapshot ao arquivo

---

## 🔍 Verificar Status

```powershell
# Ver job
gcloud run jobs describe secoes-etl --region=us-central1 --project=comite-tecnologia

# Ver execuções
gcloud logging read "resource.type=cloud_run_job" --limit=50 --project=comite-tecnologia
```

---

## 📁 Referência

- **Script**: `clean-and-run.ps1`
- **Config**: `pipeline-config.json`
- **Docs**: `docs/cloud-storage.md`
