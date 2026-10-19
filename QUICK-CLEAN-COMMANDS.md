# ⚡ COMANDOS RÁPIDOS

Copie e cole estes comandos no PowerShell:

## 1️⃣ LIMPAR A BASE

```powershell
gcloud storage rm gs://extracao_alteracao_locais_votacao/secoes_alteradas_2t_2026.json --project=comite-tecnologia
```

## 2️⃣ EXECUTAR JOB MANUALMENTE

```powershell
gcloud run jobs execute secoes-etl --region=us-central1 --wait --project=comite-tecnologia
```

---

## OU EXECUTE O SCRIPT (FAZ OS DOIS PASSOS)

```powershell
.\clean-and-run.ps1
```

---

## ✅ RESULTADO

Depois de pronto (2-5 minutos):
- ✓ Dashboard com 1 aba única
- ✓ Sem histórico anterior
- ✓ Dados frescos do TSE
- ✓ Acesse: http://localhost:8080/

---

## 📝 ARQUIVOS DE REFERÊNCIA

- `clean-and-run.ps1` - Script automatizado
- `CLEAN-AND-RUN-GUIDE.md` - Guia completo
- `docs/cloud-storage.md` - Documentação técnica
