#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestionnaire centralisé des presets de configuration
Tous les presets sont définis ici et paramétrables via GUI
"""

import logging
from typing import Dict, List, Tuple
from dataclasses import dataclass

from config.trading_config import TradingConfig

logger = logging.getLogger(__name__)


@dataclass
class PresetInfo:
    """Information sur un preset"""
    id: int
    name: str
    description: str
    emoji: str
    risk_level: str  # LOW, MEDIUM, HIGH, EXTREME
    recommended_for: str


class PresetManager:
    """
    Gestionnaire centralisé des presets de configuration
    
    6 Presets disponibles:
    1. Personnalisé - Configuration manuelle
    2. Conservative - Protection maximale (débutant)
    3. Équilibrée - Standard (recommandé)
    4. Agressive - Protection minimale (expert)
    5. Désactivé - Aucune protection (backtest)
    6. ULTRA-RÉACTIF - Trading continu (expert)
    """
    
    # Définition des presets
    PRESETS: Dict[int, PresetInfo] = {
        1: PresetInfo(
            id=1,
            name="Personnalisé",
            description="Configuration actuelle (personnaliser)",
            emoji="⚙️",
            risk_level="CUSTOM",
            recommended_for="Utilisateurs avancés voulant personnaliser chaque paramètre"
        ),
        2: PresetInfo(
            id=2,
            name="Conservative",
            description="Protection maximale (débutant)",
            emoji="🟢",
            risk_level="LOW",
            recommended_for="Débutants, petits comptes (<500$), apprentissage"
        ),
        3: PresetInfo(
            id=3,
            name="Équilibrée",
            description="Standard (recommandé)",
            emoji="🟡",
            risk_level="MEDIUM",
            recommended_for="Comptes moyens (500-5000$), trading quotidien"
        ),
        4: PresetInfo(
            id=4,
            name="Agressive",
            description="Protection minimale (expert)",
            emoji="🔴",
            risk_level="HIGH",
            recommended_for="Experts, gros comptes (>5000$), haute tolérance au risque"
        ),
        5: PresetInfo(
            id=5,
            name="Désactivé",
            description="Aucune protection (backtest uniquement)",
            emoji="⚫",
            risk_level="EXTREME",
            recommended_for="Backtesting uniquement, JAMAIS en production"
        ),
        6: PresetInfo(
            id=6,
            name="ULTRA-RÉACTIF",
            description="Trading continu (expert - nouveau)",
            emoji="🔥",
            risk_level="HIGH",
            recommended_for="Experts, mode HFT, surveillance active"
        )
    }
    
    @staticmethod
    def get_preset_list() -> List[Tuple[int, str, str]]:
        """
        Retourne la liste des presets pour affichage
        
        Returns:
            Liste de tuples (id, nom_complet, description)
        """
        presets = []
        for pid, info in PresetManager.PRESETS.items():
            name_full = f"{info.emoji} {info.name}"
            presets.append((pid, name_full, info.description))
        return presets
    
    @staticmethod
    def get_preset_info(preset_id: int) -> PresetInfo:
        """Retourne les informations d'un preset"""
        return PresetManager.PRESETS.get(preset_id, PresetManager.PRESETS[3])
    
    @staticmethod
    def apply_preset(config: TradingConfig, preset_id: int) -> TradingConfig:
        """
        Applique un preset à une configuration
        
        Args:
            config: Configuration à modifier
            preset_id: ID du preset (1-6)
            
        Returns:
            Configuration modifiée
        """
        
        if preset_id == 1:
            # Personnalisé: ne rien changer
            logger.info("Preset 1 (Personnalisé) - Aucune modification")
            return config
        
        elif preset_id == 2:
            # 🟢 CONSERVATIVE - Protection maximale
            logger.info("Application preset 2 (CONSERVATIVE)")
            
            # Circuit Breaker STRICT
            config.circuit_breaker_enabled = True
            config.risk_daily_loss_enabled = True
            config.risk_daily_trades_enabled = True
            config.risk_consecutive_losses_enabled = True
            config.risk_drawdown_enabled = True
            config.risk_correlation_enabled = True
            config.risk_portfolio_enabled = True
            
            # Limites STRICTES
            config.risk_max_daily_loss = 200.0  # 200$ max/jour
            config.risk_max_daily_trades = 30  # 30 trades/jour
            config.risk_max_consecutive_losses = 3  # 3 pertes max
            config.risk_max_drawdown_percent = 8.0  # 8% drawdown max
            config.risk_max_correlated_positions = 2  # 2 positions/direction
            config.risk_max_portfolio_risk_percent = 15.0  # 15% risque max
            config.risk_cooldown_after_loss_streak_minutes = 60  # 60min cooldown
            
            # Paramètres de trading CONSERVATEURS
            config.max_positions = 3  # 3 positions max
            config.min_seconds_between_trades = 30  # 30s entre trades
            config.stc_threshold_buy = 30.0  # STC < 30 pour BUY
            config.stc_threshold_sell = 70.0  # STC > 70 pour SELL
            config.extreme_stc_threshold = 15.0  # Seuil extrême strict
            
            # Sweep DÉSACTIVÉ en mode conservateur
            config.sweep_enabled = False
            config.sweep_base_volume = 0.01
            config.sweep_max_levels = 2
            
            # MTF ACTIVÉ (filtrage strict)
            config.mtf_filter_enabled = True
            config.mtf_require_alignment = True
            config.force_mtf_bypass = False
            config.mtf_alignment_threshold = 3  # 3/4 TF doivent s'aligner
            
            # TP Infini DÉSACTIVÉ (profits classiques)
            config.infinite_tp_enabled = False
            
            logger.info("✅ Preset CONSERVATIVE appliqué - Protection maximale")
            return config
        
        elif preset_id == 3:
            # 🟡 ÉQUILIBRÉE - Standard (recommandé)
            logger.info("Application preset 3 (ÉQUILIBRÉE)")
            
            # Circuit Breaker STANDARD
            config.circuit_breaker_enabled = True
            config.risk_daily_loss_enabled = True
            config.risk_daily_trades_enabled = True
            config.risk_consecutive_losses_enabled = True
            config.risk_drawdown_enabled = True
            config.risk_correlation_enabled = True
            config.risk_portfolio_enabled = True
            
            # Limites STANDARD
            config.risk_max_daily_loss = 500.0  # 500$ max/jour
            config.risk_max_daily_trades = 50  # 50 trades/jour
            config.risk_max_consecutive_losses = 5  # 5 pertes max
            config.risk_max_drawdown_percent = 10.0  # 10% drawdown max
            config.risk_max_correlated_positions = 3  # 3 positions/direction
            config.risk_max_portfolio_risk_percent = 20.0  # 20% risque max
            config.risk_cooldown_after_loss_streak_minutes = 30  # 30min cooldown
            
            # Paramètres de trading ÉQUILIBRÉS
            config.max_positions = 5  # 5 positions max
            config.min_seconds_between_trades = 10  # 10s entre trades
            config.stc_threshold_buy = 35.0  # STC < 35 pour BUY
            config.stc_threshold_sell = 65.0  # STC > 65 pour SELL
            config.extreme_stc_threshold = 20.0  # Seuil extrême modéré
            
            # Sweep ACTIVÉ modéré
            config.sweep_enabled = True
            config.sweep_base_volume = 0.01
            config.sweep_max_levels = 4
            
            # MTF ACTIVÉ (filtrage modéré)
            config.mtf_filter_enabled = True
            config.mtf_require_alignment = False
            config.force_mtf_bypass = False
            config.mtf_alignment_threshold = 2  # 2/4 TF suffisent
            
            # TP Infini ACTIVÉ (paramètres modérés)
            config.infinite_tp_enabled = True
            config.initial_tp_distance_pips = 500.0  # 5.00$ TP initial
            config.tp_trigger_distance_pips = 150.0  # 1.50$ trigger
            config.tp_extension_pips = 250.0  # 2.50$ extension
            config.trailing_distance_pips = 30.0  # 0.30$ trailing
            config.trailing_step_pips = 10.0  # 0.10$ step
            config.sl_secure_after_trigger_pips = 10.0  # 0.10$ sécurité
            
            logger.info("✅ Preset ÉQUILIBRÉE appliqué - Configuration recommandée")
            return config
        
        elif preset_id == 4:
            # 🔴 AGRESSIVE - Protection minimale
            logger.info("Application preset 4 (AGRESSIVE)")
            
            # Circuit Breaker MINIMAL
            config.circuit_breaker_enabled = True
            config.risk_daily_loss_enabled = True  # Seule protection obligatoire
            config.risk_daily_trades_enabled = False  # Pas de limite trades
            config.risk_consecutive_losses_enabled = False  # Pas de cooldown
            config.risk_drawdown_enabled = True  # Protection drawdown seulement
            config.risk_correlation_enabled = False  # Pas de limite corrélation
            config.risk_portfolio_enabled = False  # Pas de limite portfolio
            
            # Limites PERMISSIVES
            config.risk_max_daily_loss = 1000.0  # 1000$ max/jour
            config.risk_max_drawdown_percent = 15.0  # 15% drawdown max
            
            # Paramètres de trading AGRESSIFS
            config.max_positions = 10  # 10 positions max
            config.min_seconds_between_trades = 3  # 3s entre trades
            config.stc_threshold_buy = 40.0  # STC < 40 pour BUY (plus de signaux)
            config.stc_threshold_sell = 60.0  # STC > 60 pour SELL (plus de signaux)
            config.extreme_stc_threshold = 25.0  # Seuil extrême permissif
            
            # Sweep ACTIVÉ agressif
            config.sweep_enabled = True
            config.sweep_base_volume = 0.02
            config.sweep_max_levels = 6
            
            # MTF DÉSACTIVÉ (plus de signaux)
            config.mtf_filter_enabled = False
            config.mtf_require_alignment = False
            config.force_mtf_bypass = True
            
            # TP Infini ACTIVÉ (paramètres agressifs)
            config.infinite_tp_enabled = True
            config.initial_tp_distance_pips = 800.0  # 8.00$ TP initial
            config.tp_trigger_distance_pips = 200.0  # 2.00$ trigger
            config.tp_extension_pips = 400.0  # 4.00$ extension
            config.trailing_distance_pips = 40.0  # 0.40$ trailing
            config.trailing_step_pips = 15.0  # 0.15$ step
            config.sl_secure_after_trigger_pips = 15.0  # 0.15$ sécurité
            
            logger.info("⚠️ Preset AGRESSIVE appliqué - Protection minimale")
            return config
        
        elif preset_id == 5:
            # ⚫ DÉSACTIVÉ - Aucune protection (BACKTEST UNIQUEMENT)
            logger.warning("Application preset 5 (DÉSACTIVÉ) - ⚠️ DANGEREUX ⚠️")
            
            # Circuit Breaker DÉSACTIVÉ
            config.circuit_breaker_enabled = False
            config.risk_daily_loss_enabled = False
            config.risk_daily_trades_enabled = False
            config.risk_consecutive_losses_enabled = False
            config.risk_drawdown_enabled = False
            config.risk_correlation_enabled = False
            config.risk_portfolio_enabled = False
            
            # Paramètres de trading SANS LIMITES
            config.max_positions = 50  # Illimité (pratiquement)
            config.min_seconds_between_trades = 0  # Pas de délai
            config.stc_threshold_buy = 50.0  # STC < 50 (neutre)
            config.stc_threshold_sell = 50.0  # STC > 50 (neutre)
            
            # Sweep ACTIVÉ sans limites
            config.sweep_enabled = True
            config.sweep_base_volume = 0.01
            config.sweep_max_levels = 10
            
            # MTF DÉSACTIVÉ
            config.mtf_filter_enabled = False
            config.force_mtf_bypass = True
            
            logger.warning("⚠️⚠️⚠️ CIRCUIT BREAKER DÉSACTIVÉ - BACKTEST UNIQUEMENT ⚠️⚠️⚠️")
            return config
        
        elif preset_id == 6:
            # 🔥 ULTRA-RÉACTIF - Trading continu (HFT)
            logger.info("Application preset 6 (ULTRA-RÉACTIF)")
            
            # Circuit Breaker ACTIVÉ mais PERMISSIF
            config.circuit_breaker_enabled = True
            config.risk_daily_loss_enabled = True
            config.risk_daily_trades_enabled = True
            config.risk_consecutive_losses_enabled = False  # Désactivé pour réactivité
            config.risk_drawdown_enabled = False  # Désactivé pour trading continu
            config.risk_correlation_enabled = False  # Désactivé pour plus de positions
            config.risk_portfolio_enabled = False
            
            # Limites TRÈS PERMISSIVES
            config.risk_max_daily_loss = 10000.0  # 10000$ max/jour
            config.risk_max_daily_trades = 5000  # 5000 trades/jour
            
            # Paramètres ULTRA-RÉACTIFS
            config.tick_analysis_interval = 0.0001  # 0.1ms (ultra-rapide)
            config.stc_threshold_buy = 25.0  # STC < 25 (beaucoup de signaux BUY)
            config.stc_threshold_sell = 75.0  # STC > 75 (beaucoup de signaux SELL)
            config.max_positions = 20  # 20 positions max
            config.min_seconds_between_trades = 1  # 1s entre trades
            config.extreme_stc_threshold = 30.0  # Seuil extrême permissif
            
            # Sweep INTENSE
            config.sweep_enabled = True
            config.sweep_base_volume = 0.02  # 0.02 lots de base
            config.sweep_max_levels = 8  # 8 niveaux Elliott Wave
            config.sweep_orders_per_level = 10  # 10 ordres/niveau
            
            # 🚀 MTF DÉSACTIVÉ (force_mtf_bypass=True)
            config.mtf_filter_enabled = False
            config.mtf_require_alignment = False
            config.force_mtf_bypass = True  # BYPASS TOTAL du filtre MTF
            
            # TP Infini AGRESSIF
            config.infinite_tp_enabled = True
            config.initial_tp_distance_pips = 1000.0  # 10.00$ TP initial
            config.tp_trigger_distance_pips = 300.0  # 3.00$ trigger
            config.tp_extension_pips = 500.0  # 5.00$ extension
            config.trailing_distance_pips = 50.0  # 0.50$ trailing
            config.trailing_step_pips = 20.0  # 0.20$ step
            config.sl_secure_after_trigger_pips = 20.0  # 0.20$ sécurité
            
            logger.info("🔥 Preset ULTRA-RÉACTIF appliqué - Mode HFT activé")
            return config
        
        else:
            logger.warning(f"Preset ID {preset_id} inconnu, application preset 3 (ÉQUILIBRÉE)")
            return PresetManager.apply_preset(config, 3)
    
    @staticmethod
    def get_preset_summary(preset_id: int) -> str:
        """
        Retourne un résumé textuel d'un preset
        
        Returns:
            String formaté avec les paramètres principaux
        """
        info = PresetManager.get_preset_info(preset_id)
        
        # Créer config temporaire pour extraire les valeurs
        temp_config = TradingConfig()
        PresetManager.apply_preset(temp_config, preset_id)
        
        summary = f"\n{info.emoji} {info.name.upper()}\n"
        summary += "=" * 60 + "\n"
        summary += f"Description: {info.description}\n"
        summary += f"Niveau de risque: {info.risk_level}\n"
        summary += f"Recommandé pour: {info.recommended_for}\n\n"
        
        if preset_id == 1:
            summary += "Configuration personnalisée - Paramètres actuels conservés\n"
            return summary
        
        summary += "📊 CIRCUIT BREAKER:\n"
        summary += f"  • Activé: {'✅' if temp_config.circuit_breaker_enabled else '❌'}\n"
        
        if temp_config.circuit_breaker_enabled:
            if temp_config.risk_daily_loss_enabled:
                summary += f"  • Perte max/jour: {temp_config.risk_max_daily_loss:.0f}$\n"
            if temp_config.risk_daily_trades_enabled:
                summary += f"  • Trades max/jour: {temp_config.risk_max_daily_trades}\n"
            if temp_config.risk_consecutive_losses_enabled:
                summary += f"  • Pertes consécutives: {temp_config.risk_max_consecutive_losses}\n"
            if temp_config.risk_drawdown_enabled:
                summary += f"  • Drawdown max: {temp_config.risk_max_drawdown_percent}%\n"
            if temp_config.risk_correlation_enabled:
                summary += f"  • Corrélation: {temp_config.risk_max_correlated_positions} positions/direction\n"
        
        summary += "\n⚡ TRADING:\n"
        summary += f"  • Positions max: {temp_config.max_positions}\n"
        summary += f"  • Délai entre trades: {temp_config.min_seconds_between_trades}s\n"
        summary += f"  • STC BUY < {temp_config.stc_threshold_buy}, SELL > {temp_config.stc_threshold_sell}\n"
        
        summary += "\n🌊 SWEEP:\n"
        summary += f"  • Activé: {'✅' if temp_config.sweep_enabled else '❌'}\n"
        if temp_config.sweep_enabled:
            summary += f"  • Volume base: {temp_config.sweep_base_volume} lots\n"
            summary += f"  • Niveaux max: {temp_config.sweep_max_levels}\n"
        
        summary += "\n🎯 MTF (Higher Timeframes):\n"
        summary += f"  • Activé: {'✅' if temp_config.mtf_filter_enabled else '❌ (Mode ULTRA-RÉACTIF)'}\n"
        summary += f"  • Force bypass: {'✅ (Ichimoku+STC uniquement)' if temp_config.force_mtf_bypass else '❌'}\n"
        
        summary += "\n♾️ TP INFINI:\n"
        summary += f"  • Activé: {'✅' if temp_config.infinite_tp_enabled else '❌'}\n"
        if temp_config.infinite_tp_enabled:
            summary += f"  • TP initial: {temp_config.initial_tp_distance_pips * 0.01:.2f}$\n"
            summary += f"  • Extension: {temp_config.tp_extension_pips * 0.01:.2f}$\n"
        
        return summary
    
    @staticmethod
    def get_preset_comparison() -> str:
        """
        Retourne un tableau comparatif de tous les presets
        
        Returns:
            String formaté avec tableau comparatif
        """
        comparison = "\n" + "=" * 100 + "\n"
        comparison += "📊 COMPARAISON DES PRESETS\n"
        comparison += "=" * 100 + "\n\n"
        
        # En-têtes
        comparison += f"{'Paramètre':<30} | {'Conservative':<15} | {'Équilibrée':<15} | {'Agressive':<15} | {'ULTRA':<15}\n"
        comparison += "-" * 100 + "\n"
        
        # Lignes de comparaison
        configs = {
            'Conservative': PresetManager.apply_preset(TradingConfig(), 2),
            'Équilibrée': PresetManager.apply_preset(TradingConfig(), 3),
            'Agressive': PresetManager.apply_preset(TradingConfig(), 4),
            'ULTRA': PresetManager.apply_preset(TradingConfig(), 6),
        }
        
        # Perte max/jour
        comparison += f"{'Perte max/jour':<30} | "
        comparison += f"{configs['Conservative'].risk_max_daily_loss:>14.0f}$ | "
        comparison += f"{configs['Équilibrée'].risk_max_daily_loss:>14.0f}$ | "
        comparison += f"{configs['Agressive'].risk_max_daily_loss:>14.0f}$ | "
        comparison += f"{configs['ULTRA'].risk_max_daily_loss:>14.0f}$\n"
        
        # Trades max/jour
        comparison += f"{'Trades max/jour':<30} | "
        comparison += f"{configs['Conservative'].risk_max_daily_trades:>15} | "
        comparison += f"{configs['Équilibrée'].risk_max_daily_trades:>15} | "
        comparison += f"{'Illimité':>15} | "
        comparison += f"{configs['ULTRA'].risk_max_daily_trades:>15}\n"
        
        # Positions max
        comparison += f"{'Positions max':<30} | "
        for name in ['Conservative', 'Équilibrée', 'Agressive', 'ULTRA']:
            comparison += f"{configs[name].max_positions:>15} | "
        comparison += "\n"
        
        # Délai entre trades
        comparison += f"{'Délai entre trades (s)':<30} | "
        for name in ['Conservative', 'Équilibrée', 'Agressive', 'ULTRA']:
            comparison += f"{configs[name].min_seconds_between_trades:>15} | "
        comparison += "\n"
        
        # MTF activé
        comparison += f"{'Filtre MTF (HTF)':<30} | "
        for name in ['Conservative', 'Équilibrée', 'Agressive', 'ULTRA']:
            mtf_status = "✅ OUI" if configs[name].mtf_filter_enabled else "❌ NON"
            comparison += f"{mtf_status:>15} | "
        comparison += "\n"
        
        # Sweep niveaux
        comparison += f"{'Sweep niveaux max':<30} | "
        for name in ['Conservative', 'Équilibrée', 'Agressive', 'ULTRA']:
            sweep_val = configs[name].sweep_max_levels if configs[name].sweep_enabled else 0
            comparison += f"{sweep_val:>15} | "
        comparison += "\n"
        
        comparison += "=" * 100 + "\n"
        
        return comparison


# Fonction helper pour utilisation simplifiée
def apply_preset_to_config(config: TradingConfig, preset_name_or_id) -> TradingConfig:
    """
    Applique un preset à une config (helper function)
    
    Args:
        config: Configuration à modifier
        preset_name_or_id: Nom du preset (str) ou ID (int)
        
    Returns:
        Configuration modifiée
    """
    if isinstance(preset_name_or_id, str):
        # Convertir nom en ID
        name_to_id = {
            "personnalisé": 1,
            "conservative": 2,
            "équilibrée": 3,
            "agressive": 4,
            "désactivé": 5,
            "ultra": 6,
            "ultra-réactif": 6,
        }
        preset_id = name_to_id.get(preset_name_or_id.lower(), 3)
    else:
        preset_id = preset_name_or_id
    
    return PresetManager.apply_preset(config, preset_id)
