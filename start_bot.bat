@echo off
REM Script Batch pour lancer le bot HFT avec Rust activé
REM Utilisation: start_bot.bat

echo ================================================================================
echo    HFT TRADING BOT - Demarrage avec Rust
echo ================================================================================
echo.

REM Activer l'environnement virtuel
echo [1/3] Activation de l'environnement virtuel...
cd /d D:\Prototype
call .venv\Scripts\activate.bat

if errorlevel 1 (
    echo    [ERREUR] Echec de l'activation de .venv
    pause
    exit /b 1
)
echo    [OK] Environnement virtuel active
echo.

REM Vérifier que Rust est bien compilé
echo [2/3] Verification du module Rust...
cd /d D:\Prototype\Production

python -c "import hft_rust_core; exit(0 if (hasattr(hft_rust_core, 'STCCalculator') and hasattr(hft_rust_core, 'IchimokuCalculator')) else 1)"
if errorlevel 1 (
    echo    [ATTENTION] Module Rust incomplet - Compilation en cours...
    cd hft_rust_core
    python -m pip install maturin --quiet
    maturin develop --release
    cd ..
) else (
    echo    [OK] Module Rust compile et operationnel
)
echo.

REM Lancer le bot
echo [3/3] Lancement du bot HFT...
echo ================================================================================
python run_hft_bot.py
