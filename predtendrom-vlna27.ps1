# PredTendrom.sk - nasadenie vlny 27 (Google Search Console verifikacna znacka)
# Spustit v PowerShell z C:\Projekty\claude\tendre-portal

$ErrorActionPreference = "Stop"

Write-Host "1/5 Kontrola priecinka..." -ForegroundColor Cyan
if (-not (Test-Path ".git")) {
    Write-Host "CHYBA: Tento priecinok nie je git repozitar. Spustite z C:\Projekty\claude\tendre-portal" -ForegroundColor Red
    exit 1
}

Write-Host "2/5 Stiahnutie najnovsieho stavu z GitHub..." -ForegroundColor Cyan
git fetch origin
git checkout main
git pull --ff-only origin main
if ($LASTEXITCODE -ne 0) {
    Write-Host "CHYBA: lokalny main sa nedal zosynchronizovat s origin/main. Zastavujem, nic sa nezmenilo." -ForegroundColor Red
    exit 1
}

Write-Host "3/5 Pridanie balicka zmien (vlna27)..." -ForegroundColor Cyan
git bundle verify predtendrom-vlna27.bundle
if ($LASTEXITCODE -ne 0) {
    Write-Host "CHYBA: balicek predtendrom-vlna27.bundle chyba alebo je poskodeny." -ForegroundColor Red
    exit 1
}
git fetch predtendrom-vlna27.bundle main:vlna27

Write-Host "4/5 Zlucenie do main..." -ForegroundColor Cyan
git merge --ff-only vlna27
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Fast-forward zlyhal (niekto medzitym pushol ine zmeny)." -ForegroundColor Yellow
    Write-Host "Skuste rucne:  git merge --no-edit vlna27" -ForegroundColor Yellow
    Write-Host "a potom:       git push" -ForegroundColor Yellow
    exit 1
}

Write-Host "5/5 Odoslanie na GitHub..." -ForegroundColor Cyan
git push
if ($LASTEXITCODE -ne 0) {
    Write-Host "CHYBA: git push zlyhal. Skontrolujte pripojenie/opravnenia." -ForegroundColor Red
    exit 1
}

Write-Host ""
Write-Host "HOTOVO. Vlna 27 je na GitHub-e." -ForegroundColor Green
Write-Host "Pridava jeden riadok do public/index.html (Google Search Console meta znacka)." -ForegroundColor Green
Write-Host "Po nasadeni (par sekund na Cloudflare) dam vediet a doverim si to v Search Console." -ForegroundColor Green
