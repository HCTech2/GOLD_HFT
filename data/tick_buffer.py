#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de gestion du buffer circulaire de ticks.
Stocke les ticks en temps réel et construit les bougies OHLC M1 et M5.
"""

import threading
from collections import deque
from typing import List, Tuple, Optional, Deque
from datetime import datetime
import numpy as np
import MetaTrader5 as mt5
import logging

from models.tick import Tick
from models.ohlc import OHLC

logger = logging.getLogger(__name__)


class TickBuffer:
    """Buffer circulaire pour stocker les ticks en temps réel"""
    
    def __init__(self, max_size: int = 10000, symbol: str = "XAUUSD-m"):
        self.max_size = max_size
        self.symbol = symbol
        self.ticks: Deque[Tick] = deque(maxlen=max_size)
        self.lock = threading.Lock()
        self.last_update = None
        self.tick_count = 0  # Compteur total de ticks reçus
        
        # Buffers OHLC pour différents timeframes
        self.m1_candles: Deque[OHLC] = deque(maxlen=100)  # 100 bougies M1
        self.m5_candles: Deque[OHLC] = deque(maxlen=100)  # 100 bougies M5
        
        # Variables pour construire les bougies
        self.current_m1_candle: Optional[OHLC] = None
        self.current_m5_candle: Optional[OHLC] = None
        self.last_m1_time: Optional[datetime] = None
        self.last_m5_time: Optional[datetime] = None
    
    def load_historical_candles(self, count: int = 60) -> bool:
        """Charge l'historique des bougies M1 et M5 depuis MT5"""
        try:
            logger.info(f"Chargement de l'historique OHLC pour {self.symbol}...")
            
            # Charger les bougies M1
            m1_rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M1, 0, count)
            if m1_rates is not None and len(m1_rates) > 0:
                with self.lock:
                    self.m1_candles.clear()
                    for rate in m1_rates:
                        candle = OHLC(
                            timestamp=datetime.fromtimestamp(rate['time']),
                            open=rate['open'],
                            high=rate['high'],
                            low=rate['low'],
                            close=rate['close'],
                            volume=int(rate['tick_volume'])
                        )
                        self.m1_candles.append(candle)
                    
                    # La dernière bougie devient la bougie courante
                    if len(self.m1_candles) > 0:
                        self.last_m1_time = self.m1_candles[-1].timestamp
                
                logger.info(f"[OK] {len(m1_rates)} bougies M1 chargées")
            else:
                logger.warning(f"[WARN] Impossible de charger les bougies M1 pour {self.symbol}")
            
            # Charger les bougies M5
            m5_rates = mt5.copy_rates_from_pos(self.symbol, mt5.TIMEFRAME_M5, 0, count)
            if m5_rates is not None and len(m5_rates) > 0:
                with self.lock:
                    self.m5_candles.clear()
                    for rate in m5_rates:
                        candle = OHLC(
                            timestamp=datetime.fromtimestamp(rate['time']),
                            open=rate['open'],
                            high=rate['high'],
                            low=rate['low'],
                            close=rate['close'],
                            volume=int(rate['tick_volume'])
                        )
                        self.m5_candles.append(candle)
                    
                    # La dernière bougie devient la bougie courante
                    if len(self.m5_candles) > 0:
                        self.last_m5_time = self.m5_candles[-1].timestamp
                
                logger.info(f"[OK] {len(m5_rates)} bougies M5 chargées")
            else:
                logger.warning(f"[WARN] Impossible de charger les bougies M5 pour {self.symbol}")
            
            return True
            
        except Exception as e:
            logger.error(f"[ERROR] Erreur lors du chargement de l'historique OHLC: {e}")
            return False
    
    def add_tick(self, tick: Tick) -> None:
        """Ajoute un tick au buffer et met à jour les bougies OHLC"""
        with self.lock:
            self.ticks.append(tick)
            self.tick_count += 1  # Incrémenter le compteur
            self.last_update = datetime.now()
            
            # Mettre à jour les bougies M1 et M5
            self._update_ohlc_candles(tick)
    
    def _update_ohlc_candles(self, tick: Tick) -> None:
        """Met à jour les bougies OHLC M1 et M5"""
        # Arrondir au début de la minute
        minute_start = tick.timestamp.replace(second=0, microsecond=0)
        
        # Mise à jour M1
        if self.last_m1_time is None or minute_start > self.last_m1_time:
            # Nouvelle bougie M1
            if self.current_m1_candle is not None:
                self.m1_candles.append(self.current_m1_candle)
            
            self.current_m1_candle = OHLC(
                timestamp=minute_start,
                open=tick.mid_price,
                high=tick.mid_price,
                low=tick.mid_price,
                close=tick.mid_price,
                volume=tick.volume
            )
            self.last_m1_time = minute_start
        else:
            # Mise à jour bougie M1 courante
            if self.current_m1_candle is not None:
                self.current_m1_candle.high = max(self.current_m1_candle.high, tick.mid_price)
                self.current_m1_candle.low = min(self.current_m1_candle.low, tick.mid_price)
                self.current_m1_candle.close = tick.mid_price
                self.current_m1_candle.volume += tick.volume
        
        # Mise à jour M5 (arrondir à 5 minutes)
        minute = tick.timestamp.minute
        m5_minute = (minute // 5) * 5
        m5_start = tick.timestamp.replace(minute=m5_minute, second=0, microsecond=0)
        
        if self.last_m5_time is None or m5_start > self.last_m5_time:
            # Nouvelle bougie M5
            if self.current_m5_candle is not None:
                self.m5_candles.append(self.current_m5_candle)
            
            self.current_m5_candle = OHLC(
                timestamp=m5_start,
                open=tick.mid_price,
                high=tick.mid_price,
                low=tick.mid_price,
                close=tick.mid_price,
                volume=tick.volume
            )
            self.last_m5_time = m5_start
        else:
            # Mise à jour bougie M5 courante
            if self.current_m5_candle is not None:
                self.current_m5_candle.high = max(self.current_m5_candle.high, tick.mid_price)
                self.current_m5_candle.low = min(self.current_m5_candle.low, tick.mid_price)
                self.current_m5_candle.close = tick.mid_price
                self.current_m5_candle.volume += tick.volume
    
    def get_m1_candles(self, count: int = 60) -> List[OHLC]:
        """Retourne les N dernières bougies M1"""
        with self.lock:
            candles = list(self.m1_candles)[-count:]
            if self.current_m1_candle is not None:
                candles.append(self.current_m1_candle)
            return candles
    
    def get_m5_candles(self, count: int = 60) -> List[OHLC]:
        """Retourne les N dernières bougies M5"""
        with self.lock:
            candles = list(self.m5_candles)[-count:]
            if self.current_m5_candle is not None:
                candles.append(self.current_m5_candle)
            return candles
    
    def get_recent_ticks(self, count: int = 100) -> List[Tick]:
        """Retourne les N derniers ticks"""
        with self.lock:
            return list(self.ticks)[-count:] if len(self.ticks) > 0 else []
    
    def get_all_ticks(self) -> List[Tick]:
        """Retourne tous les ticks du buffer"""
        with self.lock:
            return list(self.ticks)
    
    def get_tick_count(self) -> int:
        """Retourne le nombre de ticks dans le buffer"""
        with self.lock:
            return len(self.ticks)
    
    def get_price_range(self) -> Tuple[float, float]:
        """Retourne le prix min et max des ticks actuels"""
        with self.lock:
            if not self.ticks:
                return 0.0, 0.0
            prices = [t.mid_price for t in self.ticks]
            return min(prices), max(prices)
    
    def get_average_spread(self) -> float:
        """Retourne le spread moyen"""
        with self.lock:
            if not self.ticks:
                return 0.0
            spreads = [t.spread for t in self.ticks]
            return np.mean(spreads) if spreads else 0.0
