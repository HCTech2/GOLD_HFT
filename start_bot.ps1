# Script PowerShell pour lancer le bot HFT avec Rust activé
# Utilisation: .\start_bot.ps1

Write-Host "================================================================================" -ForegroundColor Cyan
Write-Host "   HFT TRADING BOT - Démarrage avec Rust" -ForegroundColor Cyan
Write-Host "================================================================================" -ForegroundColor Cyan

# Activer l'environnement virtuel
Write-Host "`n[1/3] Activation de l'environnement virtuel..." -ForegroundColor Yellow
Set-Location "D:\Prototype"
& ".\.venv\Scripts\Activate.ps1"

if ($LASTEXITCODE -ne 0 -and $null -ne $LASTEXITCODE) {
    Write-Host "   [ERREUR] Échec de l'activation de .venv" -ForegroundColor Red
    exit 1
}
Write-Host "   [OK] Environnement virtuel activé" -ForegroundColor Green

# Vérifier que Rust est bien compilé
Write-Host "`n[2/3] Vérification du module Rust..." -ForegroundColor Yellow
Set-Location "D:\Prototype\Production"
$rustCheck = python -c "import hft_rust_core; print(hasattr(hft_rust_core, 'STCCalculator') and hasattr(hft_rust_core, 'IchimokuCalculator'))"

if ($rustCheck -eq "True") {
    Write-Host "   [OK] Module Rust compilé et opérationnel" -ForegroundColor Green
} else {
    Write-Host "   [ATTENTION] Module Rust incomplet - Compilation en cours..." -ForegroundColor Yellow
    Set-Location "hft_rust_core"
    python -m pip install maturin --quiet
    maturin develop --release
    Set-Location ".."
}

# Lancer le bot
Write-Host "`n[3/3] Lancement du bot HFT..." -ForegroundColor Yellow
Write-Host "================================================================================" -ForegroundColor Cyan
python run_hft_bot.py
