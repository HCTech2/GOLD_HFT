#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration de trading pour le bot HFT XAU/USD
"""

from dataclasses import dataclass, field
from typing import List, Tuple
from enum import Enum


class OrderType(Enum):
    """Types d'ordres"""
    BUY = "BUY"
    SELL = "SELL"


class PositionState(Enum):
    """États d'une position"""
    OPEN = "OPEN"
    CLOSED = "CLOSED"
    PENDING = "PENDING"


class PositionType(Enum):
    """Type de position dans le système unifié HFT_DIRECT + SWEEP"""
    DIRECT = "DIRECT"    # Position HFT_DIRECT (ordre unique)
    SWEEP = "SWEEP"      # Position SWEEP (partie d'un groupe Martingale/Elliott)


@dataclass
class TradingConfig:
    """Configuration de la stratégie de trading"""
    # Symbole et portefeuille
    symbol: str = "XAUUSD-m"  # XAU/USD Micro sur TitanFX
    initial_portfolio: float = 50  # $50 initial
    
    # Tailles de positions
    target_x2_thresholds: List[float] = field(default_factory=lambda: [10, 20, 40, 80, 130, 200, 300])
    position_sizes: List[float] = field(default_factory=lambda: [0.05, 0.15, 0.25, 0.35, 0.45, 0.55, 0.65])
    
    # Paramètres EMA
    ema_fast_period: int = 9
    ema_slow_period: int = 21
    
    # Paramètres Ichimoku
    ichimoku_tenkan: int = 9
    ichimoku_kijun: int = 26
    ichimoku_senkou_b: int = 52
    ichimoku_tenkan_sen: int = 9
    ichimoku_kijun_sen: int = 26
    ichimoku_senkou_span_b: int = 52
    
    # Paramètres Elliott Wave
    wave_lookback: int = 50
    
    # Paramètres Schaff Trend Cycle
    stc_period: int = 2
    stc_fast_length: int = 23
    stc_slow_length: int = 50
    stc_threshold_buy: float = 40.0   # 🚀 ULTRA-RÉACTIF: 40 (anciennement 25) = plus de signaux BUY
    stc_threshold_sell: float = 60.0  # 🚀 ULTRA-RÉACTIF: 60 (anciennement 75) = plus de signaux SELL
    
    # Paramètres de trading
    max_pips_sweep: int = 15000
    kill_zone_london: Tuple[int, int] = (0, 6)
    kill_zone_ny: Tuple[int, int] = (9, 16)
    kill_zone_enabled: bool = False  # Kill zone désactivée par défaut
    max_simultaneous_orders: int = 8  # 🚀 ULTRA-RÉACTIF: 8 ordres (anciennement 3)
    max_positions: int = 10  # 🚀 ULTRA-RÉACTIF: 10 positions (anciennement 4)
    min_seconds_between_trades: int = 5  # 🚀 ULTRA-RÉACTIF: 5 secondes (anciennement 30)
    ignore_stc: bool = False  # Ignorer le STC pour les signaux
    
    # Paramètres HFT (High Frequency Trading)
    tick_buffer_size: int = 100000  # Nombre de ticks à conserver en mémoire
    tick_analysis_interval: float = 0.0001  # 🚀 ULTRA-RÉACTIF: 0.1ms = 10000 checks/sec (anciennement 0.001)
    
    # Seuils de réactivité
    min_tick_volume: int = 1
    spread_threshold: float = 10.05  # Spread max en dollars (0.01$ à 20$)
    
    # ============================================================================
    # TIMEFRAME DE LA STRATÉGIE (Configurable)
    # ============================================================================
    strategy_timeframe: str = "M1"  # TICK, M1, M5 - Timeframe pour STC/Ichimoku
    # TICK = Calculs sur chaque tick (ultra-réactif, plus de bruit)
    # M1 = Calculs sur bougies M1 (équilibré, recommandé)
    # M5 = Calculs sur bougies M5 (plus lent, moins de faux signaux)
    
    # Timeframe de confirmation secondaire (optionnel)
    confirmation_timeframe: str = "M5"  # Timeframe secondaire pour double confirmation
    use_confirmation_timeframe: bool = False  # Activer la confirmation secondaire
    
    # Paramètres SL/TP
    base_sl_distance: float = 10.0  # 10$ de SL de base (100 points)
    base_tp_distance: float = 20.0  # 20$ de TP de base (200 points) - Ratio 1:2
    spread_compensation_multiplier: float = 1.5  # Compensation du spread dans le TP
    
    # Paramètres de profit réactif (fermeture automatique en profit)
    reactive_profit_enabled: bool = True  # Activer la clôture réactive en profit
    profit_threshold_per_position: float = 5.0  # Seuil de profit par position (en $) pour clôture automatique
    profit_threshold_cumulative: float = 15.0  # Seuil de profit cumulé (en $) pour clôture de toutes les positions

    # Trading sans croisement Ichimoku (pour signaux STC extrêmes)
    allow_no_crossover_on_extreme_stc: bool = True  # Autoriser trade sans croisement si STC très extrême
    extreme_stc_threshold: float = 15.0  # 🚀 ULTRA-RÉACTIF: 15.0 (anciennement 5.0) = plus tolérant

    # ============================================================================
    # SYSTÈME DE PRIORITÉ TICK + CONFIANCE HTF (Activable/Désactivable)
    # ============================================================================
    
    # Activation du système de confiance HTF
    htf_confidence_enabled: bool = True  # Activer système de confiance HTF
    tick_priority_mode: bool = True  # M1/Ticks = décision, HTF = confiance uniquement
    
    # Calcul du score de confiance HTF (0-100%)
    # Score = (votes_aligned / total_votes) * 100
    # Exemples: 4/4 votes = 100%, 3/4 = 75%, 2/4 = 50%, 1/4 = 25%, 0/4 = 0%
    
    # Ajustement dynamique TP/SL selon confiance HTF
    # Format: (confiance_min, confiance_max) → (tp_multiplier, sl_multiplier)
    # Confiance HAUTE (75-100%) → TP large (x1.5), SL serré (x0.7)
    confidence_high_min: float = 75.0  # Confiance haute >= 75%
    tp_multiplier_high_confidence: float = 1.5  # TP x1.5 si confiance haute
    sl_multiplier_high_confidence: float = 0.7  # SL x0.7 (plus serré)
    
    # Confiance MOYENNE (40-74%) → TP standard (x1.0), SL standard (x1.0)
    confidence_medium_min: float = 40.0  # Confiance moyenne >= 40%
    tp_multiplier_medium_confidence: float = 1.0  # TP normal
    sl_multiplier_medium_confidence: float = 1.0  # SL normal
    
    # Confiance FAIBLE (0-39%) → TP prudent (x0.6), SL large (x1.3)
    tp_multiplier_low_confidence: float = 0.6  # TP x0.6 (réduit)
    sl_multiplier_low_confidence: float = 1.3  # SL x1.3 (plus large)
    
    # Seuil minimum de confiance pour trader (optionnel)
    min_confidence_to_trade: float = 0.0  # 0 = accepte tous, 25 = minimum 25% confiance
    
    # Machine Learning
    ml_enabled: bool = True
    ml_state_file: str = "data/ml_state.npz"
    ml_train_test_split: float = 0.8  # 80% training, 20% test
    trade_database_path: str = "ml/data/trades.db"

    # Trailing dynamique (valeurs par défaut en cas d'absence de recommandation ML)
    trailing_secure_base: float = 5.0
    trailing_extension_base: float = 12.0
    trailing_distance_base: float = 4.0
    
    # ============================================================================
    # SYSTÈME TP INFINI & TRAILING STOP (Configurable via GUI)
    # ============================================================================
    
    # 🔥 TP Initial - Distance TRÈS loin devant le prix (Gold bouge de 20-50$/jour)
    initial_tp_distance_pips: float = 1000.0  # Distance TP initial depuis l'entrée (en pips) - TP TRÈS loin devant (10.00$)
    
    # 🔥 TP Infini - Déclenchement du trailing
    tp_trigger_distance_pips: float = 300.0  # Distance du TP (en pips) pour déclencher le trailing (3.00$)
    tp_extension_pips: float = 500.0  # De combien repousser le TP (en pips) après déclenchement (5.00$)
    
    # Trailing Stop - Suivi du prix
    trailing_distance_pips: float = 200.0  # 🔥 Distance du trailing stop derrière le prix (2.00$) - ÉLARGI pour volatilité Gold
    trailing_step_pips: float = 50.0  # 🔥 Pas de déplacement du SL (0.50$) - minimum de mouvement
    
    # Sécurité SL - Sécurisation progressive
    sl_secure_after_trigger_pips: float = 50.0  # 🔥 Sécuriser +50 pips (0.50$) après 1er déclenchement - PROFIT MINIMUM GARANTI
    sl_breakeven_enabled: bool = True  # Mettre SL au breakeven après déclenchement
    
    # Activation
    infinite_tp_enabled: bool = True  # Activer le système TP infini
    
    # Compatibilité anciennes versions (alias)
    @property
    def tp_proximity_pips(self):
        return self.tp_trigger_distance_pips
    
    @tp_proximity_pips.setter
    def tp_proximity_pips(self, value):
        self.tp_trigger_distance_pips = value
    
    # ============================================================================
    # CIRCUIT BREAKER & RISK MANAGEMENT (Activable/Désactivable)
    # ============================================================================
    
    # Activation globale du Circuit Breaker
    circuit_breaker_enabled: bool = False  # Activer/Désactiver TOUT le système de protection
    
    # Protection 1: Perte journalière
    risk_daily_loss_enabled: bool = True  # Activer limite de perte journalière
    risk_max_daily_loss: float = 500.0  # Perte journalière maximale en $
    
    # Protection 2: Overtrading
    risk_daily_trades_enabled: bool = True  # Activer limite de trades/jour
    risk_max_daily_trades: int = 5000  # 🚀 ULTRA-RÉACTIF: 5000 trades/jour (anciennement 1000)
    
    # Protection 3: Pertes consécutives
    risk_consecutive_losses_enabled: bool = True  # Activer détection pertes consécutives
    risk_max_consecutive_losses: int = 9  # Pertes consécutives max avant cooldown
    risk_cooldown_after_loss_streak_minutes: int = 30  # Durée pause après série de pertes
    
    # Protection 4: Drawdown
    risk_drawdown_enabled: bool = False  # 🚀 DÉSACTIVÉ - Pas de limite drawdown
    risk_max_drawdown_percent: float = 50.0  # Drawdown max en % du capital (ignoré si désactivé)
    
    # Protection 5: Corrélation des positions
    risk_correlation_enabled: bool = True  # Activer limite positions corrélées
    risk_max_correlated_positions: int = 7  # Positions max dans la même direction
    
    # Protection 6: Risque portefeuille global
    risk_portfolio_enabled: bool = True  # Activer limite risque global
    risk_max_portfolio_risk_percent: float = 65.0  # Risque max du portefeuille en %
    
    # Volume dynamique
    volume_dynamic_enabled: bool = True  # Adapter le volume selon volatilité et ML
    volume_min_multiplier: float = 0.5  # Multiplicateur minimum en haute volatilité
    volume_max_multiplier: float = 2.0  # Multiplicateur maximum si ML confiant
    
    # Filtrage multi-timeframe (Higher TimeFrames)
    mtf_filter_enabled: bool = False  # 🚀 DÉSACTIVÉ PAR DÉFAUT - Activer via GUI pour filtrage HTF
    mtf_require_alignment: bool = False  # 🚀 ULTRA-RÉACTIF: Désactivé pour plus de liberté (anciennement True)
    mtf_timeframes: List[str] = field(default_factory=lambda: ['M15', 'M30', 'H1', 'H4'])  # Timeframes HTF à analyser
    mtf_alignment_threshold: int = 1  # Nombre minimum de TF alignés (1/4 suffit si les autres sont None)
    force_mtf_bypass: bool = False  # 🔥 CRITIQUE: Bypass total du MTF même si mtf_filter_enabled=True (Mode 6 ULTRA)
    
    # Cache des indicateurs
    indicators_cache_enabled: bool = True  # Activer le cache pour performances
    
    # Seuil ATR pour volume dynamique
    max_atr_threshold: float = 15.0  # ATR max pour calcul volume (en $)
    
    # ============================================================================
    # SWEEP PROGRESSIF - MARTINGALE ADDITIVE
    # ============================================================================
    
    # Activation du système Sweep
    sweep_enabled: bool = True  # Activer/désactiver le sweep progressif
    
    # Volume de base pour le sweep (première position)
    sweep_base_volume: float = 0.01  # Mise de départ (0.01 à 100.00 lots)
    
    # Nombre maximum de niveaux Elliott Wave
    sweep_max_levels: int = 5  # Nombre de niveaux (2-8)
    
    # Nombre d'ordres à placer par niveau
    sweep_orders_per_level: int = 10  # Ordres par niveau (1-10)
    
    # Logique de progression : ADDITIVE (pas multiplicative)
    # Ordre 1 : base_volume
    # Ordre 2 : base_volume + base_volume = 2x base
    # Ordre 3 : base_volume + base_volume + base_volume = 3x base
    # Ordre 4 : 4x base, Ordre 5 : 5x base, etc.

