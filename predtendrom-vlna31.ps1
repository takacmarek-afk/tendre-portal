$ErrorActionPreference = "Stop"

Write-Host "1/5 Kontrola priecinka..."
if (-not (Test-Path ".git")) {
    Write-Host "CHYBA: Tento skript spustite v priecinku tendre-portal (kde je .git)."
    exit 1
}

Write-Host "2/5 Stiahnutie najnovsieho stavu z GitHub..."
git checkout main
git pull origin main

Write-Host "3/5 Pridanie balicka zmien (vlna31)..."
git bundle verify predtendrom-vlna31.bundle
git fetch predtendrom-vlna31.bundle main:vlna31

Write-Host "4/5 Zlucenie do main..."
git merge --ff-only vlna31
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Fast-forward zlucenie sa nepodarilo (mozna zmena aj na GitHub-e medzicasom)."
    Write-Host "Skuste namiesto toho:"
    Write-Host "  git merge --no-edit vlna31"
    Write-Host "a ak sa objavi konflikt, dajte vediet."
    exit 1
}

Write-Host "5/5 Odoslanie na GitHub..."
git push origin main

Write-Host ""
Write-Host "HOTOVO. Vlna 31 je na GitHub-e."
Write-Host "Prida odkazy na Facebook a Instagram do paticky (index, cennik, obce, servis, trh)"
Write-Host "a nahladovy obrazok pri zdielani (og:image) na trh, zdroje, prihlasenie, servis."
Write-Host "Ziadna databazova migracia, ziadna zmena na produkcnych datach."
