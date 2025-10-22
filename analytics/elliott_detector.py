#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Détecteur de vagues Elliott Wave
Identifie les patterns d'impulsion (1-5) et de correction (A-C)
"""

import numpy as np
from typing import List, Optional, Dict, Tuple
from enum import Enum
from dataclasses import dataclass
from datetime import datetime

import sys
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent.parent))

from indicators.zigzag import ZigZagIndicator, SwingPoint, SwingType, ZigZagResult


class WaveType(Enum):
    """Type de vague Elliott"""
    IMPULSE_1 = 1
    IMPULSE_2 = 2
    IMPULSE_3 = 3
    IMPULSE_4 = 4
    IMPULSE_5 = 5
    CORRECTION_A = -1
    CORRECTION_B = -2
    CORRECTION_C = -3
    UNKNOWN = 0


class WaveDirection(Enum):
    """Direction de la vague"""
    UP = 1
    DOWN = -1


@dataclass
class FibonacciLevel:
    """Niveau de retracement Fibonacci"""
    level: float  # 0.236, 0.382, 0.5, 0.618, etc.
    price: float
    label: str


@dataclass
class ElliottWave:
    """Une vague Elliott identifiée"""
    wave_type: WaveType
    direction: WaveDirection
    start_swing: SwingPoint
    end_swing: SwingPoint
    price_range: float
    duration_bars: int
    fibonacci_levels: List[FibonacciLevel]
    confidence: float  # 0-1


@dataclass
class ElliottPattern:
    """Pattern Elliott complet (5 vagues + correction)"""
    impulse_waves: List[ElliottWave]  # Vagues 1-5
    correction_waves: List[ElliottWave]  # Vagues A-C
    pattern_start: datetime
    pattern_end: datetime
    is_complete: bool
    current_wave: Optional[WaveType]
    next_expected_wave: Optional[WaveType]


class ElliottWaveDetector:
    """
    Détecteur de vagues Elliott Wave
    
    Applique les règles Elliott:
    - Vague 2 ne retrace jamais au-delà de la vague 1
    - Vague 3 n'est jamais la plus courte
    - Vague 4 ne chevauche pas la vague 1
    """
    
    # Ratios Fibonacci standards
    FIBONACCI_RATIOS = {
        'retracement': [0.236, 0.382, 0.5, 0.618, 0.786],
        'extension': [1.0, 1.272, 1.618, 2.0, 2.618]
    }
    
    def __init__(self, zigzag_threshold: float = 0.5):
        """
        Args:
            zigzag_threshold: Threshold pour l'indicateur ZigZag (%)
        """
        self.zigzag = ZigZagIndicator(threshold_percent=zigzag_threshold)
        self.detected_patterns: List[ElliottPattern] = []
    
    def detect_waves(
        self,
        high: np.ndarray,
        low: np.ndarray,
        close: np.ndarray,
        timestamps: Optional[List[datetime]] = None
    ) -> Optional[ElliottPattern]:
        """
        Détecte les vagues Elliott dans les données de prix
        
        Args:
            high: Prix high
            low: Prix low
            close: Prix close
            timestamps: Timestamps optionnels
            
        Returns:
            ElliottPattern si détecté, None sinon
        """
        # Calculer ZigZag
        zigzag_result = self.zigzag.calculate(high, low, close, timestamps)
        
        if len(zigzag_result.swing_points) < 6:
            return None  # Besoin d'au moins 6 swings pour 5 vagues
        
        # Détecter vagues d'impulsion (1-5)
        impulse_waves = self._detect_impulse_waves(zigzag_result.swing_points)
        
        if not impulse_waves or len(impulse_waves) < 5:
            return None
        
        # Détecter vagues de correction (A-C) si présentes
        correction_waves = self._detect_correction_waves(
            zigzag_result.swing_points,
            impulse_waves
        )
        
        # Déterminer vague actuelle
        current_wave = self._determine_current_wave(
            impulse_waves,
            correction_waves,
            zigzag_result.swing_points
        )
        
        # Prédire prochaine vague
        next_wave = self._predict_next_wave(current_wave, len(correction_waves))
        
        pattern = ElliottPattern(
            impulse_waves=impulse_waves,
            correction_waves=correction_waves,
            pattern_start=impulse_waves[0].start_swing.timestamp,
            pattern_end=impulse_waves[-1].end_swing.timestamp,
            is_complete=len(impulse_waves) == 5 and len(correction_waves) == 3,
            current_wave=current_wave,
            next_expected_wave=next_wave
        )
        
        return pattern
    
    def _detect_impulse_waves(self, swings: List[SwingPoint]) -> List[ElliottWave]:
        """Détecte les 5 vagues d'impulsion"""
        waves = []
        
        # Chercher pattern de 5 vagues
        for start_idx in range(len(swings) - 5):
            candidate_swings = swings[start_idx:start_idx + 6]
            
            # Vérifier si c'est un pattern valide
            if self._validate_impulse_pattern(candidate_swings):
                # Créer les 5 vagues
                for i in range(5):
                    wave = self._create_wave(
                        WaveType(i + 1),
                        candidate_swings[i],
                        candidate_swings[i + 1]
                    )
                    waves.append(wave)
                
                break  # Prendre le premier pattern valide
        
        return waves
    
    def _validate_impulse_pattern(self, swings: List[SwingPoint]) -> bool:
        """
        Valide un pattern de 5 vagues selon les règles Elliott
        
        Règles:
        1. Vague 2 ne dépasse pas le début de vague 1
        2. Vague 3 n'est pas la plus courte
        3. Vague 4 ne chevauche pas vague 1
        """
        if len(swings) != 6:
            return False
        
        # Calculer amplitudes
        wave1 = abs(swings[1].price - swings[0].price)
        wave2 = abs(swings[2].price - swings[1].price)
        wave3 = abs(swings[3].price - swings[2].price)
        wave4 = abs(swings[4].price - swings[3].price)
        wave5 = abs(swings[5].price - swings[4].price)
        
        # Déterminer direction (bullish ou bearish)
        is_bullish = swings[1].price > swings[0].price
        
        # Règle 1: Vague 2 ne dépasse pas début vague 1
        if is_bullish:
            if swings[2].price < swings[0].price:
                return False
        else:
            if swings[2].price > swings[0].price:
                return False
        
        # Règle 2: Vague 3 n'est pas la plus courte
        if wave3 < wave1 and wave3 < wave5:
            return False
        
        # Règle 3: Vague 4 ne chevauche pas vague 1
        if is_bullish:
            if swings[4].price < swings[1].price:
                return False
        else:
            if swings[4].price > swings[1].price:
                return False
        
        return True
    
    def _create_wave(
        self,
        wave_type: WaveType,
        start: SwingPoint,
        end: SwingPoint
    ) -> ElliottWave:
        """Crée un objet ElliottWave"""
        direction = WaveDirection.UP if end.price > start.price else WaveDirection.DOWN
        price_range = abs(end.price - start.price)
        duration = end.index - start.index
        
        # Calculer niveaux Fibonacci
        fib_levels = self._calculate_fibonacci_levels(start.price, end.price, direction)
        
        # Calculer confiance basée sur la validité des règles Elliott
        confidence = self._calculate_wave_confidence(wave_type, price_range, duration)
        
        return ElliottWave(
            wave_type=wave_type,
            direction=direction,
            start_swing=start,
            end_swing=end,
            price_range=price_range,
            duration_bars=duration,
            fibonacci_levels=fib_levels,
            confidence=confidence
        )
    
    def _calculate_fibonacci_levels(
        self,
        start_price: float,
        end_price: float,
        direction: WaveDirection
    ) -> List[FibonacciLevel]:
        """Calcule les niveaux de retracement Fibonacci"""
        levels = []
        price_range = end_price - start_price
        
        for ratio in self.FIBONACCI_RATIOS['retracement']:
            if direction == WaveDirection.UP:
                level_price = end_price - (price_range * ratio)
            else:
                level_price = end_price + (abs(price_range) * ratio)
            
            levels.append(FibonacciLevel(
                level=ratio,
                price=level_price,
                label=f"{ratio * 100:.1f}%"
            ))
        
        return levels
    
    def _calculate_wave_confidence(
        self,
        wave_type: WaveType,
        price_range: float,
        duration: int
    ) -> float:
        """Calcule la confiance de la vague (0-1)"""
        confidence = 0.5  # Base
        
        # Vague 3 devrait être la plus forte
        if wave_type == WaveType.IMPULSE_3:
            confidence += 0.2
        
        # Durée raisonnable
        if 5 <= duration <= 50:
            confidence += 0.1
        
        # Amplitude significative
        if price_range > 0:
            confidence += 0.2
        
        return min(1.0, confidence)
    
    def _detect_correction_waves(
        self,
        all_swings: List[SwingPoint],
        impulse_waves: List[ElliottWave]
    ) -> List[ElliottWave]:
        """Détecte les vagues de correction A-B-C"""
        if len(impulse_waves) < 5:
            return []
        
        correction_waves = []
        
        # Chercher swings après la vague 5
        last_impulse_swing_idx = impulse_waves[-1].end_swing.index
        
        # Trouver l'index dans all_swings
        start_idx = 0
        for i, swing in enumerate(all_swings):
            if swing.index == last_impulse_swing_idx:
                start_idx = i + 1
                break
        
        # Besoin d'au moins 3 swings pour A-B-C
        if start_idx + 3 <= len(all_swings):
            correction_swings = all_swings[start_idx:start_idx + 4]
            
            # Créer vagues A, B, C
            for i, wave_type in enumerate([WaveType.CORRECTION_A, WaveType.CORRECTION_B, WaveType.CORRECTION_C]):
                if i + 1 < len(correction_swings):
                    wave = self._create_wave(
                        wave_type,
                        correction_swings[i],
                        correction_swings[i + 1]
                    )
                    correction_waves.append(wave)
        
        return correction_waves
    
    def _determine_current_wave(
        self,
        impulse_waves: List[ElliottWave],
        correction_waves: List[ElliottWave],
        all_swings: List[SwingPoint]
    ) -> Optional[WaveType]:
        """Détermine la vague actuelle"""
        if not impulse_waves:
            return WaveType.UNKNOWN
        
        # Si correction complète
        if len(correction_waves) == 3:
            return WaveType.CORRECTION_C
        
        # Si correction en cours
        if correction_waves:
            return correction_waves[-1].wave_type
        
        # Si impulsion complète
        if len(impulse_waves) == 5:
            return WaveType.IMPULSE_5
        
        # Sinon, dernière vague d'impulsion
        return impulse_waves[-1].wave_type
    
    def _predict_next_wave(
        self,
        current_wave: Optional[WaveType],
        correction_count: int
    ) -> Optional[WaveType]:
        """Prédit la prochaine vague attendue"""
        if current_wave is None or current_wave == WaveType.UNKNOWN:
            return WaveType.IMPULSE_1
        
        # Mapping des transitions
        wave_sequence = {
            WaveType.IMPULSE_1: WaveType.IMPULSE_2,
            WaveType.IMPULSE_2: WaveType.IMPULSE_3,
            WaveType.IMPULSE_3: WaveType.IMPULSE_4,
            WaveType.IMPULSE_4: WaveType.IMPULSE_5,
            WaveType.IMPULSE_5: WaveType.CORRECTION_A,
            WaveType.CORRECTION_A: WaveType.CORRECTION_B,
            WaveType.CORRECTION_B: WaveType.CORRECTION_C,
            WaveType.CORRECTION_C: WaveType.IMPULSE_1,  # Nouveau cycle
        }
        
        return wave_sequence.get(current_wave, WaveType.UNKNOWN)
    
    def get_trading_signal(self, pattern: ElliottPattern) -> Dict:
        """
        Génère un signal de trading basé sur le pattern Elliott
        
        Returns:
            Dict avec 'action', 'confidence', 'target', 'stop'
        """
        if not pattern or not pattern.current_wave:
            return {
                'action': 'WAIT',
                'confidence': 0.0,
                'target': None,
                'stop': None,
                'reason': 'No pattern detected'
            }
        
        current = pattern.current_wave
        
        # Vague 3: Signal FORT (meilleure vague pour trader)
        if current == WaveType.IMPULSE_2 and pattern.next_expected_wave == WaveType.IMPULSE_3:
            wave2 = pattern.impulse_waves[1]
            direction = 'BUY' if wave2.direction == WaveDirection.DOWN else 'SELL'
            
            # Target: Extension 1.618 de vague 1
            target = self._calculate_wave3_target(pattern.impulse_waves)
            
            # Stop: En dessous/au-dessus de vague 2
            stop = wave2.end_swing.price
            
            return {
                'action': direction,
                'confidence': 0.85,
                'target': target,
                'stop': stop,
                'reason': 'Wave 3 setup (strongest impulse)'
            }
        
        # Vague 5: Signal MODÉRÉ (dernière vague, prudence)
        elif current == WaveType.IMPULSE_4 and pattern.next_expected_wave == WaveType.IMPULSE_5:
            wave4 = pattern.impulse_waves[3]
            direction = 'BUY' if wave4.direction == WaveDirection.DOWN else 'SELL'
            
            target = self._calculate_wave5_target(pattern.impulse_waves)
            stop = wave4.end_swing.price
            
            return {
                'action': direction,
                'confidence': 0.60,
                'target': target,
                'stop': stop,
                'reason': 'Wave 5 setup (final impulse, take profit soon)'
            }
        
        # Correction: Signal CONTRE-TENDANCE (risqué)
        elif current in [WaveType.IMPULSE_5, WaveType.CORRECTION_A]:
            wave5 = pattern.impulse_waves[4]
            direction = 'SELL' if wave5.direction == WaveDirection.UP else 'BUY'
            
            return {
                'action': direction,
                'confidence': 0.40,
                'target': None,
                'stop': wave5.end_swing.price,
                'reason': 'Correction expected (counter-trend, risky)'
            }
        
        return {
            'action': 'WAIT',
            'confidence': 0.0,
            'target': None,
            'stop': None,
            'reason': f'Current wave: {current.name}'
        }
    
    def _calculate_wave3_target(self, impulse_waves: List[ElliottWave]) -> Optional[float]:
        """Calcule target pour vague 3 (1.618 extension de vague 1)"""
        if len(impulse_waves) < 2:
            return None
        
        wave1 = impulse_waves[0]
        wave2 = impulse_waves[1]
        
        wave1_range = wave1.price_range
        
        if wave1.direction == WaveDirection.UP:
            target = wave2.end_swing.price + (wave1_range * 1.618)
        else:
            target = wave2.end_swing.price - (wave1_range * 1.618)
        
        return target
    
    def _calculate_wave5_target(self, impulse_waves: List[ElliottWave]) -> Optional[float]:
        """Calcule target pour vague 5 (égale à vague 1 depuis fin vague 4)"""
        if len(impulse_waves) < 4:
            return None
        
        wave1 = impulse_waves[0]
        wave4 = impulse_waves[3]
        
        wave1_range = wave1.price_range
        
        if wave1.direction == WaveDirection.UP:
            target = wave4.end_swing.price + wave1_range
        else:
            target = wave4.end_swing.price - wave1_range
        
        return target
