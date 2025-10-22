#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Indicateurs techniques pour HFT
Support Rust (hft_rust_core) pour performances maximales
"""

import numpy as np
from collections import deque
from datetime import datetime
from typing import List, Tuple, Optional
import logging

from config.trading_config import TradingConfig, OrderType
from models.data_models import Tick, OHLC

# Tentative d'import du module Rust pour accélération
try:
    import hft_rust_core
    USE_RUST = True
    logger = logging.getLogger(__name__)
    logger.info("✓ Module Rust chargé - Performances optimales activées")
except ImportError:
    USE_RUST = False
    logger = logging.getLogger(__name__)
    logger.warning("⚠ Module Rust indisponible - Fallback Python (compiler avec: python build_rust.py)")


class HFTIndicators:
    """Indicateurs techniques optimisés pour le trading haute fréquence"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        # Historiques séparés pour chaque timeframe
        self.price_history_tick = deque(maxlen=config.ichimoku_senkou_span_b * 3)
        self.price_history_m1 = deque(maxlen=config.ichimoku_senkou_span_b * 3)
        self.price_history_m5 = deque(maxlen=config.ichimoku_senkou_span_b * 3)
        self.last_update = None
    
    def update_from_ticks(self, ticks: List[Tick]) -> None:
        """Met à jour l'historique des prix TICK à partir des ticks"""
        if not ticks:
            return
        
        for tick in ticks:
            self.price_history_tick.append(tick.mid_price)
        
        self.last_update = datetime.now()
    
    def update_from_m1_candles(self, candles: List[OHLC]) -> None:
        """Met à jour l'historique des prix M1 à partir des bougies"""
        if not candles:
            return
        
        self.price_history_m1.clear()
        for candle in candles:
            self.price_history_m1.append(candle.close)
        
        self.last_update = datetime.now()
    
    def update_from_m5_candles(self, candles: List[OHLC]) -> None:
        """Met à jour l'historique des prix M5 à partir des bougies"""
        if not candles:
            return
        
        self.price_history_m5.clear()
        for candle in candles:
            self.price_history_m5.append(candle.close)
        
        self.last_update = datetime.now()
    
    def calculate_ichimoku(self, timeframe: str = "TICK") -> Tuple[Optional[float], Optional[float], Optional[float], Optional[float]]:
        """Calcule les lignes Ichimoku pour un timeframe donné"""
        # Sélectionner l'historique approprié
        if timeframe == "M1":
            price_history = self.price_history_m1
        elif timeframe == "M5":
            price_history = self.price_history_m5
        else:
            price_history = self.price_history_tick
        
        if len(price_history) < self.config.ichimoku_senkou_span_b:
            return None, None, None, None
        
        prices = list(price_history)
        
        # Tenkan-sen
        tenkan_high = max(prices[-self.config.ichimoku_tenkan_sen:])
        tenkan_low = min(prices[-self.config.ichimoku_tenkan_sen:])
        tenkan_sen = (tenkan_high + tenkan_low) / 2
        
        # Kijun-sen
        kijun_high = max(prices[-self.config.ichimoku_kijun_sen:])
        kijun_low = min(prices[-self.config.ichimoku_kijun_sen:])
        kijun_sen = (kijun_high + kijun_low) / 2
        
        # Senkou Span A
        senkou_span_a = (tenkan_sen + kijun_sen) / 2
        
        # Senkou Span B
        senkou_b_high = max(prices[-self.config.ichimoku_senkou_span_b:])
        senkou_b_low = min(prices[-self.config.ichimoku_senkou_span_b:])
        senkou_span_b = (senkou_b_high + senkou_b_low) / 2
        
        return tenkan_sen, kijun_sen, senkou_span_a, senkou_span_b
    
    def detect_ichimoku_signal(self, current_price: float, timeframe: str = "TICK") -> Optional[OrderType]:
        """Détecte un signal de croisement Ichimoku pour un timeframe donné"""
        tenkan, kijun, senkou_a, senkou_b = self.calculate_ichimoku(timeframe)
        
        if None in [tenkan, kijun, senkou_a, senkou_b]:
            return None
        
        cloud_top = max(senkou_a, senkou_b)
        cloud_bottom = min(senkou_a, senkou_b)
        
        # Prix au-dessus du nuage = signal haussier
        if current_price > cloud_top and tenkan > kijun:
            return OrderType.BUY
        elif current_price < cloud_bottom and tenkan < kijun:
            return OrderType.SELL
        
        return None
    
    def calculate_stc(self, timeframe: str = "TICK") -> Optional[float]:
        """Calcule le Schaff Trend Cycle pour un timeframe donné"""
        # Sélectionner l'historique approprié
        if timeframe == "M1":
            price_history = self.price_history_m1
        elif timeframe == "M5":
            price_history = self.price_history_m5
        else:
            price_history = self.price_history_tick
        
        if len(price_history) < self.config.stc_slow_length:
            return None
        
        prices = np.array(list(price_history)[-self.config.stc_slow_length:])
        
        # Calculer MACD
        ema_fast = self._ema(prices, self.config.stc_fast_length)
        ema_slow = self._ema(prices, self.config.stc_slow_length)
        macd = ema_fast[-1] - ema_slow[-1]
        
        # Normaliser MACD entre 0 et 100
        macd_values = ema_fast - ema_slow
        macd_min = np.min(macd_values[-self.config.stc_period:])
        macd_max = np.max(macd_values[-self.config.stc_period:])
        
        if macd_max - macd_min == 0:
            return 50.0
        
        stoch = 100 * (macd - macd_min) / (macd_max - macd_min)
        
        # Appliquer un lissage
        stc = self._ema(np.array([stoch]), 3)[-1]
        
        return float(stc)
    
    def _ema(self, data: np.ndarray, period: int) -> np.ndarray:
        """Calcule l'EMA"""
        if len(data) < period:
            return data
        
        multiplier = 2.0 / (period + 1)
        ema = np.zeros(len(data))
        ema[0] = data[0]
        
        for i in range(1, len(data)):
            ema[i] = data[i] * multiplier + ema[i-1] * (1 - multiplier)
        
        return ema
    
    def confirm_with_stc(self, signal: OrderType, timeframe: str = "TICK") -> bool:
        """Confirme un signal avec le STC pour un timeframe donné"""
        stc_value = self.calculate_stc(timeframe)
        
        if stc_value is None:
            return False
        
        if signal == OrderType.BUY:
            return stc_value >= self.config.stc_threshold_buy and stc_value <= 50
        elif signal == OrderType.SELL:
            return stc_value <= self.config.stc_threshold_sell and stc_value >= 50
        
        return False
