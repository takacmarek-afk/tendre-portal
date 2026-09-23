# PredTendrom.sk - nasadenie vlny 26 (programmatic SEO pre koncicie zmluvy
# + .gitignore oprava). Spustit v PowerShell z C:\Projekty\claude\tendre-portal

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

Write-Host "3/5 Pridanie balicka zmien (vlna26)..." -ForegroundColor Cyan
git bundle verify predtendrom-vlna26.bundle
if ($LASTEXITCODE -ne 0) {
    Write-Host "CHYBA: balicek predtendrom-vlna26.bundle chyba alebo je poskodeny." -ForegroundColor Red
    exit 1
}
git fetch predtendrom-vlna26.bundle main:vlna26

Write-Host "4/5 Zlucenie do main..." -ForegroundColor Cyan
git merge --ff-only vlna26
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Fast-forward zlyhal (niekto medzitym pushol ine zmeny - napr. tyzdenny automat)." -ForegroundColor Yellow
    Write-Host "Skuste rucne:  git merge --no-edit vlna26" -ForegroundColor Yellow
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
Write-Host "HOTOVO. Vlna 26 je na GitHub-e." -ForegroundColor Green
Write-Host "Toto zatial NIC nemeni naostro na webe ani v databaze - pridalo len kod:" -ForegroundColor Green
Write-Host "  - novy SQL subor supabase/44_zmluvy_seo_agregat.sql (treba spustit rucne v Supabase, ked potvrdis hranicu)" -ForegroundColor Green
Write-Host "  - novy generator pipeline/generuj_zmluvy_podstranky.py" -ForegroundColor Green
Write-Host "  - novy GitHub Action .github/workflows/zmluvy-podstranky.yml (len rucne spustitelny, nic nebezi automaticky)" -ForegroundColor Green
Write-Host "  - .gitignore oprava (.scratch/ priecinok)" -ForegroundColor Green
