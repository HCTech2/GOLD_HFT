#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Indicateur ZigZag pour détection de swings significatifs
Identifie les pivots high/low et la tendance actuelle
"""

import numpy as np
from typing import List, Tuple, Optional, Dict
from enum import Enum
from dataclasses import dataclass
from datetime import datetime


class ZigZagTrend(Enum):
    """Type de tendance détectée"""
    BULLISH = 1
    BEARISH = -1
    NEUTRAL = 0


class SwingType(Enum):
    """Type de swing point"""
    HIGH = 1
    LOW = -1


@dataclass
class SwingPoint:
    """Point de swing (high ou low)"""
    index: int
    price: float
    timestamp: datetime
    swing_type: SwingType
    strength: float  # Force du swing (0-1)


@dataclass
class ZigZagResult:
    """Résultat de l'analyse ZigZag"""
    current_trend: ZigZagTrend
    swing_points: List[SwingPoint]
    last_swing_high: Optional[SwingPoint]
    last_swing_low: Optional[SwingPoint]
    bars_since_last_swing: int
    swing_magnitude: float  # Amplitude du dernier swing en pips


class ZigZagIndicator:
    """
    Indicateur ZigZag pour détecter les swings significatifs
    
    Utilise un threshold en % pour filtrer les petits mouvements
    et identifier les vrais pivots high/low
    """
    
    def __init__(self, threshold_percent: float = 0.5, min_bars: int = 3):
        """
        Args:
            threshold_percent: Mouvement minimum en % pour valider un swing
            min_bars: Nombre minimum de barres entre deux swings
        """
        self.threshold_percent = threshold_percent
        self.min_bars = min_bars
        self.swing_points: List[SwingPoint] = []
    
    def calculate(
        self, 
        high: np.ndarray, 
        low: np.ndarray, 
        close: np.ndarray,
        timestamps: Optional[List[datetime]] = None
    ) -> ZigZagResult:
        """
        Calcule les points ZigZag sur une série de prix
        
        Args:
            high: Array des prix high
            low: Array des prix low
            close: Array des prix close
            timestamps: Timestamps optionnels
            
        Returns:
            ZigZagResult avec tendance et swing points
        """
        if len(high) < 10:
            return self._empty_result()
        
        # Générer timestamps si non fournis
        if timestamps is None:
            timestamps = [datetime.now() for _ in range(len(high))]
        
        # Détecter les swings
        swing_points = self._detect_swings(high, low, close, timestamps)
        
        if len(swing_points) < 2:
            return self._empty_result()
        
        # Déterminer la tendance actuelle
        current_trend = self._determine_trend(swing_points)
        
        # Trouver les derniers swings
        last_high = None
        last_low = None
        for swing in reversed(swing_points):
            if swing.swing_type == SwingType.HIGH and last_high is None:
                last_high = swing
            if swing.swing_type == SwingType.LOW and last_low is None:
                last_low = swing
            if last_high and last_low:
                break
        
        # Calculer bars depuis dernier swing
        bars_since = len(high) - swing_points[-1].index - 1 if swing_points else 0
        
        # Calculer magnitude du dernier swing
        magnitude = 0.0
        if len(swing_points) >= 2:
            magnitude = abs(swing_points[-1].price - swing_points[-2].price)
        
        return ZigZagResult(
            current_trend=current_trend,
            swing_points=swing_points,
            last_swing_high=last_high,
            last_swing_low=last_low,
            bars_since_last_swing=bars_since,
            swing_magnitude=magnitude
        )
    
    def _detect_swings(
        self, 
        high: np.ndarray, 
        low: np.ndarray, 
        close: np.ndarray,
        timestamps: List[datetime]
    ) -> List[SwingPoint]:
        """Détecte les swing points"""
        swings = []
        
        # Paramètres de détection
        lookback = max(self.min_bars, 3)
        threshold = self.threshold_percent / 100.0
        
        # Détecter les highs
        for i in range(lookback, len(high) - lookback):
            is_high = True
            for j in range(i - lookback, i + lookback + 1):
                if j != i and high[j] >= high[i]:
                    is_high = False
                    break
            
            if is_high:
                # Vérifier threshold
                if len(swings) == 0 or abs(high[i] - swings[-1].price) / swings[-1].price >= threshold:
                    # Calculer strength basé sur la différence avec les voisins
                    strength = self._calculate_strength(high, i, lookback)
                    swings.append(SwingPoint(
                        index=i,
                        price=high[i],
                        timestamp=timestamps[i],
                        swing_type=SwingType.HIGH,
                        strength=strength
                    ))
        
        # Détecter les lows
        for i in range(lookback, len(low) - lookback):
            is_low = True
            for j in range(i - lookback, i + lookback + 1):
                if j != i and low[j] <= low[i]:
                    is_low = False
                    break
            
            if is_low:
                # Vérifier threshold
                if len(swings) == 0 or abs(low[i] - swings[-1].price) / swings[-1].price >= threshold:
                    strength = self._calculate_strength(low, i, lookback, is_low=True)
                    swings.append(SwingPoint(
                        index=i,
                        price=low[i],
                        timestamp=timestamps[i],
                        swing_type=SwingType.LOW,
                        strength=strength
                    ))
        
        # Trier par index
        swings.sort(key=lambda s: s.index)
        
        # Alterner high/low
        filtered_swings = self._alternate_swings(swings)
        
        return filtered_swings
    
    def _calculate_strength(
        self, 
        prices: np.ndarray, 
        index: int, 
        lookback: int,
        is_low: bool = False
    ) -> float:
        """Calcule la force d'un swing (0-1)"""
        start = max(0, index - lookback)
        end = min(len(prices), index + lookback + 1)
        
        if is_low:
            diffs = [prices[index] - prices[j] for j in range(start, end) if j != index]
        else:
            diffs = [prices[j] - prices[index] for j in range(start, end) if j != index]
        
        if not diffs:
            return 0.5
        
        # Normaliser entre 0 et 1
        max_diff = max(abs(d) for d in diffs)
        if max_diff == 0:
            return 0.5
        
        avg_diff = np.mean([abs(d) for d in diffs])
        strength = min(1.0, avg_diff / max_diff)
        
        return strength
    
    def _alternate_swings(self, swings: List[SwingPoint]) -> List[SwingPoint]:
        """Assure l'alternance high/low dans les swings"""
        if len(swings) < 2:
            return swings
        
        filtered = [swings[0]]
        
        for swing in swings[1:]:
            # Garder seulement si type différent du précédent
            if swing.swing_type != filtered[-1].swing_type:
                filtered.append(swing)
            else:
                # Remplacer si plus extrême
                if swing.swing_type == SwingType.HIGH and swing.price > filtered[-1].price:
                    filtered[-1] = swing
                elif swing.swing_type == SwingType.LOW and swing.price < filtered[-1].price:
                    filtered[-1] = swing
        
        return filtered
    
    def _determine_trend(self, swings: List[SwingPoint]) -> ZigZagTrend:
        """Détermine la tendance basée sur les swings"""
        if len(swings) < 4:
            return ZigZagTrend.NEUTRAL
        
        # Comparer les 2 derniers highs et 2 derniers lows
        highs = [s for s in swings if s.swing_type == SwingType.HIGH]
        lows = [s for s in swings if s.swing_type == SwingType.LOW]
        
        if len(highs) < 2 or len(lows) < 2:
            return ZigZagTrend.NEUTRAL
        
        # Higher highs et higher lows = bullish
        higher_highs = highs[-1].price > highs[-2].price
        higher_lows = lows[-1].price > lows[-2].price
        
        # Lower highs et lower lows = bearish
        lower_highs = highs[-1].price < highs[-2].price
        lower_lows = lows[-1].price < lows[-2].price
        
        if higher_highs and higher_lows:
            return ZigZagTrend.BULLISH
        elif lower_highs and lower_lows:
            return ZigZagTrend.BEARISH
        else:
            return ZigZagTrend.NEUTRAL
    
    def _empty_result(self) -> ZigZagResult:
        """Retourne un résultat vide"""
        return ZigZagResult(
            current_trend=ZigZagTrend.NEUTRAL,
            swing_points=[],
            last_swing_high=None,
            last_swing_low=None,
            bars_since_last_swing=0,
            swing_magnitude=0.0
        )
    
    def get_support_resistance(
        self, 
        result: ZigZagResult, 
        tolerance: float = 0.001
    ) -> Dict[str, List[float]]:
        """
        Identifie les niveaux de support/résistance
        
        Args:
            result: Résultat ZigZag
            tolerance: Tolérance pour regrouper les niveaux (en %)
            
        Returns:
            Dict avec 'support' et 'resistance' (listes de prix)
        """
        if not result.swing_points:
            return {'support': [], 'resistance': []}
        
        # Extraire highs et lows
        highs = [s.price for s in result.swing_points if s.swing_type == SwingType.HIGH]
        lows = [s.price for s in result.swing_points if s.swing_type == SwingType.LOW]
        
        # Regrouper les niveaux proches
        resistance = self._cluster_levels(highs, tolerance)
        support = self._cluster_levels(lows, tolerance)
        
        return {
            'support': sorted(support),
            'resistance': sorted(resistance, reverse=True)
        }
    
    def _cluster_levels(self, prices: List[float], tolerance: float) -> List[float]:
        """Regroupe les prix proches en clusters"""
        if not prices:
            return []
        
        clusters = []
        sorted_prices = sorted(prices)
        
        current_cluster = [sorted_prices[0]]
        
        for price in sorted_prices[1:]:
            # Si prix proche du cluster actuel
            if abs(price - np.mean(current_cluster)) / np.mean(current_cluster) <= tolerance:
                current_cluster.append(price)
            else:
                # Sauvegarder cluster et en démarrer un nouveau
                clusters.append(np.mean(current_cluster))
                current_cluster = [price]
        
        # Ajouter dernier cluster
        if current_cluster:
            clusters.append(np.mean(current_cluster))
        
        return clusters
