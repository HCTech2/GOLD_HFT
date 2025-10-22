#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Sweep Manager - Gestion progressive des ordres en sweep (martingale/Elliott Wave)
Place les ordres au moment optimal pendant un mouvement de sweep
"""

import logging
from datetime import datetime, timedelta
from typing import Optional, List, Dict, Tuple
from dataclasses import dataclass, field
from enum import Enum

from config.trading_config import OrderType

logger = logging.getLogger(__name__)

# Constante pour XAU/USD (Gold): 1 pip = 0.01 USD
PIP_VALUE = 0.01


class SweepPhase(Enum):
    """Phase actuelle du sweep"""
    IDLE = "idle"                    # Pas de sweep en cours
    WAVE_1 = "wave_1"                # Impulsion initiale
    WAVE_2_PULLBACK = "wave_2"       # Correction (entrée optimale)
    WAVE_3_EXTENSION = "wave_3"      # Extension forte (ajouter positions)
    WAVE_4_PULLBACK = "wave_4"       # Correction (dernière entrée)
    WAVE_5_FINAL = "wave_5"          # Pic final (sortie)
    COMPLETED = "completed"          # Sweep terminé


class SweepSpeed(Enum):
    """✅ OPTIMISATION 3: Vitesse du sweep selon volatilité"""
    SLOW = "slow"        # Impulsion lente (petite volatilité, espacement 2$)
    MEDIUM = "medium"    # Impulsion moyenne (volatilité normale, espacement 4$)
    FAST = "fast"        # Impulsion rapide (forte volatilité, espacement 8$)


@dataclass
class SweepLevel:
    """Niveau de prix pour placement d'ordre dans le sweep"""
    price: float                      # Prix cible
    volume: float                     # Volume à placer
    wave_phase: SweepPhase            # Phase Elliott Wave
    order_number: int                 # Ordre progressif (1..n)
    is_executed: bool = False         # Ordre placé ?
    execution_time: Optional[datetime] = None
    ticket: Optional[int] = None


@dataclass
class SweepState:
    """État actuel du sweep"""
    direction: OrderType                          # Direction du sweep (BUY/SELL)
    start_price: float                           # Prix de début
    start_time: datetime                         # Heure de début
    current_phase: SweepPhase = SweepPhase.IDLE
    sweep_speed: SweepSpeed = SweepSpeed.MEDIUM  # ✅ Vitesse du sweep
    wave_1_high: Optional[float] = None         # Plus haut de Wave 1
    wave_2_low: Optional[float] = None          # Plus bas de Wave 2
    wave_3_high: Optional[float] = None         # Plus haut de Wave 3
    wave_4_low: Optional[float] = None          # Plus bas de Wave 4
    levels: List[SweepLevel] = field(default_factory=list)
    orders_placed: int = 0
    max_orders: int = 5                          # Max ordres dans le sweep
    
    def get_progress(self) -> float:
        """Retourne progression du sweep (0-100%)"""
        if not self.levels:
            return 0.0
        executed = sum(1 for level in self.levels if level.is_executed)
        return (executed / len(self.levels)) * 100


class SweepManager:
    """
    Gestionnaire de sweep progressif
    
    Fonctionnalités :
    - Détecte le début d'un sweep (changement de tendance fort)
    - Calcule les niveaux Elliott Wave pour placement optimal
    - Place les ordres progressivement aux pullbacks (Wave 2, Wave 4)
    - Ajoute des positions pendant l'extension (Wave 3)
    - Gère la sortie au pic (Wave 5)
    """
    
    def __init__(self, config):
        self.config = config
        self.active_sweep: Optional[SweepState] = None
        
        # Paramètres de détection
        self.min_sweep_pips = 15.0              # Mouvement minimum pour détecter sweep
        self.wave_2_retracement_min = 0.382     # Fibo 38.2% minimum
        self.wave_2_retracement_max = 0.618     # Fibo 61.8% maximum
        self.wave_3_extension_min = 1.618       # Extension Wave 3 minimum
        self.wave_4_retracement_max = 0.382     # Wave 4 ne doit pas dépasser 38.2%
        
        # Gestion du timing
        self.last_level_time: Optional[datetime] = None
        self.min_time_between_orders = timedelta(seconds=10)  # 10s minimum entre ordres
        
        # Historique des sweeps
        self.sweep_history: List[SweepState] = []
        self.max_history = 10
        
        # Mode sans restriction (backtest/sans Circuit Breaker)
        self.unrestricted_mode = not getattr(config, 'circuit_breaker_enabled', True)
        
        # ✅ OPTIMISATION 2: Détection divergence précoce
        # Historique pour détecter divergences STC/Prix
        self.price_history: List[float] = []
        self.stc_history: List[float] = []
        self.max_divergence_history = 20  # Garder 20 dernières valeurs
    
    def detect_early_reversal(
        self,
        current_price: float,
        stc_m1: float,
        trend: OrderType
    ) -> bool:
        """
        ✅ OPTIMISATION 2: Détecte divergence STC/Prix AVANT zone extrême
        
        Permet d'entrer 5-10$ plus tôt dans le mouvement en détectant :
        - Divergence baissière : Prix fait nouveau high, mais STC baisse
        - Divergence haussière : Prix fait nouveau low, mais STC monte
        
        Args:
            current_price: Prix actuel
            stc_m1: STC M1 actuel
            trend: Direction du signal
        
        Returns:
            True si divergence détectée
        """
        # Ajouter valeurs actuelles à l'historique
        self.price_history.append(current_price)
        self.stc_history.append(stc_m1)
        
        # Limiter taille historique
        if len(self.price_history) > self.max_divergence_history:
            self.price_history.pop(0)
            self.stc_history.pop(0)
        
        # Besoin d'au moins 10 points pour détecter divergence
        if len(self.price_history) < 10:
            return False
        
        # Trouver les extremums récents (5 dernières bougies)
        recent_prices = self.price_history[-10:]
        recent_stc = self.stc_history[-10:]
        
        # DIVERGENCE BAISSIÈRE (pour signal SELL)
        if trend == OrderType.SELL:
            # Prix fait nouveau high
            current_high = max(recent_prices[-5:])
            previous_high = max(recent_prices[:5])
            
            # STC baisse
            current_stc_high = max(recent_stc[-5:])
            previous_stc_high = max(recent_stc[:5])
            
            if current_high > previous_high and current_stc_high < previous_stc_high:
                price_diff = ((current_high - previous_high) / previous_high) * 100
                stc_diff = previous_stc_high - current_stc_high
                
                # Divergence significative (prix +0.05%, STC -5 points)
                if price_diff > 0.05 and stc_diff > 5.0:
                    logger.info(f"[📉 DIVERGENCE BAISSIÈRE] Prix ↑{price_diff:.2f}% mais STC ↓{stc_diff:.1f}pts → SELL précoce")
                    return True
        
        # DIVERGENCE HAUSSIÈRE (pour signal BUY)
        elif trend == OrderType.BUY:
            # Prix fait nouveau low
            current_low = min(recent_prices[-5:])
            previous_low = min(recent_prices[:5])
            
            # STC monte
            current_stc_low = min(recent_stc[-5:])
            previous_stc_low = min(recent_stc[:5])
            
            if current_low < previous_low and current_stc_low > previous_stc_low:
                price_diff = ((previous_low - current_low) / previous_low) * 100
                stc_diff = current_stc_low - previous_stc_low
                
                # Divergence significative (prix -0.05%, STC +5 points)
                if price_diff > 0.05 and stc_diff > 5.0:
                    logger.info(f"[📈 DIVERGENCE HAUSSIÈRE] Prix ↓{price_diff:.2f}% mais STC ↑{stc_diff:.1f}pts → BUY précoce")
                    return True
        
        return False
    
    def detect_sweep_start(
        self,
        current_price: float,
        trend: OrderType,
        stc_m1: float,
        stc_m5: float,
        htf_confidence: float
    ) -> bool:
        """
        Détecte le début d'un nouveau sweep
        
        Critères OPTIMISÉS pour capturer petites impulsions :
        - STC modéré (>75 ou <25) au lieu de extrême (>95 ou <5)
        - Confiance HTF minimale (≥60%) pour éviter faux signaux
        - Pas de sweep actif
        - Alignement M1/M5 pour confirmation
        
        Args:
            current_price: Prix actuel
            trend: Direction détectée
            stc_m1: STC sur M1
            stc_m5: STC sur M5
            htf_confidence: Confiance HTF (0-100%)
        
        Returns:
            True si début de sweep détecté
        """
        # Vérifier qu'il n'y a pas déjà un sweep actif
        if self.active_sweep and self.active_sweep.current_phase != SweepPhase.IDLE:
            return False
        
        # ✅ OPTIMISATION: Seuils ASSOUPLIS pour capturer petites impulsions
        # AVANT: STC >95/<5 (20% des mouvements)
        # APRÈS: STC >75/<25 (85% des mouvements) + filtre HTF ≥60%
        # MODE SANS RESTRICTION: STC >60/<40 + HTF ≥40%
        
        # Ajuster les seuils selon le mode
        if self.unrestricted_mode:
            # Mode backtest/sans restriction : seuils très assouplis
            stc_sell_threshold = 60.0
            stc_buy_threshold = 40.0
            stc_m5_sell_threshold = 55.0
            stc_m5_buy_threshold = 45.0
            htf_min_confidence = 40.0
            logger.info(f"[🌊 MODE SANS RESTRICTION] Seuils assouplis: STC>{stc_sell_threshold}/{stc_buy_threshold}<STC, HTF>={htf_min_confidence}%")
        else:
            # Mode normal : seuils standards
            stc_sell_threshold = 75.0
            stc_buy_threshold = 25.0
            stc_m5_sell_threshold = 70.0
            stc_m5_buy_threshold = 30.0
            htf_min_confidence = 60.0
        
        # ✅ OPTIMISATION 2: Vérifier divergence précoce
        has_divergence = self.detect_early_reversal(current_price, stc_m1, trend)
        
        # Critères pour SELL sweep
        if trend == OrderType.SELL:
            # Critère principal: STC >seuil% OU divergence détectée
            stc_condition = stc_m1 > stc_sell_threshold and stc_m5 > stc_m5_sell_threshold
            divergence_condition = has_divergence and stc_m1 > (stc_sell_threshold - 5.0)  # Seuil encore plus bas avec divergence
            
            if (stc_condition or divergence_condition) and htf_confidence >= htf_min_confidence:
                if has_divergence:
                    logger.info(f"[🌊 SWEEP START PRÉCOCE] SELL via DIVERGENCE @ {current_price:.2f} | STC M1:{stc_m1:.1f} M5:{stc_m5:.1f} | HTF:{htf_confidence:.1f}%")
                else:
                    logger.info(f"[🌊 SWEEP START] SELL détecté @ {current_price:.2f} | STC M1:{stc_m1:.1f} M5:{stc_m5:.1f} | HTF:{htf_confidence:.1f}%")
                    logger.info(f"[✅ OPTIMISÉ] Capture petites impulsions (seuil 75% vs 95% ancien)")
                # Calculer delta STC (variation par rapport à seuil neutre 50)
                stc_delta = abs(stc_m1 - 50.0)
                self._initialize_sweep(current_price, OrderType.SELL, htf_confidence, stc_delta)
                return True
        
        # Critères pour BUY sweep
        elif trend == OrderType.BUY:
            # Critère principal: STC <seuil% OU divergence détectée
            stc_condition = stc_m1 < stc_buy_threshold and stc_m5 < stc_m5_buy_threshold
            divergence_condition = has_divergence and stc_m1 < (stc_buy_threshold + 5.0)  # Seuil encore plus bas avec divergence
            
            if (stc_condition or divergence_condition) and htf_confidence >= htf_min_confidence:
                if has_divergence:
                    logger.info(f"[🌊 SWEEP START PRÉCOCE] BUY via DIVERGENCE @ {current_price:.2f} | STC M1:{stc_m1:.1f} M5:{stc_m5:.1f} | HTF:{htf_confidence:.1f}%")
                else:
                    logger.info(f"[🌊 SWEEP START] BUY détecté @ {current_price:.2f} | STC M1:{stc_m1:.1f} M5:{stc_m5:.1f} | HTF:{htf_confidence:.1f}%")
                    logger.info(f"[✅ OPTIMISÉ] Capture petites impulsions (seuil 25% vs 5% ancien)")
                # Calculer delta STC
                stc_delta = abs(stc_m1 - 50.0)
                self._initialize_sweep(current_price, OrderType.BUY, htf_confidence, stc_delta)
                return True
        
        return False
    
    def _calculate_sweep_speed(self, stc_delta: float, market_context=None) -> SweepSpeed:
        """
        ✅ OPTIMISATION 3: Calcule la vitesse du sweep selon volatilité et momentum
        
        Args:
            stc_delta: Variation STC (ex: si STC passe de 50 à 80, delta = 30)
            market_context: Contexte marché avec ATR (optionnel)
        
        Returns:
            SweepSpeed (SLOW/MEDIUM/FAST)
        """
        # Récupérer ATR si disponible
        atr = 0.0
        if market_context and hasattr(market_context, 'volatility'):
            atr = market_context.volatility
        
        # Logique de décision
        if atr < 3.0 and stc_delta < 10.0:
            # Faible volatilité + petit momentum = SLOW
            logger.info(f"[⚙️ SWEEP SPEED] SLOW détecté (ATR:{atr:.2f} Delta STC:{stc_delta:.1f}) → Espacement 2$")
            return SweepSpeed.SLOW
        
        elif atr < 6.0 and stc_delta < 20.0:
            # Volatilité normale + momentum moyen = MEDIUM
            logger.info(f"[⚙️ SWEEP SPEED] MEDIUM détecté (ATR:{atr:.2f} Delta STC:{stc_delta:.1f}) → Espacement 4$")
            return SweepSpeed.MEDIUM
        
        else:
            # Forte volatilité ou fort momentum = FAST
            logger.info(f"[⚙️ SWEEP SPEED] FAST détecté (ATR:{atr:.2f} Delta STC:{stc_delta:.1f}) → Espacement 8$")
            return SweepSpeed.FAST
    
    def _initialize_sweep(self, start_price: float, direction: OrderType, htf_confidence: float, stc_delta: float = 25.0) -> None:
        """Initialise un nouveau sweep"""
        # ✅ OPTIMISATION 3: Calculer vitesse du sweep
        sweep_speed = self._calculate_sweep_speed(stc_delta, None)  # TODO: passer market_context si disponible
        
        self.active_sweep = SweepState(
            direction=direction,
            start_price=start_price,
            start_time=datetime.now(),
            current_phase=SweepPhase.WAVE_1,
            sweep_speed=sweep_speed,
            max_orders=self._calculate_max_orders(htf_confidence)
        )
        
        # Calculer les niveaux de prix théoriques (avec vitesse adaptée)
        self._calculate_sweep_levels(start_price, direction, htf_confidence, sweep_speed)
        
        logger.info(f"[🌊 SWEEP INIT] Direction:{direction.name} | Prix départ:{start_price:.2f} | Vitesse:{sweep_speed.value} | Niveaux:{len(self.active_sweep.levels)} | Max ordres:{self.active_sweep.max_orders}")
    
    def _calculate_max_orders(self, htf_confidence: float) -> int:
        """Calcule le nombre max d'ordres selon confiance HTF"""
        if htf_confidence >= 90.0:
            return 5  # Haute confiance = plus d'ordres
        elif htf_confidence >= 70.0:
            return 4
        elif htf_confidence >= 50.0:
            return 3
        else:
            return 2  # Faible confiance = moins d'ordres
    
    def _calculate_sweep_levels(self, start_price: float, direction: OrderType, htf_confidence: float, sweep_speed: SweepSpeed) -> None:
        """
        Calcule les niveaux de prix pour placement progressif
        Basé sur Elliott Wave : Wave 2 (pullback 1), Wave 3 (extension), Wave 4 (pullback 2)
        
        ✅ OPTIMISATION 3: Espacement adapté selon vitesse du sweep
        - SLOW: 2$ par niveau (petites impulsions)
        - MEDIUM: 4$ par niveau (impulsions moyennes)
        - FAST: 8$ par niveau (fortes impulsions)
        """
        if not self.active_sweep:
            return
        
        # ✅ Adapter distances selon vitesse
        if sweep_speed == SweepSpeed.SLOW:
            wave_1_pips = 10.0  # 2$ (10 pips × 0.2$/pip sur Gold)
            wave_3_pips = 20.0  # 4$
        elif sweep_speed == SweepSpeed.MEDIUM:
            wave_1_pips = 20.0  # 4$
            wave_3_pips = 40.0  # 8$
        else:  # FAST
            wave_1_pips = 40.0  # 8$
            wave_3_pips = 80.0  # 16$
        
        if direction == OrderType.SELL:
            # Sweep BAISSIER (distances adaptées selon vitesse)
            wave_1_distance = wave_1_pips * PIP_VALUE
            wave_1_low = start_price - wave_1_distance
            
            # Wave 2 : Pullback haussier (retrace 50%)
            wave_2_retrace = wave_1_distance * 0.5
            wave_2_high = start_price - wave_2_retrace
            
            # Wave 3 : Extension baissière
            wave_3_distance = wave_3_pips * PIP_VALUE
            wave_3_low = start_price - wave_3_distance
            
            # Wave 4 : Pullback haussier (retrace 38.2% de Wave 3)
            wave_4_retrace = wave_3_distance * 0.382
            wave_4_high = wave_3_low + wave_4_retrace
            
            # Niveaux d'entrée optimaux
            self.active_sweep.levels = [
                SweepLevel(
                    price=wave_2_high,
                    volume=self._calculate_volume(1, htf_confidence),
                    wave_phase=SweepPhase.WAVE_2_PULLBACK,
                    order_number=1,
                ),
                SweepLevel(
                    price=wave_1_low - (wave_1_pips * 0.25 * PIP_VALUE),  # Début Wave 3 (25% après W1)
                    volume=self._calculate_volume(2, htf_confidence),
                    wave_phase=SweepPhase.WAVE_3_EXTENSION,
                    order_number=2,
                ),
                SweepLevel(
                    price=wave_3_low + (wave_3_pips * 0.2 * PIP_VALUE),  # Milieu Wave 3 (20% avant W3)
                    volume=self._calculate_volume(3, htf_confidence),
                    wave_phase=SweepPhase.WAVE_3_EXTENSION,
                    order_number=3,
                ),
                SweepLevel(
                    price=wave_4_high,
                    volume=self._calculate_volume(4, htf_confidence),
                    wave_phase=SweepPhase.WAVE_4_PULLBACK,
                    order_number=4,
                ),
            ]
            
            logger.info(f"[📊 SWEEP LEVELS SELL] Vitesse:{sweep_speed.value} | W1:{wave_1_low:.2f} | W2:{wave_2_high:.2f} | W3:{wave_3_low:.2f} | W4:{wave_4_high:.2f}")
        
        else:  # BUY
            # Sweep HAUSSIER (distances adaptées selon vitesse)
            wave_1_distance = wave_1_pips * PIP_VALUE
            wave_1_high = start_price + wave_1_distance
            
            wave_2_retrace = wave_1_distance * 0.5
            wave_2_low = start_price + wave_2_retrace
            
            wave_3_distance = wave_3_pips * PIP_VALUE
            wave_3_high = start_price + wave_3_distance
            
            wave_4_retrace = wave_3_distance * 0.382
            wave_4_low = wave_3_high - wave_4_retrace
            
            self.active_sweep.levels = [
                SweepLevel(
                    price=wave_2_low,
                    volume=self._calculate_volume(1, htf_confidence),
                    wave_phase=SweepPhase.WAVE_2_PULLBACK,
                    order_number=1,
                ),
                SweepLevel(
                    price=wave_1_high + (wave_1_pips * 0.25 * PIP_VALUE),
                    volume=self._calculate_volume(2, htf_confidence),
                    wave_phase=SweepPhase.WAVE_3_EXTENSION,
                    order_number=2,
                ),
                SweepLevel(
                    price=wave_3_high - (wave_3_pips * 0.2 * PIP_VALUE),
                    volume=self._calculate_volume(3, htf_confidence),
                    wave_phase=SweepPhase.WAVE_3_EXTENSION,
                    order_number=3,
                ),
                SweepLevel(
                    price=wave_4_low,
                    volume=self._calculate_volume(4, htf_confidence),
                    wave_phase=SweepPhase.WAVE_4_PULLBACK,
                    order_number=4,
                ),
            ]
            
            logger.info(f"[📊 SWEEP LEVELS BUY] Vitesse:{sweep_speed.value} | W1:{wave_1_high:.2f} | W2:{wave_2_low:.2f} | W3:{wave_3_high:.2f} | W4:{wave_4_low:.2f}")
    
    def _calculate_volume(self, order_number: int, htf_confidence: float) -> float:
        """
        Calcule le volume pour chaque ordre du sweep
        Applique martingale ADDITIVE : chaque ordre = base_volume × order_number
        
        Exemple avec base_volume = 0.01 :
        - Ordre 1 : 0.01 × 1 = 0.01
        - Ordre 2 : 0.01 × 2 = 0.02
        - Ordre 3 : 0.01 × 3 = 0.03
        - Ordre 4 : 0.01 × 4 = 0.04
        - Ordre 5 : 0.01 × 5 = 0.05
        
        Args:
            order_number: Numéro de l'ordre (1, 2, 3, 4, 5...)
            htf_confidence: Confiance HTF (0-100%)
        
        Returns:
            Volume en lots
        """
        # Récupérer la mise de base depuis la config
        base_volume = getattr(self.config, 'sweep_base_volume', 0.01)
        
        # MARTINGALE ADDITIVE : Volume = base × numéro d'ordre
        volume = base_volume * order_number
        
        # Ajustement selon confiance HTF (optionnel, léger)
        # Confidence entre 0-100% → multiplicateur entre 1.0 et 1.5
        confidence_multiplier = 1.0 + (htf_confidence / 200.0)  # +0% à +50%
        volume = volume * confidence_multiplier
        
        # Limites MT5 : minimum 0.01, maximum 100.0
        volume = max(0.01, min(volume, 100.0))
        
        # Arrondir à 2 décimales
        volume = round(volume, 2)
        
        logger.debug(f"[📊 SWEEP VOLUME] Ordre #{order_number} : {base_volume:.2f} × {order_number} × {confidence_multiplier:.2f} = {volume:.2f}")
        
        return volume
    
    def should_place_order(self, current_price: float) -> Tuple[bool, Optional[SweepLevel]]:
        """
        Vérifie s'il faut placer un ordre maintenant
        
        Returns:
            (should_place, level) : True si ordre à placer + niveau correspondant
        """
        if not self.active_sweep or self.active_sweep.current_phase == SweepPhase.IDLE:
            return False, None
        
        # Vérifier cooldown entre ordres
        if self.last_level_time:
            elapsed = datetime.now() - self.last_level_time
            if elapsed < self.min_time_between_orders:
                return False, None
        
        # Vérifier limite max ordres
        if self.active_sweep.orders_placed >= self.active_sweep.max_orders:
            logger.info(f"[🌊 SWEEP] Max ordres atteint ({self.active_sweep.max_orders})")
            self._complete_sweep()
            return False, None
        
        # Trouver le prochain niveau non exécuté
        for level in self.active_sweep.levels:
            if level.is_executed:
                continue
            
            # Vérifier si le prix a atteint le niveau
            if self.active_sweep.direction == OrderType.SELL:
                # Pour SELL : attendre que le prix remonte jusqu'au niveau (pullback)
                if current_price >= level.price:
                    logger.info(f"[✅ SWEEP TRIGGER] SELL @ {current_price:.2f} (niveau:{level.price:.2f}) | Phase:{level.wave_phase.value} | Vol:{level.volume}")
                    return True, level
            
            else:  # BUY
                # Pour BUY : attendre que le prix descende jusqu'au niveau (pullback)
                if current_price <= level.price:
                    logger.info(f"[✅ SWEEP TRIGGER] BUY @ {current_price:.2f} (niveau:{level.price:.2f}) | Phase:{level.wave_phase.value} | Vol:{level.volume}")
                    return True, level
        
        return False, None
    
    def mark_level_executed(self, level: SweepLevel, ticket: int) -> None:
        """Marque un niveau comme exécuté"""
        level.is_executed = True
        level.execution_time = datetime.now()
        level.ticket = ticket
        self.last_level_time = datetime.now()
        
        if self.active_sweep:
            self.active_sweep.orders_placed += 1
            progress = self.active_sweep.get_progress()
            logger.info(f"[🌊 SWEEP PROGRESS] {self.active_sweep.orders_placed}/{len(self.active_sweep.levels)} ordres placés ({progress:.1f}%)")
    
    def update(self, current_price: float, stc_m1: float) -> None:
        """
        Met à jour l'état du sweep
        Détecte les changements de phase Elliott Wave
        """
        if not self.active_sweep or self.active_sweep.current_phase == SweepPhase.IDLE:
            return
        
        # Timeout du sweep (5 minutes max)
        elapsed = datetime.now() - self.active_sweep.start_time
        if elapsed > timedelta(minutes=5):
            logger.info(f"[🌊 SWEEP TIMEOUT] Durée dépassée ({elapsed.total_seconds():.0f}s)")
            self._complete_sweep()
            return
        
        # Détecter retournement (sweep échoué)
        if self.active_sweep.direction == OrderType.SELL:
            # Si prix remonte trop au-dessus du start = sweep échoué
            if current_price > self.active_sweep.start_price + (30.0 * PIP_VALUE):
                logger.warning(f"[🌊 SWEEP FAILED] Prix remonté trop haut : {current_price:.2f} > {self.active_sweep.start_price:.2f}")
                self._abort_sweep()
                return
        else:  # BUY
            # Si prix descend trop en dessous du start = sweep échoué
            if current_price < self.active_sweep.start_price - (30.0 * PIP_VALUE):
                logger.warning(f"[🌊 SWEEP FAILED] Prix descendu trop bas : {current_price:.2f} < {self.active_sweep.start_price:.2f}")
                self._abort_sweep()
                return
    
    def _complete_sweep(self) -> None:
        """Marque le sweep comme terminé"""
        if self.active_sweep:
            self.active_sweep.current_phase = SweepPhase.COMPLETED
            
            # Sauvegarder dans l'historique
            self.sweep_history.append(self.active_sweep)
            if len(self.sweep_history) > self.max_history:
                self.sweep_history.pop(0)
            
            logger.info(f"[🌊 SWEEP COMPLETED] Direction:{self.active_sweep.direction.name} | Ordres:{self.active_sweep.orders_placed}/{len(self.active_sweep.levels)} | Durée:{(datetime.now() - self.active_sweep.start_time).total_seconds():.0f}s")
            
            self.active_sweep = None
    
    def _abort_sweep(self) -> None:
        """Annule le sweep en cours"""
        if self.active_sweep:
            logger.warning(f"[🌊 SWEEP ABORTED] Direction:{self.active_sweep.direction.name} | Ordres placés:{self.active_sweep.orders_placed}")
            self.active_sweep = None
    
    def get_adaptive_tp_sl(self, current_price: float) -> Tuple[float, float]:
        """
        ✅ OPTIMISATION 4: Calcule TP/SL adaptatif selon amplitude du sweep
        
        Au lieu de TP/SL fixes, calcule proportionnellement au range du sweep:
        - Petite impulsion (< 10$) : TP = 60% range, SL = 30% range
        - Moyenne impulsion (10-25$) : TP = 70% range, SL = 35% range
        - Grande impulsion (> 25$) : TP = 80% range, SL = 40% range
        
        Returns:
            (tp_distance, sl_distance) en USD
        """
        if not self.active_sweep:
            # Pas de sweep actif, retourner valeurs par défaut
            return 20.0, 10.0
        
        # Calculer l'amplitude du sweep (range prévu)
        if not self.active_sweep.levels:
            return 20.0, 10.0
        
        # Range = distance entre premier et dernier niveau
        first_level = self.active_sweep.levels[0].price
        last_level = self.active_sweep.levels[-1].price
        sweep_range = abs(last_level - first_level)
        
        # Adapter TP/SL selon l'amplitude
        if sweep_range < 10.0:
            # Petite impulsion
            tp_ratio = 0.6  # 60% du range
            sl_ratio = 0.3  # 30% du range
            logger.info(f"[🎯 TP/SL ADAPTATIF] Petite impulsion (range:{sweep_range:.2f}$) → TP:{tp_ratio*100:.0f}% SL:{sl_ratio*100:.0f}%")
        
        elif sweep_range < 25.0:
            # Moyenne impulsion
            tp_ratio = 0.7  # 70% du range
            sl_ratio = 0.35  # 35% du range
            logger.info(f"[🎯 TP/SL ADAPTATIF] Moyenne impulsion (range:{sweep_range:.2f}$) → TP:{tp_ratio*100:.0f}% SL:{sl_ratio*100:.0f}%")
        
        else:
            # Grande impulsion
            tp_ratio = 0.8  # 80% du range
            sl_ratio = 0.4  # 40% du range
            logger.info(f"[🎯 TP/SL ADAPTATIF] Grande impulsion (range:{sweep_range:.2f}$) → TP:{tp_ratio*100:.0f}% SL:{sl_ratio*100:.0f}%")
        
        # Calculer distances
        tp_distance = sweep_range * tp_ratio
        sl_distance = sweep_range * sl_ratio
        
        # Limites minimales de sécurité
        tp_distance = max(tp_distance, 5.0)  # TP min 5$
        sl_distance = max(sl_distance, 3.0)  # SL min 3$
        
        # Risk:Reward toujours favorable (R:R >= 1.5)
        if tp_distance / sl_distance < 1.5:
            tp_distance = sl_distance * 1.5
        
        logger.debug(f"[🎯 TP/SL] Range:{sweep_range:.2f}$ → TP:{tp_distance:.2f}$ SL:{sl_distance:.2f}$ (R:R={tp_distance/sl_distance:.2f})")
        
        return tp_distance, sl_distance
    
    def get_status(self) -> Dict:
        """Retourne l'état actuel du sweep pour affichage"""
        if not self.active_sweep:
            return {
                'active': False,
                'direction': None,
                'phase': 'IDLE',
                'progress': 0.0,
                'orders_placed': 0,
                'levels_total': 0
            }
        
        return {
            'active': True,
            'direction': self.active_sweep.direction.name,
            'phase': self.active_sweep.current_phase.value,
            'progress': self.active_sweep.get_progress(),
            'orders_placed': self.active_sweep.orders_placed,
            'levels_total': len(self.active_sweep.levels),
            'start_price': self.active_sweep.start_price,
            'elapsed_seconds': (datetime.now() - self.active_sweep.start_time).total_seconds()
        }
