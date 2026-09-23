# PredTendrom.sk — nasadenie vlny 24 (Start dostava cenovy benchmark)
# Spusti v PowerSheli v priecinku C:\Projekty\claude\tendre-portal
# (skript sa vie spustit aj odkialkolvek, cd si urobi sam).

$repo = "C:\Projekty\claude\tendre-portal"
$bundle = Join-Path $repo "predtendrom-vlna24.bundle"

if (-not (Test-Path $repo)) {
    Write-Host "CHYBA: priecinok $repo neexistuje." -ForegroundColor Red
    exit 1
}
Set-Location $repo

if (-not (Test-Path $bundle)) {
    Write-Host "CHYBA: $bundle sa nenasiel. Skontroluj, ci je subor v tomto priecinku." -ForegroundColor Red
    exit 1
}

# Najdi git.exe — bud v PATH, alebo zabaleny v GitHub Desktop
$git = Get-Command git -ErrorAction SilentlyContinue
if ($git) {
    $gitExe = $git.Source
} else {
    $found = Get-ChildItem "$env:LOCALAPPDATA\GitHubDesktop" -Recurse -Filter git.exe -ErrorAction SilentlyContinue | Select-Object -First 1
    if (-not $found) {
        Write-Host "CHYBA: git.exe sa nenasiel ani v PATH ani v GitHub Desktop." -ForegroundColor Red
        exit 1
    }
    $gitExe = $found.FullName
}
Write-Host "Pouzivam git: $gitExe"

& $gitExe bundle verify $bundle
if ($LASTEXITCODE -ne 0) { Write-Host "CHYBA: bundle sa neoveril." -ForegroundColor Red; exit 1 }

& $gitExe pull
& $gitExe fetch $bundle main:vlna24
if ($LASTEXITCODE -ne 0) { Write-Host "CHYBA: fetch zlyhal." -ForegroundColor Red; exit 1 }

& $gitExe merge --ff-only vlna24
if ($LASTEXITCODE -ne 0) { Write-Host "CHYBA: merge zlyhal (nie je fast-forward?)." -ForegroundColor Red; exit 1 }

& $gitExe push
if ($LASTEXITCODE -ne 0) { Write-Host "CHYBA: push zlyhal." -ForegroundColor Red; exit 1 }

& $gitExe branch -d vlna24
Remove-Item $bundle -ErrorAction SilentlyContinue

Write-Host "HOTOVO" -ForegroundColor Green
