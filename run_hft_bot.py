#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Point d'entrée principal du bot HFT - Nouveau système modulaire
"""

import sys
import signal
from pathlib import Path
from datetime import datetime

# Ajouter le chemin du projet
sys.path.insert(0, str(Path(__file__).parent))

from config.trading_config import TradingConfig
from config.settings_manager import SettingsManager, extract_saveable_config, apply_saved_settings
from gui.main_window import HFTBotGUI
from utils.logger import setup_logging

# Pour l'interface de configuration
import os

# Configuration du logging
log_file = f"hft_bot_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
logger = setup_logging(log_level="INFO", log_file=log_file)


def signal_handler(sig, frame):
    """Gestionnaire de signal pour arrêt gracieux"""
    logger.info("Signal d'interruption reçu (Ctrl+C)")
    sys.exit(0)


def print_config_summary(config: TradingConfig) -> None:
    """Affiche un résumé de la configuration Circuit Breaker"""
    print("\n" + "=" * 80)
    print("📊 RÉSUMÉ DE LA CONFIGURATION")
    print("=" * 80)
    
    active_count = sum([
        config.risk_daily_loss_enabled,
        config.risk_daily_trades_enabled,
        config.risk_consecutive_losses_enabled,
        config.risk_drawdown_enabled,
        config.risk_correlation_enabled,
        config.risk_portfolio_enabled
    ])
    
    if config.circuit_breaker_enabled:
        print(f"\n✅ Circuit Breaker: ACTIVÉ")
        print(f"📊 Protections actives: {active_count}/6")
        print()
        
        if config.risk_daily_loss_enabled:
            print(f"  ✓ Perte journalière: {config.risk_max_daily_loss}$")
        else:
            print(f"  ✗ Perte journalière: DÉSACTIVÉE")
        
        if config.risk_daily_trades_enabled:
            print(f"  ✓ Trades journaliers: {config.risk_max_daily_trades}")
        else:
            print(f"  ✗ Trades journaliers: DÉSACTIVÉ")
        
        if config.risk_consecutive_losses_enabled:
            print(f"  ✓ Pertes consécutives: {config.risk_max_consecutive_losses} (cooldown {config.risk_cooldown_after_loss_streak_minutes}min)")
        else:
            print(f"  ✗ Pertes consécutives: DÉSACTIVÉ")
        
        if config.risk_drawdown_enabled:
            print(f"  ✓ Drawdown: {config.risk_max_drawdown_percent}%")
        else:
            print(f"  ✗ Drawdown: DÉSACTIVÉ")
        
        if config.risk_correlation_enabled:
            print(f"  ✓ Corrélation: {config.risk_max_correlated_positions} positions")
        else:
            print(f"  ✗ Corrélation: DÉSACTIVÉE")
        
        if config.risk_portfolio_enabled:
            print(f"  ✓ Risque portefeuille: {config.risk_max_portfolio_risk_percent}%")
        else:
            print(f"  ✗ Risque portefeuille: DÉSACTIVÉ")
        
        # Niveau de protection
        if active_count == 6:
            print("\n🟢 Niveau de protection: MAXIMAL ✅")
        elif active_count >= 4:
            print("\n🟡 Niveau de protection: STANDARD ⚠️")
        elif active_count >= 2:
            print("\n🟠 Niveau de protection: MINIMAL ⚠️⚠️")
        else:
            print("\n🔴 Niveau de protection: INSUFFISANT ❌")
    else:
        print("\n❌ Circuit Breaker: DÉSACTIVÉ")
        print("⚠️⚠️⚠️ AUCUNE PROTECTION ACTIVE ⚠️⚠️⚠️")
    
    print("\n" + "=" * 80)


def configure_circuit_breaker(config: TradingConfig) -> TradingConfig:
    """
    Interface interactive pour configurer le Circuit Breaker
    """
    print("\n" + "=" * 80)
    print("⚙️  CONFIGURATION DU CIRCUIT BREAKER")
    print("=" * 80)
    
    print("\n💡 Conseil: Gardez toutes les protections activées en production")
    print("   Désactivez uniquement pour backtesting ou si vous êtes expert\n")
    
    # Proposer des presets
    print("📚 PRESETS DISPONIBLES:")
    print("   [1] Configuration actuelle (personnaliser)")
    print("   [2] 🟢 CONSERVATIVE - Protection maximale (débutant)")
    print("   [3] 🟡 ÉQUILIBRÉE - Standard (recommandé)")
    print("   [4] 🔴 AGRESSIVE - Protection minimale (expert)")
    print("   [5] ⚫ DÉSACTIVÉ - Aucune protection (backtest uniquement)")
    
    preset = input("\nChoisir un preset [1-5] [défaut: 1]: ").strip()
    
    if preset == '2':  # Conservative
        print("\n✅ Preset CONSERVATIVE appliqué")
        config.circuit_breaker_enabled = True
        config.risk_daily_loss_enabled = True
        config.risk_daily_trades_enabled = True
        config.risk_consecutive_losses_enabled = True
        config.risk_drawdown_enabled = True
        config.risk_correlation_enabled = True
        config.risk_portfolio_enabled = True
        config.risk_max_daily_loss = 200.0
        config.risk_max_daily_trades = 30
        config.risk_max_consecutive_losses = 3
        config.risk_max_drawdown_percent = 8.0
        config.risk_max_correlated_positions = 2
        config.risk_max_portfolio_risk_percent = 15.0
        print_config_summary(config)
        return config
        
    elif preset == '3':  # Équilibrée (défaut)
        print("\n✅ Preset ÉQUILIBRÉE appliqué")
        config.circuit_breaker_enabled = True
        config.risk_daily_loss_enabled = True
        config.risk_daily_trades_enabled = True
        config.risk_consecutive_losses_enabled = True
        config.risk_drawdown_enabled = True
        config.risk_correlation_enabled = True
        config.risk_portfolio_enabled = True
        config.risk_max_daily_loss = 500.0
        config.risk_max_daily_trades = 50
        config.risk_max_consecutive_losses = 5
        config.risk_max_drawdown_percent = 10.0
        config.risk_max_correlated_positions = 3
        config.risk_max_portfolio_risk_percent = 20.0
        print_config_summary(config)
        return config
        
    elif preset == '4':  # Agressive
        print("\n⚠️ Preset AGRESSIVE appliqué")
        config.circuit_breaker_enabled = True
        config.risk_daily_loss_enabled = True
        config.risk_daily_trades_enabled = False
        config.risk_consecutive_losses_enabled = False
        config.risk_drawdown_enabled = True
        config.risk_correlation_enabled = False
        config.risk_portfolio_enabled = False
        config.risk_max_daily_loss = 1000.0
        config.risk_max_drawdown_percent = 15.0
        print_config_summary(config)
        return config
        
    elif preset == '5':  # Désactivé
        print("\n⚠️⚠️⚠️ ATTENTION: Mode SANS PROTECTION ⚠️⚠️⚠️")
        print("    Le bot peut perdre tout le capital sans limite!")
        confirm = input("    Confirmez-vous (taper 'D' en majuscules): ").strip()
        if confirm == 'D':
            config.circuit_breaker_enabled = False
            print("    → Circuit Breaker DÉSACTIVÉ")
        else:
            print("    → Annulation, retour au preset ÉQUILIBRÉE")
            config.circuit_breaker_enabled = True
            config.risk_daily_loss_enabled = True
            config.risk_daily_trades_enabled = True
            config.risk_consecutive_losses_enabled = True
            config.risk_drawdown_enabled = True
            config.risk_correlation_enabled = True
            config.risk_portfolio_enabled = True
        print_config_summary(config)
        return config
    
    # Configuration personnalisée (preset 1 ou défaut)
    
    # Protection globale
    print("🔴 [1] Circuit Breaker Global")
    current = "ACTIVÉ ✅" if config.circuit_breaker_enabled else "DÉSACTIVÉ ❌"
    print(f"    État actuel: {current}")
    response = input("    Modifier? (o/n) [défaut: n]: ").lower().strip()
    if response in ['o', 'oui', 'y', 'yes']:
        config.circuit_breaker_enabled = not config.circuit_breaker_enabled
        new_state = "ACTIVÉ ✅" if config.circuit_breaker_enabled else "DÉSACTIVÉ ❌"
        print(f"    → Nouveau: {new_state}")
    
    if not config.circuit_breaker_enabled:
        print("\n⚠️⚠️⚠️ ATTENTION: Circuit Breaker désactivé - Aucune protection ⚠️⚠️⚠️")
        print("    Le bot peut perdre tout le capital sans limite!")
        confirm = input("\n    Confirmez-vous (DANGER)? (oui/non): ").lower().strip()
        if confirm != 'oui':
            print("    → Réactivation du Circuit Breaker par sécurité")
            config.circuit_breaker_enabled = True
        else:
            print("    → Vous avez été prévenu. Aucune protection active.")
            return config  # Sortir, les autres protections sont inutiles
    
    print("\n" + "-" * 80)
    print("🛡️  PROTECTIONS INDIVIDUELLES")
    print("-" * 80)
    
    # Protection 1: Perte journalière
    print("\n[2] Protection Perte Journalière")
    current = "ACTIVÉE ✅" if config.risk_daily_loss_enabled else "DÉSACTIVÉE ❌"
    print(f"    État: {current} | Limite: {config.risk_max_daily_loss}$")
    response = input("    Modifier? (o/n) [défaut: n]: ").lower().strip()
    if response in ['o', 'oui', 'y', 'yes']:
        config.risk_daily_loss_enabled = not config.risk_daily_loss_enabled
        if config.risk_daily_loss_enabled:
            try:
                new_limit = input(f"    Nouvelle limite en $ [{config.risk_max_daily_loss}]: ").strip()
                if new_limit:
                    config.risk_max_daily_loss = float(new_limit)
            except ValueError:
                print("    → Valeur invalide, limite conservée")
    
    # Protection 2: Overtrading
    print("\n[3] Protection Overtrading")
    current = "ACTIVÉE ✅" if config.risk_daily_trades_enabled else "DÉSACTIVÉE ❌"
    print(f"    État: {current} | Limite: {config.risk_max_daily_trades} trades/jour")
    response = input("    Modifier? (o/n) [défaut: n]: ").lower().strip()
    if response in ['o', 'oui', 'y', 'yes']:
        config.risk_daily_trades_enabled = not config.risk_daily_trades_enabled
        if config.risk_daily_trades_enabled:
            try:
                new_limit = input(f"    Nouvelle limite [{config.risk_max_daily_trades}]: ").strip()
                if new_limit:
                    config.risk_max_daily_trades = int(new_limit)
            except ValueError:
                print("    → Valeur invalide, limite conservée")
    
    # Protection 3: Pertes consécutives
    print("\n[4] Protection Pertes Consécutives")
    current = "ACTIVÉE ✅" if config.risk_consecutive_losses_enabled else "DÉSACTIVÉE ❌"
    print(f"    État: {current} | Max: {config.risk_max_consecutive_losses} pertes")
    print(f"    Cooldown: {config.risk_cooldown_after_loss_streak_minutes} minutes")
    response = input("    Modifier? (o/n) [défaut: n]: ").lower().strip()
    if response in ['o', 'oui', 'y', 'yes']:
        config.risk_consecutive_losses_enabled = not config.risk_consecutive_losses_enabled
        if config.risk_consecutive_losses_enabled:
            try:
                new_limit = input(f"    Nouveau max pertes [{config.risk_max_consecutive_losses}]: ").strip()
                if new_limit:
                    config.risk_max_consecutive_losses = int(new_limit)
                new_cooldown = input(f"    Nouveau cooldown minutes [{config.risk_cooldown_after_loss_streak_minutes}]: ").strip()
                if new_cooldown:
                    config.risk_cooldown_after_loss_streak_minutes = int(new_cooldown)
            except ValueError:
                print("    → Valeur invalide, limites conservées")
    
    # Protection 4: Drawdown
    print("\n[5] Protection Drawdown")
    current = "ACTIVÉE ✅" if config.risk_drawdown_enabled else "DÉSACTIVÉE ❌"
    print(f"    État: {current} | Max: {config.risk_max_drawdown_percent}%")
    response = input("    Modifier? (o/n) [défaut: n]: ").lower().strip()
    if response in ['o', 'oui', 'y', 'yes']:
        config.risk_drawdown_enabled = not config.risk_drawdown_enabled
        if config.risk_drawdown_enabled:
            try:
                new_limit = input(f"    Nouveau max drawdown % [{config.risk_max_drawdown_percent}]: ").strip()
                if new_limit:
                    config.risk_max_drawdown_percent = float(new_limit)
            except ValueError:
                print("    → Valeur invalide, limite conservée")
    
    # Protection 5: Corrélation
    print("\n[6] Protection Corrélation")
    current = "ACTIVÉE ✅" if config.risk_correlation_enabled else "DÉSACTIVÉE ❌"
    print(f"    État: {current} | Max: {config.risk_max_correlated_positions} positions/direction")
    response = input("    Modifier? (o/n) [défaut: n]: ").lower().strip()
    if response in ['o', 'oui', 'y', 'yes']:
        config.risk_correlation_enabled = not config.risk_correlation_enabled
        if config.risk_correlation_enabled:
            try:
                new_limit = input(f"    Nouveau max positions [{config.risk_max_correlated_positions}]: ").strip()
                if new_limit:
                    config.risk_max_correlated_positions = int(new_limit)
            except ValueError:
                print("    → Valeur invalide, limite conservée")
    
    # Protection 6: Risque portefeuille
    print("\n[7] Protection Risque Portefeuille")
    current = "ACTIVÉE ✅" if config.risk_portfolio_enabled else "DÉSACTIVÉE ❌"
    print(f"    État: {current} | Max: {config.risk_max_portfolio_risk_percent}%")
    response = input("    Modifier? (o/n) [défaut: n]: ").lower().strip()
    if response in ['o', 'oui', 'y', 'yes']:
        config.risk_portfolio_enabled = not config.risk_portfolio_enabled
        if config.risk_portfolio_enabled:
            try:
                new_limit = input(f"    Nouveau max risque % [{config.risk_max_portfolio_risk_percent}]: ").strip()
                if new_limit:
                    config.risk_max_portfolio_risk_percent = float(new_limit)
            except ValueError:
                print("    → Valeur invalide, limite conservée")
    
    # Afficher le résumé
    print_config_summary(config)
    
    # Confirmation finale
    confirm = input("\n✅ Lancer le bot avec cette configuration? (o/n) [défaut: o]: ").lower().strip()
    if confirm in ['n', 'non', 'no']:
        print("\n❌ Lancement annulé")
        sys.exit(0)
    
    return config


def main():
    """Fonction principale"""
    
    print("=" * 80)
    print("🤖 HFT TRADING BOT - SYSTÈME MODULAIRE PYTHON/RUST v2.0")
    print("=" * 80)
    print(f"Version: 2.0.0 - AMÉLIORATIONS COMPLÈTES")
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print("=" * 80)
    
    # Afficher les améliorations v2.0
    print("\n🚀 NOUVELLES FONCTIONNALITÉS v2.0:")
    print("   ✅ Circuit Breaker & Risk Manager (protection capital)")
    print("   ✅ Filtrage Multi-Timeframe M15/M30/H1/H4 (4 TF)")
    print("   ✅ Rust Computing STC (25x plus rapide)")
    print("   ✅ Volume Dynamique ATR + ML (adaptatif)")
    print("   ✅ Trailing Stop 2 phases (protection profits)")
    print("   ✅ Protection Corrélation (limite positions)")
    print("   ✅ 🌊 Sweep Progressif - Martingale Additive")
    print()
    
    # Configuration du signal handler
    signal.signal(signal.SIGINT, signal_handler)
    
    # Charger la configuration
    logger.info("Chargement de la configuration...")
    config = TradingConfig()
    
    # 🆕 Charger les paramètres sauvegardés
    settings_mgr = SettingsManager()
    saved_settings = settings_mgr.load_settings()
    
    if saved_settings:
        applied = apply_saved_settings(config, saved_settings)
        print(f"\n💾 {applied} paramètres restaurés depuis la dernière session")
        logger.info(f"✅ {applied} paramètres restaurés")
    
    # Interface de configuration Circuit Breaker
    print("\n")
    configure_cb = input("⚙️  Configurer le Circuit Breaker avant lancement? (o/n) [défaut: n]: ").lower().strip()
    if configure_cb in ['o', 'oui', 'y', 'yes']:
        config = configure_circuit_breaker(config)
    else:
        print("✅ Configuration par défaut utilisée (toutes protections activées)")
    
    logger.info(f"Symbole: {config.symbol}")
    logger.info(f"Lots initiaux: {config.position_sizes}")
    logger.info(f"Positions max: {config.max_positions}")
    logger.info(f"SL base: {config.base_sl_distance}$")
    logger.info(f"TP base: {config.base_tp_distance}$")
    
    # 🌊 Configuration Sweep
    sweep_base = getattr(config, 'sweep_base_volume', 0.01)
    logger.info(f"🌊 Sweep - Mise de base: {sweep_base:.2f} lots")
    logger.info(f"🌊 Sweep - Progression: 1×{sweep_base:.2f} | 2×{sweep_base*2:.2f} | 3×{sweep_base*3:.2f} | 4×{sweep_base*4:.2f}")
    
    # Vérifier si Rust est disponible
    try:
        import hft_rust_core
        rust_available = hasattr(hft_rust_core, 'STCCalculator') and hasattr(hft_rust_core, 'IchimokuCalculator')
        
        if rust_available:
            logger.info("✅ Module Rust chargé - Performances optimales")
            print("\n✅ Module Rust détecté:")
            print("   - TickBuffer: Rust (ultra-rapide)")
            print("   - Ichimoku: Rust (15-25x plus rapide)")
            print("   - STC: Rust (10-20x plus rapide)")
            print("   - Signaux: Rust (<1µs)")
        else:
            logger.warning("⚠️ Module Rust incomplet - Recompiler avec: maturin develop --release")
            print("\n⚠️ Module Rust incomplet (classes manquantes):")
            print("   - TickBuffer: OK")
            print("   - STCCalculator: ❌ Manquant")
            print("   - IchimokuCalculator: ❌ Manquant")
            print("\n   Pour activer toutes les fonctionnalités Rust:")
            print("   cd Production/hft_rust_core")
            print("   maturin develop --release")
            print("\n   Mode actuel: Python fallback (10-50x plus lent)")
    except ImportError:
        logger.warning("⚠️ Module Rust non disponible - Fallback Python")
        print("\n⚠️ Module Rust non compilé:")
        print("   Pour performances optimales, compiler avec:")
        print("   cd Production/hft_rust_core")
        print("   pip install maturin")
        print("   maturin develop --release")
        print("\n   Mode actuel: Python pur (10-50x plus lent)")
    
    print("\n" + "=" * 80)
    print("Lancement de l'interface graphique...")
    print("=" * 80)
    
    # Créer et lancer l'interface
    try:
        gui = HFTBotGUI(config)
        logger.info("Interface graphique créée")
        
        print("\n✅ Interface prête!")
        print("   - Cliquez sur '▶ Démarrer' pour lancer le bot")
        print("   - Surveillez le dashboard pour les métriques")
        print("   - Logs disponibles dans l'onglet '📝 Logs'")
        print("\n" + "=" * 80)
        
        # Lancer la boucle GUI (bloquant)
        gui.run()
        
        # 🆕 Sauvegarder les paramètres à la fermeture
        print("\n💾 Sauvegarde des paramètres...")
        current_settings = extract_saveable_config(config)
        if settings_mgr.save_settings(current_settings):
            print(f"✅ {len(current_settings)} paramètres sauvegardés pour la prochaine session")
        
    except KeyboardInterrupt:
        print("\n\n⚠️ Interruption utilisateur (Ctrl+C)")
        logger.info("Interruption utilisateur")
        
        # Sauvegarder même en cas d'interruption
        try:
            current_settings = extract_saveable_config(config)
            settings_mgr.save_settings(current_settings)
            print("💾 Paramètres sauvegardés")
        except:
            pass
        
    except Exception as e:
        logger.error(f"Erreur fatale: {e}", exc_info=True)
        print(f"\n❌ ERREUR: {e}")
        
        # Tenter de sauvegarder même en cas d'erreur
        try:
            current_settings = extract_saveable_config(config)
            settings_mgr.save_settings(current_settings)
        except:
            pass
        
        sys.exit(1)
    
    logger.info("Application terminée")


if __name__ == "__main__":
    main()
