# ⏰ Agendamento do Cronjob (Cloud Scheduler)

## 📋 Resposta: Por que há mais abas que execuções?

O cronjob está configurado para executar **4 vezes por dia**, mas você pode estar vendo **mais de 4 abas** porque:

1. **Múltiplas execuções podem ser feitas manualmente**
2. **Histórico acumula execuções de vários dias**
3. **A estrutura guarda todas as extrações**, não descarta

## 🕐 Horários de Execução

O cronjob (Cloud Scheduler) está agendado para rodar **4 vezes ao dia**:

```
06:30 AM  (6h30 da manhã) - São Paulo
11:30 AM  (11h30 da manhã)
15:30 PM  (15h30 da tarde)
20:30 PM  (20h30 da noite)
```

**Horário:** São Paulo (`America/Sao_Paulo`)  
**Cron:** `30 6,11,15,20 * * *`

## 📊 Exemplo Prático

Se você tem **8 abas** no dashboard, isso significa:

```
Possibilidade 1: Mais de 2 dias de dados
  Dia 3: [14:00, 12:00, 10:00] (3 execuções)
  Dia 2: [15:30, 11:30, 06:30] (3 execuções)
  Dia 1: [20:30] (1 execução + 1 manual?)

Possibilidade 2: Testes ou execuções manuais
  $ gcloud run jobs execute secoes-etl --region $REGION --wait
  ↑ Isso roda imediatamente, fora do agendamento
```

## 🔧 Arquivo de Configuração

**Localização:** `docs/cloud-storage.md`

### Comando para criar o agendamento:

```powershell
gcloud scheduler jobs create http secoes-etl-4x-daily \
  --location=$REGION \
  --schedule="30 6,11,15,20 * * *" \
  --time-zone="America/Sao_Paulo" \
  --uri="https://run.googleapis.com/v2/projects/$PROJECT/locations/$REGION/jobs/secoes-etl:run" \
  --http-method=POST \
  --oauth-service-account-email="secoes-scheduler@$PROJECT.iam.gserviceaccount.com" \
  --oauth-token-scope="https://www.googleapis.com/auth/cloud-platform" \
  --max-retry-attempts=1 \
  --attempt-deadline=180s
```

## 💾 Como o Histórico Funciona

Cada execução:
1. Baixa as fontes oficiais
2. Valida e transforma os dados
3. **Acrescenta um snapshot completo** ao JSON histórico
4. **NÃO descarta execuções anteriores**

Estrutura do JSON:
```json
{
  "snapshots": [
    {
      "extracted_at": "2026-10-19T14:00:00Z",
      "rows": [...]  // dados completos dessa execução
    },
    {
      "extracted_at": "2026-10-19T11:30:00Z",
      "rows": [...]  // dados completos dessa execução
    },
    // ... mais snapshots ...
  ]
}
```

## 🎯 Por Que Guardar Histórico?

- ✓ Permite ver como os dados mudaram ao longo do dia
- ✓ Facilita comparação entre cargas (sua nova feature!)
- ✓ Auditoria completa das mudanças
- ✓ Reconstruir informações históricas se necessário

## 📈 Crescimento do JSON

Cada execução adiciona um novo snapshot. Com **4 execuções/dia**:

```
Dia 1: 4 snapshots
Dia 2: 4 snapshots (total: 8)
Dia 3: 4 snapshots (total: 12)
...
30 dias: ~120 snapshots

Tamanho estimado: aumenta ~50 KB por execução
(dependendo do número de seções alteradas)
```

## 🚀 Para Aumentar/Diminuir a Frequência

Se quiser mudar para **6 vezes ao dia**, por exemplo:

```powershell
# Alterar para: 04:00, 06:30, 11:30, 15:30, 18:00, 20:30
gcloud scheduler jobs update secoes-etl-4x-daily \
  --schedule="0,30 4,6,11,15,18,20 * * *" \
  --time-zone="America/Sao_Paulo"
```

Ou para **apenas 2 vezes**:

```powershell
# Alterar para: 12:00 e 19:00
gcloud scheduler jobs update secoes-etl-4x-daily \
  --schedule="0 12,19 * * *" \
  --time-zone="America/Sao_Paulo"
```

## ✅ Para Verificar o Agendamento Atual

```powershell
gcloud scheduler jobs describe secoes-etl-4x-daily --location=$REGION
```

Você verá algo como:

```
name: projects/$PROJECT/locations/$REGION/jobs/secoes-etl-4x-daily
schedule: 30 6,11,15,20 * * *
timeZone: America/Sao_Paulo
state: ENABLED
```

## 📝 Para Executar Manualmente

Se quiser testar ou atualizar os dados imediatamente:

```powershell
gcloud run jobs execute secoes-etl --region $REGION --wait
```

⚠️ Isso substitui o JSON publicado, então use apenas quando quiser atualizar o dashboard.

## 🔍 Monitorar Execuções

No Google Cloud Console:
1. Vá para **Cloud Run** → **Jobs**
2. Selecione `secoes-etl`
3. Veja **Executions** para histórico
4. Cada execução mostra: hora, duração, status

Ou via CLI:

```powershell
gcloud run jobs describe secoes-etl --region $REGION
gcloud logging read "resource.type=cloud_run_job AND resource.labels.job_name=secoes-etl" --limit=50
```

## 📊 Resumo

| Item | Valor |
|------|-------|
| **Frequência** | 4x ao dia |
| **Horários** | 06:30, 11:30, 15:30, 20:30 (SP) |
| **Cron** | `30 6,11,15,20 * * *` |
| **Tipo** | Cloud Scheduler + Cloud Run Job |
| **Histórico** | Acumula snapshots, nunca descarta |
| **Arquivo** | `docs/cloud-storage.md` |

---

**Conclusão:** Se você tem mais abas que 4×número_de_dias, pode ser testes/execuções manuais ou dados de mais dias que o esperado. Cada aba = 1 extração, guardada no histórico!
