#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Worker thread pour calcul des indicateurs de manière asynchrone
"""

import threading
import time
from typing import Optional, Dict, Any
import logging
from queue import Queue
from datetime import datetime

from indicators.hft_indicators import HFTIndicators
from config.trading_config import TradingConfig

logger = logging.getLogger(__name__)


class IndicatorWorker:
    """Worker thread pour calculs d'indicateurs non-bloquants"""
    
    def __init__(self, indicators: HFTIndicators, config: TradingConfig):
        self.indicators = indicators
        self.config = config
        
        self.worker_thread = None
        self.stop_event = threading.Event()
        
        # Cache des derniers résultats
        self.cache_lock = threading.Lock()
        self.indicator_cache: Dict[str, Any] = {
            'ichimoku_m1': None,
            'ichimoku_m5': None,
            'stc_m1': None,
            'stc_m5': None,
            'last_update': None,
            'computation_time_ms': 0,
        }
        
        # Queue pour demandes de calcul
        self.request_queue = Queue()
        
        # Statistiques
        self.total_computations = 0
        self.total_time_ms = 0
    
    def start(self) -> None:
        """Démarre le worker thread"""
        if self.worker_thread is None or not self.worker_thread.is_alive():
            self.stop_event.clear()
            self.worker_thread = threading.Thread(target=self._worker_loop, daemon=True)
            self.worker_thread.start()
            logger.info("IndicatorWorker démarré")
    
    def stop(self) -> None:
        """Arrête le worker thread"""
        self.stop_event.set()
        if self.worker_thread:
            self.worker_thread.join(timeout=2)
        logger.info("IndicatorWorker arrêté")
    
    def _worker_loop(self) -> None:
        """Boucle principale du worker"""
        while not self.stop_event.is_set():
            try:
                # Attendre une demande (timeout 0.5s)
                if not self.request_queue.empty():
                    request = self.request_queue.get(timeout=0.5)
                    self._process_request(request)
                else:
                    time.sleep(0.1)
                    
            except Exception as e:
                logger.error(f"Erreur dans IndicatorWorker: {e}")
                time.sleep(0.5)
    
    def _process_request(self, request: dict) -> None:
        """Traite une demande de calcul"""
        
        start_time = time.perf_counter()
        
        try:
            request_type = request.get('type')
            data = request.get('data')
            
            if request_type == 'compute_all':
                self._compute_all_indicators(data)
            elif request_type == 'compute_ichimoku':
                self._compute_ichimoku(data)
            elif request_type == 'compute_stc':
                self._compute_stc(data)
            
            computation_time = (time.perf_counter() - start_time) * 1000
            
            with self.cache_lock:
                self.indicator_cache['last_update'] = datetime.now()
                self.indicator_cache['computation_time_ms'] = computation_time
            
            self.total_computations += 1
            self.total_time_ms += computation_time
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul des indicateurs: {e}")
    
    def _compute_all_indicators(self, data: dict) -> None:
        """Calcule tous les indicateurs"""
        
        m1_candles = data.get('m1_candles', [])
        m5_candles = data.get('m5_candles', [])
        
        if len(m1_candles) < 60 or len(m5_candles) < 60:
            return
        
        # Mettre à jour l'historique des indicateurs
        self.indicators.update_from_m1_candles(m1_candles)
        self.indicators.update_from_m5_candles(m5_candles)
        
        # Calculer Ichimoku M1
        tenkan_m1, kijun_m1, senkou_a_m1, senkou_b_m1 = self.indicators.calculate_ichimoku('M1')
        
        if tenkan_m1 is not None and kijun_m1 is not None:
            # Déterminer le signal Ichimoku
            if tenkan_m1 > kijun_m1:
                signal_m1 = 'LONG'
            elif tenkan_m1 < kijun_m1:
                signal_m1 = 'SHORT'
            else:
                signal_m1 = 'NEUTRAL'
            
            ichimoku_m1 = {
                'tenkan_sen': tenkan_m1,
                'kijun_sen': kijun_m1,
                'senkou_span_a': senkou_a_m1,
                'senkou_span_b': senkou_b_m1,
                'signal': signal_m1
            }
        else:
            ichimoku_m1 = None
        
        # Calculer Ichimoku M5
        tenkan_m5, kijun_m5, senkou_a_m5, senkou_b_m5 = self.indicators.calculate_ichimoku('M5')
        
        if tenkan_m5 is not None and kijun_m5 is not None:
            if tenkan_m5 > kijun_m5:
                signal_m5 = 'LONG'
            elif tenkan_m5 < kijun_m5:
                signal_m5 = 'SHORT'
            else:
                signal_m5 = 'NEUTRAL'
            
            ichimoku_m5 = {
                'tenkan_sen': tenkan_m5,
                'kijun_sen': kijun_m5,
                'senkou_span_a': senkou_a_m5,
                'senkou_span_b': senkou_b_m5,
                'signal': signal_m5
            }
        else:
            ichimoku_m5 = None
        
        # Calculer STC M1 et M5
        stc_m1_value = self.indicators.calculate_stc('M1')
        stc_m5_value = self.indicators.calculate_stc('M5')
        
        if stc_m1_value is not None:
            stc_m1 = {
                'value': stc_m1_value,
                'signal': 'BUY' if stc_m1_value < self.config.stc_threshold_buy else ('SELL' if stc_m1_value > self.config.stc_threshold_sell else 'NEUTRAL')
            }
        else:
            stc_m1 = None
        
        if stc_m5_value is not None:
            stc_m5 = {
                'value': stc_m5_value,
                'signal': 'BUY' if stc_m5_value < self.config.stc_threshold_buy else ('SELL' if stc_m5_value > self.config.stc_threshold_sell else 'NEUTRAL')
            }
        else:
            stc_m5 = None
        
        # Mettre à jour le cache
        with self.cache_lock:
            self.indicator_cache['ichimoku_m1'] = ichimoku_m1
            self.indicator_cache['ichimoku_m5'] = ichimoku_m5
            self.indicator_cache['stc_m1'] = stc_m1
            self.indicator_cache['stc_m5'] = stc_m5
    
    def _compute_ichimoku(self, data: dict) -> None:
        """Calcule uniquement Ichimoku"""
        
        timeframe = data.get('timeframe', 'M1')
        candles = data.get('candles', [])
        
        if len(candles) < 60:
            return
        
        ichimoku = self.indicators.calculate_ichimoku(
            [c.high for c in candles],
            [c.low for c in candles],
            [c.close for c in candles],
            timeframe
        )
        
        with self.cache_lock:
            self.indicator_cache[f'ichimoku_{timeframe.lower()}'] = ichimoku
    
    def _compute_stc(self, data: dict) -> None:
        """Calcule uniquement STC"""
        
        timeframe = data.get('timeframe', 'M1')
        candles = data.get('candles', [])
        
        if len(candles) < 60:
            return
        
        stc = self.indicators.calculate_stc([c.close for c in candles], timeframe)
        
        with self.cache_lock:
            self.indicator_cache[f'stc_{timeframe.lower()}'] = stc
    
    def request_computation(self, request_type: str, data: dict) -> None:
        """Ajoute une demande de calcul à la queue"""
        self.request_queue.put({'type': request_type, 'data': data})
    
    def get_cached_indicators(self) -> Dict[str, Any]:
        """Retourne les indicateurs en cache"""
        with self.cache_lock:
            return self.indicator_cache.copy()
    
    def get_statistics(self) -> dict:
        """Retourne les statistiques du worker"""
        avg_time = self.total_time_ms / self.total_computations if self.total_computations > 0 else 0
        
        return {
            'total_computations': self.total_computations,
            'total_time_ms': self.total_time_ms,
            'average_time_ms': avg_time,
            'is_running': self.worker_thread.is_alive() if self.worker_thread else False,
        }
