# 🕐 Cronjob - Resposta Rápida

## Pergunta: Por que tem mais abas que execuções de cronjob?

### 📌 Resposta: Histórico Acumula!

O cronjob executa **4 vezes por dia**, mas o JSON guarda **TODAS** as execuções em um histórico. Não descarta, apenas acumula.

## ⏰ Agendamento Atual

```
06:30 AM  ▶ Execução 1
11:30 AM  ▶ Execução 2
15:30 PM  ▶ Execução 3
20:30 PM  ▶ Execução 4
```

Zona: **São Paulo** (`America/Sao_Paulo`)  
Cron: `30 6,11,15,20 * * *`

## 📊 Exemplo

Se você vê **12 abas**:

```
✓ Dia 3 (hoje):
   ├─ 14:00 (manual ou teste)
   ├─ 11:30 (cronjob)
   └─ 06:30 (cronjob)
   = 3 abas

✓ Dia 2 (ontem):
   ├─ 20:30 (cronjob)
   ├─ 15:30 (cronjob)
   ├─ 11:30 (cronjob)
   └─ 06:30 (cronjob)
   = 4 abas

✓ Dia 1 (anteontem):
   ├─ 20:30 (cronjob)
   ├─ 15:30 (cronjob)
   ├─ 11:30 (cronjob)
   └─ 06:30 (cronjob)
   = 4 abas

Total = 11 abas
(mais uma eventual execução manual = 12)
```

## 🔧 Onde Mudar a Frequência?

**Arquivo:** `docs/cloud-storage.md`

**Comando:**
```powershell
gcloud scheduler jobs update secoes-etl-4x-daily \
  --schedule="30 6,11,15,20 * * *" \
  --time-zone="America/Sao_Paulo"
```

Exemplos:
- `0 6,12,18 * * *` = 3x ao dia (06:00, 12:00, 18:00)
- `0 */4 * * *` = a cada 4 horas (00:00, 04:00, 08:00...)
- `30 10,14,18,22 * * *` = 4x ao dia (10:30, 14:30, 18:30, 22:30)

## 💡 Por Que Guardar Histórico?

✓ Ver como dados mudaram ao longo do dia  
✓ Sua nova feature de "cargas por horário" precisa disso!  
✓ Auditoria completa  
✓ Comparar entre extrações  

## 🚀 Executar Manualmente (Agora!)

```powershell
gcloud run jobs execute secoes-etl --region us-central1 --wait
```

Isso publica um novo snapshot **imediatamente**, sem esperar o próximo agendamento.

## 📈 Impacto no Tamanho

```
1 execução = ~50 KB (varia com seções alteradas)
4 execuções/dia = ~200 KB/dia
30 dias = ~6 MB
```

O JSON fica maior, mas é histórico importante!

---

**Resumo:** ✅ Cronjob executa 4x/dia. Cada execução vira uma aba. Histórico acumula. Não descarta. Por isso há mais abas.
