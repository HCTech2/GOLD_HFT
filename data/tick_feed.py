#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Module de flux de données en temps réel depuis MT5.
Récupère les ticks et les ajoute au buffer.
"""

import threading
import logging
import time
from datetime import datetime
import MetaTrader5 as mt5

from models.tick import Tick
from data.tick_buffer import TickBuffer
from config.trading_config import TradingConfig

logger = logging.getLogger(__name__)


class TickDataFeed:
    """Flux de données en temps réel des ticks depuis MT5"""
    
    def __init__(self, symbol: str, config: TradingConfig):
        self.symbol = symbol
        self.config = config
        self.tick_buffer = TickBuffer(config.tick_buffer_size, symbol)
        self.stop_event = threading.Event()
        self.feed_thread = None
        self.tick_count = 0
        self.last_tick_time = None
    
    def start(self) -> None:
        """Démarre le flux de données"""
        if self.feed_thread is None or not self.feed_thread.is_alive():
            # Charger l'historique OHLC au démarrage
            logger.info("=" * 80)
            logger.info("INITIALISATION DES TIMEFRAMES M1 ET M5")
            logger.info("=" * 80)
            self.tick_buffer.load_historical_candles(60)
            logger.info("=" * 80)
            
            self.stop_event.clear()
            self.feed_thread = threading.Thread(target=self._feed_loop, daemon=True)
            self.feed_thread.start()
            logger.info(f"Flux de ticks démarré pour {self.symbol}")
    
    def stop(self) -> None:
        """Arrête le flux de données"""
        self.stop_event.set()
        if self.feed_thread:
            self.feed_thread.join(timeout=5)
        logger.info(f"Flux de ticks arrêté pour {self.symbol}")
    
    def _feed_loop(self) -> None:
        """Boucle principale de récupération des ticks"""
        last_tick_time = None
        last_bid = None
        last_ask = None
        
        while not self.stop_event.is_set():
            try:
                # Récupération du dernier tick depuis MT5
                tick = mt5.symbol_info_tick(self.symbol)
                
                if tick is None:
                    time.sleep(0.001)  # Petit délai si pas de tick
                    continue
                
                # Éviter les doublons - vérifier timestamp ET prix
                current_tick_time = datetime.fromtimestamp(tick.time)
                
                # Ne skip que si MÊME timestamp ET MÊME prix (tick identique)
                if (last_tick_time and current_tick_time == last_tick_time and
                    last_bid == tick.bid and last_ask == tick.ask):
                    time.sleep(0.001)  # Petit délai pour ne pas surcharger le CPU
                    continue
                
                # Créer un objet Tick
                new_tick = Tick(
                    symbol=self.symbol,
                    bid=tick.bid,
                    ask=tick.ask,
                    timestamp=current_tick_time,
                    volume=tick.volume if hasattr(tick, 'volume') else 0
                )
                
                # Ajouter au buffer
                self.tick_buffer.add_tick(new_tick)
                self.tick_count += 1
                self.last_tick_time = current_tick_time
                last_tick_time = current_tick_time
                last_bid = tick.bid
                last_ask = tick.ask
                
            except Exception as e:
                logger.error(f"Erreur dans la boucle de ticks: {e}")
                time.sleep(0.1)  # Pause en cas d'erreur
    
    def get_tick_buffer(self) -> TickBuffer:
        """Retourne le buffer de ticks"""
        return self.tick_buffer
    
    def get_tick_count(self) -> int:
        """Retourne le nombre total de ticks reçus"""
        return self.tick_count
