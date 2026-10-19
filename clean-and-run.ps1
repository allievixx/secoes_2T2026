#!/usr/bin/env powershell
# Script para limpar a base e fazer execução manual

# Configurações
$BUCKET = "extracao_alteracao_locais_votacao"
$OBJECT = "secoes_alteradas_2t_2026.json"
$REGION = "us-central1"
$PROJECT = "comite-tecnologia"
$JOB_NAME = "secoes-etl"

Write-Host "========================================" -ForegroundColor Cyan
Write-Host "LIMPANDO BASE E EXECUTANDO JOB" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
Write-Host ""

# Passo 1: Deletar o arquivo JSON
Write-Host "[1/2] Deletando arquivo JSON do Cloud Storage..." -ForegroundColor Yellow
Write-Host "      gs://$BUCKET/$OBJECT" -ForegroundColor Gray
Write-Host ""

$deleteCmd = "gcloud storage rm gs://$BUCKET/$OBJECT --project=$PROJECT"
Write-Host "Comando:" -ForegroundColor Gray
Write-Host "  $deleteCmd" -ForegroundColor Gray
Write-Host ""

Write-Host "Executando..." -ForegroundColor Cyan
Invoke-Expression $deleteCmd
$deleteStatus = $LASTEXITCODE

if ($deleteStatus -eq 0) {
    Write-Host "✓ Arquivo deletado com sucesso!" -ForegroundColor Green
} else {
    Write-Host "⚠ Aviso: arquivo pode não existir ou houve erro" -ForegroundColor Yellow
}
Write-Host ""

# Passo 2: Executar o job manualmente
Write-Host "[2/2] Executando job manualmente..." -ForegroundColor Yellow
Write-Host "      Job: $JOB_NAME" -ForegroundColor Gray
Write-Host "      Região: $REGION" -ForegroundColor Gray
Write-Host ""

$runCmd = "gcloud run jobs execute $JOB_NAME --region=$REGION --wait --project=$PROJECT"
Write-Host "Comando:" -ForegroundColor Gray
Write-Host "  $runCmd" -ForegroundColor Gray
Write-Host ""

Write-Host "Executando... (isso pode demorar alguns minutos)" -ForegroundColor Cyan
Invoke-Expression $runCmd
$runStatus = $LASTEXITCODE

Write-Host ""
if ($runStatus -eq 0) {
    Write-Host "✓ Job executado com sucesso!" -ForegroundColor Green
    Write-Host ""
    Write-Host "📝 Novo arquivo JSON foi criado com 1 snapshot único" -ForegroundColor Cyan
    Write-Host "   Acesse: http://localhost:8080/" -ForegroundColor Cyan
    Write-Host "   Você verá apenas 1 aba com a data/hora da execução" -ForegroundColor Cyan
} else {
    Write-Host "✗ Erro ao executar job" -ForegroundColor Red
}

Write-Host ""
Write-Host "========================================" -ForegroundColor Cyan
Write-Host "PRONTO!" -ForegroundColor Cyan
Write-Host "========================================" -ForegroundColor Cyan
