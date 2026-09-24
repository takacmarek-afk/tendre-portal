$ErrorActionPreference = "Stop"

Write-Host "1/5 Kontrola priecinka..."
if (-not (Test-Path ".git")) {
    Write-Host "CHYBA: Tento skript spustite v priecinku tendre-portal (kde je .git)."
    exit 1
}

Write-Host "2/5 Stiahnutie najnovsieho stavu z GitHub..."
git checkout main
git pull origin main

Write-Host "3/5 Pridanie balicka zmien (vlna32)..."
git bundle verify predtendrom-vlna32.bundle
git fetch predtendrom-vlna32.bundle main:vlna32

Write-Host "4/5 Zlucenie do main..."
git merge --ff-only vlna32
if ($LASTEXITCODE -ne 0) {
    Write-Host ""
    Write-Host "Fast-forward zlucenie sa nepodarilo (mozna zmena aj na GitHub-e medzicasom)."
    Write-Host "Skuste namiesto toho:"
    Write-Host "  git merge --no-edit vlna32"
    Write-Host "a ak sa objavi konflikt, dajte vediet."
    exit 1
}

Write-Host "5/5 Odoslanie na GitHub..."
git push origin main

Write-Host ""
Write-Host "HOTOVO. Vlna 32 je na GitHub-e."
Write-Host "Prida tlacidla Facebook a Instagram vedla telefonu a e-mailu v sekcii Zakladatel (index, cennik)."
Write-Host "Ziadna databazova migracia, ziadna zmena na produkcnych datach."
