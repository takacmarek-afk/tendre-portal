# PredTendrom.sk - nasadenie vlny 28 (GA4 + Google Tag Manager, Consent Mode v2)
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

Write-Host "3/5 Pridanie balicka zmien (vlna28)..." -ForegroundColor Cyan
git bundle verify predtendrom-vlna28.bundle
if ($LASTEXITCODE -ne 0) {
    Write-Host "CHYBA: balicek predtendrom-vlna28.bundle chyba alebo je poskodeny." -ForegroundColor Red
    exit 1
}
git fetch predtendrom-vlna28.bundle main:vlna28

Write-Host "4/5 Zlucenie do main..." -ForegroundColor Cyan
git merge --ff-only vlna28
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Fast-forward zlyhal (niekto medzitym pushol ine zmeny)." -ForegroundColor Yellow
    Write-Host "Skuste rucne:  git merge --no-edit vlna28" -ForegroundColor Yellow
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
Write-Host "HOTOVO. Vlna 28 je na GitHub-e." -ForegroundColor Green
Write-Host "Pridava Google Analytics 4 + Google Tag Manager s Consent Mode v2:" -ForegroundColor Green
Write-Host "  - novy public/consent-analytics.js (cookie banner + consent default denied)" -ForegroundColor Green
Write-Host "  - GTM snippet vlozeny do vsetkych statickych stranok" -ForegroundColor Green
Write-Host "  - GA4 konverzia 'aktivovany_pouzivatel' pri prvom zapnuti e-mail. odberu" -ForegroundColor Green
Write-Host "  - aktualizovany text v Ochrane osobnych udajov (index.html)" -ForegroundColor Green
Write-Host "Ziadna databazova migracia, ziadna zmena na produkcnych datach." -ForegroundColor Green
