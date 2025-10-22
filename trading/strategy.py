#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Stratégie HFT complète avec Ichimoku + STC
"""

import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Dict, Optional, Tuple
from collections import deque
import logging

import MetaTrader5 as mt5

from config.trading_config import TradingConfig, OrderType
from analytics.market_observer import MarketObserver, MarketContext
from analytics.ml_agent import HFTLearningAgent, MLRecommendation, TradeExperience
from data.tick_feed import TickDataFeed
from indicators.hft_indicators import HFTIndicators
from trading.position_manager import HFTPositionManager
from trading.risk_manager import RiskManager, RiskLimits
from trading.sweep_manager import SweepManager
from ml.trade_database import TradeDatabase, TradeEvent
from models.data_models import Tick, TradeRecord

logger = logging.getLogger(__name__)


class HFTStrategy:
    """Stratégie de trading haute fréquence basée sur Ichimoku + STC"""
    
    def __init__(self, config: TradingConfig, gui=None):
        self.config = config
        self.gui = gui  # Référence à la GUI pour accéder aux multiplicateurs
        self.tick_feed = TickDataFeed(config.symbol, config)
        self.indicators = HFTIndicators(config)
        self.position_manager = HFTPositionManager(config, gui=gui)
        self.market_observer = MarketObserver(config, self.indicators)
        self.last_market_context: Optional[MarketContext] = None
        self.learning_agent = (
            HFTLearningAgent(config, Path(config.ml_state_file)) if config.ml_enabled else None
        )
        self.active_recommendations: Dict[int, MLRecommendation] = {}
        self.last_recommendation: Optional[MLRecommendation] = None
        self.position_manager.register_close_callback(self._on_trade_closed)

        # Journalisation des trades pour le pipeline ML
        self.trade_database = TradeDatabase()
        self._pending_trade_events: Dict[int, TradeEvent] = {}
        self._last_indicator_snapshot: Dict[str, Any] = {}
        
        # Initialiser le Risk Manager
        risk_limits = RiskLimits(
            max_daily_loss=config.risk_max_daily_loss,
            max_daily_trades=config.risk_max_daily_trades,
            max_consecutive_losses=config.risk_max_consecutive_losses,
            max_drawdown_percent=config.risk_max_drawdown_percent,
            max_correlated_positions=config.risk_max_correlated_positions,
            max_portfolio_risk_percent=config.risk_max_portfolio_risk_percent,
            cooldown_after_loss_streak_minutes=config.risk_cooldown_after_loss_streak_minutes,
        )
        self.risk_manager = RiskManager(config, risk_limits)
        
        # Initialiser le Sweep Manager
        self.sweep_manager = SweepManager(config)
        
        self.strategy_thread = None
        self.stop_event = threading.Event()
        self.is_running = False
        
        # Métriques
        self.signals_generated = 0
        self.orders_sent = 0
        self.orders_rejected = 0
        self.last_signal_time = None
        self.last_analysis_duration = 0.0
        
        # Cooldown entre trades
        self.last_trade_time = None
        self.min_trade_interval = timedelta(seconds=config.min_seconds_between_trades)
    
    def start(self) -> bool:
        """Démarre la stratégie de trading"""
        
        # Initialiser MT5
        if not mt5.initialize():
            logger.error("Échec de l'initialisation de MT5")
            return False
        
        logger.info(f"MT5 initialisé - Version: {mt5.version()}")
        
        # Vérifier connexion compte
        account_info = mt5.account_info()
        if account_info is None:
            logger.error("Impossible de récupérer les informations du compte")
            return False
        
        logger.info(f"Compte: {account_info.login}, Serveur: {account_info.server}")
        logger.info(f"Balance: {account_info.balance:.2f}, Equity: {account_info.equity:.2f}")
        
        # Vérifier le symbole
        symbol_info = mt5.symbol_info(self.config.symbol)
        if symbol_info is None:
            logger.error(f"Symbole {self.config.symbol} non trouvé")
            return False
        
        if not symbol_info.visible:
            if not mt5.symbol_select(self.config.symbol, True):
                logger.error(f"Impossible d'activer le symbole {self.config.symbol}")
                return False
        
        logger.info(f"Symbole: {self.config.symbol}, Spread: {symbol_info.spread}, Point: {symbol_info.point}")
        
        # Démarrer le flux de ticks
        self.tick_feed.start()
        time.sleep(2)  # Laisser le buffer se remplir
        
        # Démarrer le thread de stratégie
        self.stop_event.clear()
        self.is_running = True
        self.strategy_thread = threading.Thread(target=self._strategy_loop, daemon=True)
        self.strategy_thread.start()
        
        logger.info("=" * 80)
        logger.info("STRATÉGIE HFT DÉMARRÉE")
        logger.info("=" * 80)
        
        return True
    
    def _calculate_htf_confidence(self, buy_votes: int, sell_votes: int, total_votes: int, market_trend: OrderType) -> float:
        """
        Calcule le score de confiance HTF (0-100%) basé sur l'alignement des timeframes
        
        Args:
            buy_votes: Nombre de votes BUY
            sell_votes: Nombre de votes SELL
            total_votes: Total de votes valides
            market_trend: Tendance décidée par M1
        
        Returns:
            Score de confiance 0-100%
        """
        if total_votes == 0:
            return 0.0
        
        # Calculer le pourcentage d'alignement avec la tendance M1
        if market_trend == OrderType.BUY:
            aligned_votes = buy_votes
        elif market_trend == OrderType.SELL:
            aligned_votes = sell_votes
        else:
            return 0.0
        
        confidence = (aligned_votes / total_votes) * 100.0
        return confidence
    
    def _get_strategy_timeframe(self) -> str:
        """
        Retourne le timeframe configuré pour la stratégie
        Gère la compatibilité avec TICK qui utilise M1
        
        Returns:
            Timeframe: 'M1', 'M5', etc.
        """
        tf = getattr(self.config, 'strategy_timeframe', 'M1').upper()
        
        # TICK utilise M1 comme base
        if tf == 'TICK':
            return 'M1'
        
        return tf
    
    def _get_candles_for_strategy(self, tick_buffer, count: int = 100):
        """
        Récupère les bougies selon le timeframe configuré
        
        Args:
            tick_buffer: Buffer de ticks
            count: Nombre de bougies à récupérer
        
        Returns:
            Liste de bougies du timeframe configuré
        """
        tf = self._get_strategy_timeframe()
        
        if tf == 'M1':
            return tick_buffer.get_m1_candles(count)
        elif tf == 'M5':
            return tick_buffer.get_m5_candles(count)
        else:
            # Par défaut M1
            logger.warning(f"[⚠️ TIMEFRAME] {tf} non supporté, utilisation de M1")
            return tick_buffer.get_m1_candles(count)
    
    def _get_dynamic_tp_sl_multipliers(self, confidence: float) -> tuple[float, float]:
        """
        Retourne les multiplicateurs TP/SL selon le score de confiance HTF
        
        Args:
            confidence: Score de confiance 0-100%
        
        Returns:
            (tp_multiplier, sl_multiplier)
        """
        if confidence >= self.config.confidence_high_min:
            # Confiance HAUTE → TP large, SL serré
            return (self.config.tp_multiplier_high_confidence, self.config.sl_multiplier_high_confidence)
        elif confidence >= self.config.confidence_medium_min:
            # Confiance MOYENNE → TP/SL standard
            return (self.config.tp_multiplier_medium_confidence, self.config.sl_multiplier_medium_confidence)
        else:
            # Confiance FAIBLE → TP prudent, SL large
            return (self.config.tp_multiplier_low_confidence, self.config.sl_multiplier_low_confidence)
    
    def stop(self) -> None:
        """Arrête la stratégie de trading"""
        logger.info("Arrêt de la stratégie...")
        
        self.stop_event.set()
        self.is_running = False
        
        if self.strategy_thread:
            self.strategy_thread.join(timeout=5)
        
        self.tick_feed.stop()
        self.position_manager.stop_position_monitor()
        
        mt5.shutdown()

        try:
            self.trade_database.close()
        except Exception as db_err:
            logger.error(f"Erreur lors de la fermeture de la base de trades: {db_err}", exc_info=True)
        
        logger.info("Stratégie arrêtée")
    
    def _strategy_loop(self) -> None:
        """Boucle principale de la stratégie"""
        
        last_tick_count = 0
        loop_iteration = 0
        
        logger.info("[STRATEGY_LOOP] Boucle de stratégie démarrée")
        
        while not self.stop_event.is_set():
            try:
                loop_iteration += 1
                start_time = time.perf_counter()
                
                # Récupérer les ticks récents
                tick_buffer = self.tick_feed.get_tick_buffer()
                current_tick_count = tick_buffer.tick_count
                
                # Log périodique pour diagnostic (toutes les 100 itérations)
                if loop_iteration % 100 == 0:
                    logger.info(f"[STRATEGY_LOOP] Itération {loop_iteration} - tick_count: {current_tick_count} (last: {last_tick_count})")
                
                # Analyser uniquement si de nouveaux ticks
                if current_tick_count > last_tick_count:
                    logger.info(f"[🎯 NOUVEAUX TICKS] {current_tick_count} > {last_tick_count} → Appel _analyze_and_execute()")
                    self._analyze_and_execute(tick_buffer)
                    last_tick_count = current_tick_count
                else:
                    # Log si aucun nouveau tick (debug uniquement toutes les 1000 itérations)
                    if loop_iteration % 1000 == 0:
                        logger.info(f"[⏸️ ATTENTE] Aucun nouveau tick - current:{current_tick_count} = last:{last_tick_count}")
                
                # Mesurer la durée d'analyse
                self.last_analysis_duration = time.perf_counter() - start_time
                
                # Pause pour éviter surcharge CPU
                time.sleep(self.config.tick_analysis_interval)
                
            except Exception as e:
                logger.error(f"Erreur dans la boucle de stratégie: {e}", exc_info=True)
                time.sleep(1)

    # ------------------------------------------------------------------
    # Outils ML et gestion des positions
    # ------------------------------------------------------------------
    def _get_ml_recommendation(self, order_type: OrderType) -> Optional[MLRecommendation]:
        if not self.learning_agent or not self.last_market_context:
            return None

        try:
            recommendation = self.learning_agent.recommend(self.last_market_context, order_type)
            self.last_recommendation = recommendation
            return recommendation
        except Exception as err:
            logger.error(f"[ML] Impossible de générer une recommandation: {err}", exc_info=True)
            return None

    def _build_trade_metadata(
        self,
        order_type: OrderType,
        recommendation: Optional[MLRecommendation],
    ) -> Dict[str, object]:
        market_context_dict = (
            MarketObserver.serialize_context(self.last_market_context)
            if self.last_market_context
            else {}
        )

        trailing_plan = {
            "secure_profit": recommendation.secure_profit if recommendation else self.config.trailing_secure_base,
            "extension_trigger": recommendation.extension_trigger if recommendation else self.config.trailing_extension_base,
            "trailing_distance": recommendation.trailing_distance if recommendation else self.config.trailing_distance_base,
        }

        metadata: Dict[str, object] = {
            "order_type": order_type.value,
            "created_at": datetime.utcnow().isoformat(),
            "market_context": market_context_dict,
            "trailing_plan": trailing_plan,
        }

        if recommendation:
            metadata.update(
                {
                    "ml_recommendation": HFTLearningAgent.recommendation_to_dict(recommendation),
                    "ml_confidence": recommendation.confidence,
                    "risk_multiplier": recommendation.risk_multiplier,
                    "sl_multiplier": recommendation.sl_multiplier,
                    "tp_multiplier": recommendation.tp_multiplier,
                    "avoid_trade": recommendation.avoid_trade,
                }
            )

        return metadata

    def _sanitize_for_json(self, value: Any) -> Any:
        if isinstance(value, dict):
            return {str(k): self._sanitize_for_json(v) for k, v in value.items()}
        if isinstance(value, (list, tuple, set)):
            return [self._sanitize_for_json(v) for v in value]
        if isinstance(value, datetime):
            return value.isoformat()
        if isinstance(value, timedelta):
            return value.total_seconds()
        if isinstance(value, OrderType):
            return value.value
        if isinstance(value, (int, float, str, bool)) or value is None:
            return value
        return str(value)

    def _get_symbol_spread(self) -> Optional[float]:
        symbol_info = mt5.symbol_info(self.config.symbol)
        if not symbol_info:
            return None
        return float(symbol_info.spread * symbol_info.point)

    def _register_trade_open(
        self,
        ticket: int,
        order_type: OrderType,
        entry_price: float,
        volume: float,
        stop_loss: float,
        take_profit: float,
        htf_confidence: float,
        metadata: Dict[str, Any],
        recommendation: Optional[MLRecommendation],
        rr_ratio: float,
        sweep_info: Optional[Dict[str, Any]] = None,
    ) -> None:
        context = self.last_market_context
        snapshot = self._last_indicator_snapshot or {}

        sanitized_metadata = self._sanitize_for_json(metadata or {})

        sweep_phase = None
        order_number = 0
        sweep_speed = None
        if sweep_info:
            sweep_phase = sweep_info.get("phase")
            order_number = int(sweep_info.get("order_number", 0) or 0)
            sweep_speed = sweep_info.get("sweep_speed")
        else:
            sweep_phase = sanitized_metadata.get("sweep_phase")
            order_number = int(sanitized_metadata.get("order_number", 0) or 0)

        features = {
            "rr_ratio": rr_ratio,
            "stop_loss": stop_loss,
            "take_profit": take_profit,
            "sl_multiplier_total": sanitized_metadata.get("sl_multiplier_total"),
            "tp_multiplier_total": sanitized_metadata.get("tp_multiplier_total"),
            "volume_multiplier_total": sanitized_metadata.get("volume_multiplier_total"),
            "htf_confidence": htf_confidence,
            "strategy_timeframe": snapshot.get("strategy_tf"),
            "volatility_pp": snapshot.get("volatility_pp") or (context.volatility_pp if context else None),
            "volume_ratio": snapshot.get("volume_ratio"),
            "volume_pressure": snapshot.get("volume_pressure"),
            "session_label": snapshot.get("session_label"),
            "favorable_window": context.favorable_window if context else None,
            "trade_type": "SWEEP" if sweep_info else "CORE",
            "sweep_speed": sweep_speed,
        }

        if recommendation:
            features.update(
                {
                    "ml_confidence": recommendation.confidence,
                    "ml_risk_multiplier": recommendation.risk_multiplier,
                    "ml_sl_multiplier": recommendation.sl_multiplier,
                    "ml_tp_multiplier": recommendation.tp_multiplier,
                }
            )

        event = TradeEvent(
            timestamp=time.time(),
            symbol=self.config.symbol,
            direction=order_type.value,
            strategy="SWEEP" if sweep_info else "CORE",
            entry_price=entry_price,
            exit_price=None,
            volume=volume,
            profit_loss=None,
            duration_sec=None,
            order_number=order_number,
            sweep_phase=sweep_phase,
            confidence=recommendation.confidence if recommendation else sanitized_metadata.get("ml_confidence"),
            htf_confidence=htf_confidence,
            stc_m1=snapshot.get("stc_m1"),
            stc_m5=snapshot.get("stc_m5"),
            ichimoku_tenkan=snapshot.get("tenkan"),
            ichimoku_kijun=snapshot.get("kijun"),
            atr=context.volatility_pp if context else None,
            spread=self._get_symbol_spread(),
            features=self._sanitize_for_json(features),
            metadata=sanitized_metadata,
        )

        self._pending_trade_events[ticket] = event

    def _finalize_trade_event(self, trade: TradeRecord, duration_seconds: float) -> None:
        event = self._pending_trade_events.pop(trade.ticket, None)
        metadata = self._sanitize_for_json(trade.metadata or {})
        exit_price = trade.exit_price
        profit = trade.profit

        if event is None:
            entry_timestamp = trade.entry_time.timestamp() if trade.entry_time else time.time()
            event = TradeEvent(
                timestamp=entry_timestamp,
                symbol=trade.symbol,
                direction=trade.order_type.value,
                strategy=metadata.get("trade_type", "CORE"),
                entry_price=trade.entry_price,
                exit_price=exit_price,
                volume=trade.volume,
                profit_loss=profit,
                duration_sec=duration_seconds,
                order_number=int(metadata.get("order_number", 0) or 0),
                sweep_phase=metadata.get("sweep_phase"),
                confidence=metadata.get("ml_confidence"),
                htf_confidence=metadata.get("htf_confidence"),
                stc_m1=self._last_indicator_snapshot.get("stc_m1"),
                stc_m5=self._last_indicator_snapshot.get("stc_m5"),
                ichimoku_tenkan=self._last_indicator_snapshot.get("tenkan"),
                ichimoku_kijun=self._last_indicator_snapshot.get("kijun"),
                atr=self._last_indicator_snapshot.get("volatility_pp"),
                spread=self._get_symbol_spread(),
                features={},
                metadata=metadata,
            )
        else:
            event.exit_price = exit_price
            event.profit_loss = profit
            event.duration_sec = duration_seconds
            event.metadata.update(metadata)

        post_features = {
            "max_unrealized_profit": metadata.get("max_unrealized_profit"),
            "max_unrealized_drawdown": metadata.get("max_unrealized_drawdown"),
            "last_unrealized_profit": metadata.get("last_unrealized_profit"),
            "close_reason": metadata.get("close_reason"),
        }

        event.features.update(self._sanitize_for_json(post_features))
        event.metadata["exit_time"] = trade.exit_time.isoformat() if trade.exit_time else None

        self.trade_database.append(event)

    def _manage_open_positions(self) -> None:
        trades = self.position_manager.get_all_positions()
        if not trades:
            return

        for trade in trades:
            trailing_plan = trade.metadata.get("trailing_plan") or {}
            secure = float(trailing_plan.get("secure_profit", self.config.trailing_secure_base))
            extension = float(trailing_plan.get("extension_trigger", self.config.trailing_extension_base))
            trailing_distance = float(trailing_plan.get("trailing_distance", self.config.trailing_distance_base))

            if not trailing_plan:
                trailing_plan = {
                    "secure_profit": secure,
                    "extension_trigger": extension,
                    "trailing_distance": trailing_distance,
                }
                self.position_manager.update_trade_metadata(trade.ticket, {"trailing_plan": trailing_plan})

            updated = self.position_manager.apply_trailing_strategy(
                trade,
                secure,
                extension,
                trailing_distance,
            )

            if updated:
                logger.debug(
                    f"[TRAILING] Ajustement appliqué (ticket={trade.ticket}) stage={trade.metadata.get('trailing_stage')}"
                )

    def _on_trade_closed(self, trade: TradeRecord) -> None:
        # Enregistrer dans le Risk Manager
        self.risk_manager.record_trade_closed(trade)

        duration_seconds = 0.0
        if trade.entry_time and trade.exit_time:
            duration_seconds = max((trade.exit_time - trade.entry_time).total_seconds(), 0.0)

        if self.learning_agent:
            try:
                metadata = trade.metadata or {}
                context_dict = metadata.get("market_context")
                if context_dict:
                    context = self.learning_agent.reconstruct_context(context_dict)

                    max_profit = float(metadata.get("max_unrealized_profit", trade.profit))
                    max_drawdown = float(metadata.get("max_unrealized_drawdown", 0.0))

                    experience = TradeExperience(
                        order_type=trade.order_type,
                        profit=trade.profit,
                        max_profit=max_profit,
                        max_drawdown=max_drawdown,
                        duration_seconds=duration_seconds,
                        context=context,
                    )

                    self.learning_agent.update(experience)
                    logger.info(
                        f"[ML] Trade #{trade.ticket} intégré au modèle (profit={trade.profit:.2f}$, max={max_profit:.2f}$, drawdown={max_drawdown:.2f}$)"
                    )
                else:
                    logger.debug(f"[ML] Aucun contexte de marché pour le trade #{trade.ticket}, apprentissage ignoré")
            except Exception as err:
                logger.error(f"[ML] Échec de la mise à jour du modèle: {err}", exc_info=True)

        self._finalize_trade_event(trade, duration_seconds)
        self.active_recommendations.pop(trade.ticket, None)
    
    def _analyze_and_execute(self, tick_buffer) -> None:
        """
        Analyse HFT avec stratégie de SWEEP:
        - STC détermine la TENDANCE du marché (BUY/SELL)
        - Ichimoku déclenche les ENTRÉES à chaque croisement Tenkan/Kijun
        - Mode SWEEP: Multiplier les entrées rapides dans la tendance
        """
        
        logger.info(f"[🔍 ANALYSE] Début _analyze_and_execute - tick_count: {tick_buffer.tick_count}")
        
        # ===================================================================
        # SYSTÈME DE CLÔTURE RÉACTIVE EN PROFIT (100% PROFITABLE)
        # ===================================================================
        
        if self.config.reactive_profit_enabled:
            # Récupérer toutes les positions du bot
            bot_positions = mt5.positions_get(symbol=self.config.symbol)
            
            if bot_positions:
                # Mode 1: Clôture par position individuelle
                for pos in bot_positions:
                    if pos.magic == 234000:  # Positions du bot uniquement
                        profit = pos.profit
                        
                        # Fermer si profit > seuil par position
                        if profit >= self.config.profit_threshold_per_position:
                            logger.info(f"[CLÔTURE RÉACTIVE] Position #{pos.ticket} - Profit: {profit:.2f}$ (seuil: {self.config.profit_threshold_per_position}$)")
                            self.position_manager.close_position(pos.ticket, reason=f"Profit_Reactive_{profit:.2f}$")
                
                # Mode 2: Clôture cumulative (toutes positions si total > seuil)
                total_profit = self.position_manager.get_total_unrealized_profit()
                
                if total_profit >= self.config.profit_threshold_cumulative:
                    logger.info(f"[CLÔTURE CUMULATIVE] Profit total: {total_profit:.2f}$ (seuil: {self.config.profit_threshold_cumulative}$)")
                    logger.info(f"[CLÔTURE CUMULATIVE] Fermeture de toutes les positions du bot")
                    
                    # Fermer toutes les positions du bot
                    for pos in bot_positions:
                        if pos.magic == 234000:
                            self.position_manager.close_position(pos.ticket, reason=f"Cumulative_Profit_{total_profit:.2f}$")
        
        # ===================================================================
        # STRATÉGIE HFT SWEEP: STC (tendance) + ICHIMOKU (entrées)
        # ===================================================================
        
        # Trailing dynamique sur les positions existantes
        self._manage_open_positions()

        # Vérifier le nombre de positions
        num_positions = self.position_manager.get_open_positions_count()
        if num_positions >= self.config.max_positions:
            logger.info(f"[🚫 POSITIONS] Max atteint ({num_positions}/{self.config.max_positions}) - Pas de nouveau trade")
            return
        
        # ========================================================================
        # RÉCUPÉRATION DES BOUGIES SELON TIMEFRAME CONFIGURÉ
        # ========================================================================
        strategy_tf = self._get_strategy_timeframe()
        logger.info(f"[⏱️ TIMEFRAME] Stratégie sur {strategy_tf} (config: {getattr(self.config, 'strategy_timeframe', 'M1')})")
        
        # Récupérer les bougies du timeframe principal
        candles = self._get_candles_for_strategy(tick_buffer, 100)
        
        if len(candles) < 60:
            logger.warning(f"[📊 DONNÉES] Historique {strategy_tf} insuffisant: {len(candles)}/60 bougies")
            return
        
        # Mise à jour des indicateurs avec le timeframe principal
        if strategy_tf == 'M1':
            self.indicators.update_from_m1_candles(candles)
        elif strategy_tf == 'M5':
            self.indicators.update_from_m5_candles(candles)
        
        logger.info(f"[✅ INDICATEURS] Historique {strategy_tf} mis à jour - {len(candles)} bougies")
        
        # ========================================================================
        # CALCUL DES INDICATEURS SUR LE TIMEFRAME CONFIGURÉ
        # ========================================================================
        
        # Calculer STC sur le timeframe principal
        stc_primary = self.indicators.calculate_stc(strategy_tf)
        
        # Timeframe de confirmation (optionnel)
        stc_confirmation = None
        confirmation_tf = getattr(self.config, 'confirmation_timeframe', 'M5')
        use_confirmation = getattr(self.config, 'use_confirmation_timeframe', False)
        
        if use_confirmation and confirmation_tf != strategy_tf:
            # Charger les bougies du timeframe de confirmation
            if confirmation_tf == 'M1':
                conf_candles = tick_buffer.get_m1_candles(100)
                self.indicators.update_from_m1_candles(conf_candles)
            elif confirmation_tf == 'M5':
                conf_candles = tick_buffer.get_m5_candles(100)
                self.indicators.update_from_m5_candles(conf_candles)
            
            stc_confirmation = self.indicators.calculate_stc(confirmation_tf)
            logger.info(f"[📊 STC] {strategy_tf}={stc_primary}, {confirmation_tf}={stc_confirmation} (confirmation)")
        else:
            logger.info(f"[📊 STC] {strategy_tf}={stc_primary}")

        # Calculer et stocker le contexte de marché enrichi
        try:
            self.last_market_context = self.market_observer.compute_context(tick_buffer)
            logger.info(f"[✅ CONTEXTE] MarketObserver OK")
            self._last_indicator_snapshot.update(
                {
                    "volatility_pp": self.last_market_context.volatility_pp,
                    "volume_ratio": self.last_market_context.volume_ratio,
                    "volume_pressure": self.last_market_context.volume_pressure,
                    "session_label": self.last_market_context.session_label,
                    "favorable_window": self.last_market_context.favorable_window,
                }
            )
        except Exception as ctx_err:
            logger.error(f"Erreur MarketObserver: {ctx_err}", exc_info=True)

        if stc_primary is None:
            logger.info(f"[🚫 STC] Données insuffisantes - {strategy_tf}:{stc_primary}")
            return  # Pas assez de données STC
        
        # ========================================================================
        # COMPATIBILITÉ: Alias pour le code existant
        # ========================================================================
        # Le code utilise stc_m1/stc_m5, on les mappe selon le timeframe configuré
        if strategy_tf == 'M1':
            stc_m1 = stc_primary
            stc_m5 = stc_confirmation if stc_confirmation is not None else stc_primary
        elif strategy_tf == 'M5':
            stc_m5 = stc_primary
            stc_m1 = stc_confirmation if stc_confirmation is not None else stc_primary
        else:
            stc_m1 = stc_primary
            stc_m5 = stc_primary

        self._last_indicator_snapshot.update({"stc_m1": stc_m1, "stc_m5": stc_m5})
        
        logger.info(f"[🎯 ANALYSE HTF] Démarrage filtrage multi-timeframe...")
        
        # ==============================================================
        # ÉTAPE 1: STC DÉTERMINE LA TENDANCE DU MARCHÉ
        # ==============================================================
        market_trend = None
        htf_confidence_score = 0.0  # Score de confiance HTF (0-100%)
        
        # FILTRAGE MULTI-TIMEFRAME (M15/M30/H1/H4) si activé
        if self.config.mtf_filter_enabled:
            # Analyser tous les timeframes HTF
            htf_trends = {}
            for tf in self.config.mtf_timeframes:
                try:
                    trend = self._get_htf_trend_rust(tf)
                    htf_trends[tf] = trend
                    logger.info(f"[HTF {tf}] Tendance calculée: {trend}")
                except Exception as e:
                    logger.error(f"[HTF {tf}] ❌ Erreur calcul: {e}", exc_info=True)
                    htf_trends[tf] = None
            
            logger.info(f"[📊 HTF TRENDS] M15:{htf_trends.get('M15')}, M30:{htf_trends.get('M30')}, H1:{htf_trends.get('H1')}, H4:{htf_trends.get('H4')}")
            
            # Compter les votes pour chaque direction
            buy_votes = sum(1 for trend in htf_trends.values() if trend == OrderType.BUY)
            sell_votes = sum(1 for trend in htf_trends.values() if trend == OrderType.SELL)
            total_votes = len([t for t in htf_trends.values() if t is not None])
            
            logger.info(f"[📊 VOTES HTF] BUY:{buy_votes} SELL:{sell_votes} Total:{total_votes}")
            
            # ========================================================================
            # MODE TICK PRIORITY: M1 décide, HTF donne confiance
            # ========================================================================
            if getattr(self.config, 'tick_priority_mode', False):
                logger.info(f"[⚡ TICK PRIORITY] M1 décide la direction, HTF = confiance uniquement")
                logger.info(f"[📊 CONDITION STC] M1:{stc_m1:.1f} M5:{stc_m5:.1f} | Seuils: Buy<{self.config.stc_threshold_buy} Sell>{self.config.stc_threshold_sell}")
                
                # M1 DÉCIDE la tendance (priorité absolue aux ticks)
                if stc_m1 < self.config.stc_threshold_buy or (stc_m1 < 50 and stc_m5 < 50):
                    market_trend = OrderType.BUY
                    logger.info(f"[➡️ M1 DÉCISION] HAUSSIÈRE (STC M1:{stc_m1:.1f})")
                    
                    # HTF donne CONFIANCE
                    if getattr(self.config, 'htf_confidence_enabled', False):
                        htf_confidence_score = self._calculate_htf_confidence(buy_votes, sell_votes, total_votes, market_trend)
                        logger.info(f"[📊 CONFIANCE HTF] {htf_confidence_score:.1f}% ({buy_votes}/{total_votes} votes BUY)")
                        
                        # Vérifier confiance minimum si requis
                        if htf_confidence_score < self.config.min_confidence_to_trade:
                            logger.warning(f"[⚠️ CONFIANCE FAIBLE] {htf_confidence_score:.1f}% < {self.config.min_confidence_to_trade}% requis - Trade annulé")
                            return
                
                elif stc_m1 > self.config.stc_threshold_sell or (stc_m1 > 50 and stc_m5 > 50):
                    market_trend = OrderType.SELL
                    logger.info(f"[➡️ M1 DÉCISION] BAISSIÈRE (STC M1:{stc_m1:.1f})")
                    
                    # HTF donne CONFIANCE
                    if getattr(self.config, 'htf_confidence_enabled', False):
                        htf_confidence_score = self._calculate_htf_confidence(buy_votes, sell_votes, total_votes, market_trend)
                        logger.info(f"[📊 CONFIANCE HTF] {htf_confidence_score:.1f}% ({sell_votes}/{total_votes} votes SELL)")
                        
                        # Vérifier confiance minimum si requis
                        if htf_confidence_score < self.config.min_confidence_to_trade:
                            logger.warning(f"[⚠️ CONFIANCE FAIBLE] {htf_confidence_score:.1f}% < {self.config.min_confidence_to_trade}% requis - Trade annulé")
                            return
                else:
                    logger.info(f"[⚠️ M1 NEUTRE] STC M1:{stc_m1:.1f} M5:{stc_m5:.1f} - Pas de tendance claire")
                    return
            
            # ========================================================================
            # MODE CLASSIQUE: HTF doit confirmer (ancien comportement)
            # ========================================================================
            elif self.config.mtf_require_alignment:
                # Mode strict: Besoin de X timeframes alignés minimum
                required_alignment = self.config.mtf_alignment_threshold
                logger.info(f"[📊 CONDITION STC] M1:{stc_m1:.1f} M5:{stc_m5:.1f} | Seuils: Buy<{self.config.stc_threshold_buy} Sell>{self.config.stc_threshold_sell}")
                
                # Tendance HAUSSIÈRE si M1/M5 haussiers ET HTF confirmés
                if stc_m1 < self.config.stc_threshold_buy or (stc_m1 < 50 and stc_m5 < 50):
                    logger.info(f"[➡️ CONDITION] HAUSSIÈRE détectée (STC M1/M5 bas)")
                    if buy_votes >= required_alignment:
                        market_trend = OrderType.BUY
                        logger.info(f"[TENDANCE HTF] ✅ HAUSSIÈRE CONFIRMÉE - M1:{stc_m1:.1f}, M5:{stc_m5:.1f} | HTF BUY:{buy_votes}/{total_votes}")
                    else:
                        logger.info(f"[TENDANCE HTF] ❌ REJET BUY - Votes insuffisants: {buy_votes}/{total_votes} (requis:{required_alignment})")
                        return
                
                # Tendance BAISSIÈRE si M1/M5 baissiers ET HTF confirmés
                elif stc_m1 > self.config.stc_threshold_sell or (stc_m1 > 50 and stc_m5 > 50):
                    logger.info(f"[➡️ CONDITION] BAISSIÈRE détectée (STC M1/M5 haut)")
                    if sell_votes >= required_alignment:
                        market_trend = OrderType.SELL
                        logger.info(f"[TENDANCE HTF] ✅ BAISSIÈRE CONFIRMÉE - M1:{stc_m1:.1f}, M5:{stc_m5:.1f} | HTF SELL:{sell_votes}/{total_votes}")
                    else:
                        logger.info(f"[TENDANCE HTF] ❌ REJET SELL - Votes insuffisants: {sell_votes}/{total_votes} (requis:{required_alignment})")
                        return
                else:
                    logger.info(f"[TENDANCE HTF] ⚠️ NEUTRE - STC M1:{stc_m1:.1f}, M5:{stc_m5:.1f} - Aucune tendance claire")
                    return
            else:
                # Mode permissif: Majorité simple suffit
                if stc_m1 < self.config.stc_threshold_buy or (stc_m1 < 50 and stc_m5 < 50):
                    # Si signal M1 TRÈS FORT (<10), on donne priorité même si HTF contredit
                    if buy_votes > sell_votes or stc_m1 < 10.0:
                        market_trend = OrderType.BUY
                        if stc_m1 < 10.0 and sell_votes > buy_votes:
                            logger.info(f"[⚡ SIGNAL EXTRÊME] STC M1={stc_m1:.1f} <10 - PRIORITÉ M1 malgré HTF SELL:{sell_votes}/BUY:{buy_votes}")
                        else:
                            logger.debug(f"[TENDANCE HTF] HAUSSIÈRE - M1:{stc_m1:.1f}, M5:{stc_m5:.1f} | HTF BUY:{buy_votes} SELL:{sell_votes}")
                    else:
                        logger.debug(f"[TENDANCE HTF] ❌ CONFLIT - M1/M5:BUY mais HTF SELL dominant (M1={stc_m1:.1f} pas assez extrême)")
                        return
                        
                elif stc_m1 > self.config.stc_threshold_sell or (stc_m1 > 50 and stc_m5 > 50):
                    # Si signal M1 TRÈS FORT (>90), on donne priorité même si HTF contredit
                    if sell_votes > buy_votes or stc_m1 > 90.0:
                        market_trend = OrderType.SELL
                        if stc_m1 > 90.0 and buy_votes > sell_votes:
                            logger.info(f"[⚡ SIGNAL EXTRÊME] STC M1={stc_m1:.1f} >90 - PRIORITÉ M1 malgré HTF BUY:{buy_votes}/SELL:{sell_votes}")
                        else:
                            logger.debug(f"[TENDANCE HTF] BAISSIÈRE - M1:{stc_m1:.1f}, M5:{stc_m5:.1f} | HTF SELL:{sell_votes} BUY:{buy_votes}")
                    else:
                        logger.debug(f"[TENDANCE HTF] ❌ CONFLIT - M1/M5:SELL mais HTF BUY dominant (M1={stc_m1:.1f} pas assez extrême)")
                        return
                else:
                    logger.debug(f"[TENDANCE HTF] NEUTRE - STC M1:{stc_m1:.1f}, M5:{stc_m5:.1f}")
                    return
        else:
            # Mode sans filtrage HTF (comportement original)
            # Tendance HAUSSIÈRE (BUY): STC en zone basse (survente) ou en remontée
            if stc_m1 < self.config.stc_threshold_buy or (stc_m1 < 50 and stc_m5 < 50):
                market_trend = OrderType.BUY
                logger.debug(f"[TENDANCE STC] HAUSSIÈRE - STC M1: {stc_m1:.1f}, M5: {stc_m5:.1f}")
            
            # Tendance BAISSIÈRE (SELL): STC en zone haute (surachat) ou en descente
            elif stc_m1 > self.config.stc_threshold_sell or (stc_m1 > 50 and stc_m5 > 50):
                market_trend = OrderType.SELL
                logger.debug(f"[TENDANCE STC] BAISSIÈRE - STC M1: {stc_m1:.1f}, M5: {stc_m5:.1f}")
            
            else:
                # Tendance NEUTRE - pas de trade
                logger.debug(f"[TENDANCE STC] NEUTRE - STC M1: {stc_m1:.1f}, M5: {stc_m5:.1f} - Pas de trade")
                return
        
        self._last_indicator_snapshot["htf_confidence"] = htf_confidence_score

        # ==============================================================
        # ÉTAPE 2: ICHIMOKU DÉCLENCHE LES ENTRÉES (CROISEMENT)
        # ==============================================================
        
        # VÉRIFICATION RISK MANAGER avant d'analyser Ichimoku
        open_positions = self.position_manager.get_all_positions()
        can_trade, risk_reason = self.risk_manager.check_can_trade(market_trend, open_positions)
        
        if not can_trade:
            logger.warning(f"[RISK MANAGER] Trading bloqué: {risk_reason}")
            return
        
        # DEBUG: Confirmer qu'on arrive ici
        logger.info(f"[🔍 DEBUG] Début calcul Ichimoku M1 - Tendance: {market_trend}")
        
        # Calculer Ichimoku M1
        tenkan_m1, kijun_m1, senkou_a_m1, senkou_b_m1 = self.indicators.calculate_ichimoku(strategy_tf)
        self._last_indicator_snapshot.update(
            {
                "stc_m1": stc_primary,
                "stc_m5": stc_confirmation if stc_confirmation is not None else stc_primary,
                "strategy_tf": strategy_tf,
                "tenkan": tenkan_m1,
                "kijun": kijun_m1,
            }
        )
        
        if None in [tenkan_m1, kijun_m1]:
            # Diagnostic: afficher pourquoi Ichimoku échoue
            history_len = len(self.indicators.price_history_m1) if strategy_tf == 'M1' else len(self.indicators.price_history_m5)
            required_len = self.config.ichimoku_senkou_span_b
            logger.warning(
                f"[ICHIMOKU] Données insuffisantes - Historique {strategy_tf}: {history_len}/{required_len} bougies "
                f"(Tenkan:{tenkan_m1}, Kijun:{kijun_m1})"
            )
            return  # Pas assez de données Ichimoku
        
        # Détecter CROISEMENT Tenkan/Kijun
        # On compare les 2 dernières valeurs pour détecter un croisement récent
        candles_prev = self._get_candles_for_strategy(tick_buffer, 101)  # 1 bougie de plus
        if len(candles_prev) < 61:
            return
        
        # Recalculer Ichimoku pour la bougie précédente
        if strategy_tf == 'M1':
            self.indicators.update_from_m1_candles(candles_prev[:-1])  # Exclure la dernière
        elif strategy_tf == 'M5':
            self.indicators.update_from_m5_candles(candles_prev[:-1])
        
        tenkan_prev, kijun_prev, _, _ = self.indicators.calculate_ichimoku(strategy_tf)
        
        # Restaurer l'indicateur avec les données actuelles
        if strategy_tf == 'M1':
            self.indicators.update_from_m1_candles(candles)
        elif strategy_tf == 'M5':
            self.indicators.update_from_m5_candles(candles)
        
        if None in [tenkan_prev, kijun_prev]:
            return
        
        # CROISEMENT HAUSSIER: Tenkan croise Kijun vers le haut
        ichimoku_crossover_bullish = (tenkan_prev <= kijun_prev) and (tenkan_m1 > kijun_m1)
        
        # CROISEMENT BAISSIER: Tenkan croise Kijun vers le bas
        ichimoku_crossover_bearish = (tenkan_prev >= kijun_prev) and (tenkan_m1 < kijun_m1)
        
        # Log diagnostic du croisement
        logger.info(f"[🔍 ICHIMOKU] Prev: T={tenkan_prev:.2f} K={kijun_prev:.2f} | Actuel: T={tenkan_m1:.2f} K={kijun_m1:.2f}")
        logger.info(f"[🔍 CROISEMENT] Haussier={ichimoku_crossover_bullish} | Baissier={ichimoku_crossover_bearish} | Tendance={market_trend}")
        
        # ==============================================================
        # ÉTAPE 3: SWEEP - ENTRÉE SI CROISEMENT DANS LA TENDANCE
        # ==============================================================
        
        current_price = candles[-1].close
        self._last_indicator_snapshot["current_price"] = current_price
        signal_triggered = False
        
        # Vérifier si on a un signal STC EXTRÊME qui pourrait bypasser le croisement
        extreme_stc_buy = stc_m1 < self.config.extreme_stc_threshold if hasattr(self.config, 'extreme_stc_threshold') else stc_m1 < 5.0
        extreme_stc_sell = stc_m1 > (100 - (self.config.extreme_stc_threshold if hasattr(self.config, 'extreme_stc_threshold') else 5.0))
        allow_no_crossover = getattr(self.config, 'allow_no_crossover_on_extreme_stc', True)
        
        # SWEEP HAUSSIER: Tendance BUY + Croisement haussier Ichimoku (OU STC extrême)
        if market_trend == OrderType.BUY and (ichimoku_crossover_bullish or (allow_no_crossover and extreme_stc_buy and tenkan_m1 > kijun_m1)):
            logger.info("=" * 80)
            if ichimoku_crossover_bullish:
                logger.info(f"[🟢 SWEEP HAUSSIER] STC: {stc_m1:.1f} (tendance BUY) + Ichimoku: Tenkan croise Kijun ↗️")
            else:
                logger.info(f"[🟢 SWEEP HAUSSIER - STC EXTRÊME] STC: {stc_m1:.1f} <{self.config.extreme_stc_threshold if hasattr(self.config, 'extreme_stc_threshold') else 5.0} + Ichimoku: Tenkan > Kijun")
            logger.info(f"[🟢 SWEEP HAUSSIER] Tenkan: {tenkan_m1:.2f} > Kijun: {kijun_m1:.2f}")
            logger.info(f"[🟢 SWEEP HAUSSIER] Prix: {current_price:.2f} - ENTRÉE LONG")
            
            # Afficher confiance HTF si activée
            if getattr(self.config, 'htf_confidence_enabled', False) and getattr(self.config, 'tick_priority_mode', False):
                logger.info(f"[🎯 CONFIANCE HTF] {htf_confidence_score:.1f}% - Ajustement TP/SL dynamique")
            
            logger.info("=" * 80)
            
            self.signals_generated += 1
            self.last_signal_time = datetime.now()
            
            # 🌊 SWEEP MODE: Détecter début de sweep et placer ordres progressivement
            if self.sweep_manager.detect_sweep_start(current_price, OrderType.BUY, stc_m1, stc_m5, htf_confidence_score):
                logger.info("[🌊 SWEEP] Sweep HAUSSIER initié - Ordres seront placés progressivement")
            
            signal_triggered = True
        
        # SWEEP BAISSIER: Tendance SELL + Croisement baissier Ichimoku (OU STC extrême)
        elif market_trend == OrderType.SELL and (ichimoku_crossover_bearish or (allow_no_crossover and extreme_stc_sell and tenkan_m1 < kijun_m1)):
            logger.info("=" * 80)
            if ichimoku_crossover_bearish:
                logger.info(f"[🔴 SWEEP BAISSIER] STC: {stc_m1:.1f} (tendance SELL) + Ichimoku: Tenkan croise Kijun ↘️")
            else:
                logger.info(f"[🔴 SWEEP BAISSIER - STC EXTRÊME] STC: {stc_m1:.1f} >{100 - (self.config.extreme_stc_threshold if hasattr(self.config, 'extreme_stc_threshold') else 5.0)} + Ichimoku: Tenkan < Kijun")
            logger.info(f"[🔴 SWEEP BAISSIER] Tenkan: {tenkan_m1:.2f} < Kijun: {kijun_m1:.2f}")
            logger.info(f"[🔴 SWEEP BAISSIER] Prix: {current_price:.2f} - ENTRÉE SHORT")
            
            # Afficher confiance HTF si activée
            if getattr(self.config, 'htf_confidence_enabled', False) and getattr(self.config, 'tick_priority_mode', False):
                logger.info(f"[🎯 CONFIANCE HTF] {htf_confidence_score:.1f}% - Ajustement TP/SL dynamique")
            
            logger.info("=" * 80)
            
            self.signals_generated += 1
            self.last_signal_time = datetime.now()
            
            # 🌊 SWEEP MODE: Détecter début de sweep et placer ordres progressivement
            if self.sweep_manager.detect_sweep_start(current_price, OrderType.SELL, stc_m1, stc_m5, htf_confidence_score):
                logger.info("[🌊 SWEEP] Sweep BAISSIER initié - Ordres seront placés progressivement")
            
            signal_triggered = True
        
        # 🌊 SWEEP UPDATE: Mettre à jour le sweep et placer ordres si niveaux atteints
        self.sweep_manager.update(current_price, stc_m1)
        should_place, level = self.sweep_manager.should_place_order(current_price)
        
        if should_place and level:
            # Placer l'ordre du niveau atteint
            if self.sweep_manager.active_sweep.direction == OrderType.BUY:
                logger.info(f"[🌊 SWEEP ORDER] Placement LONG @ {current_price:.2f} | Volume:{level.volume} | Phase:{level.wave_phase.value}")
                self._execute_long_sweep(current_price, level, htf_confidence_score)
            else:
                logger.info(f"[🌊 SWEEP ORDER] Placement SHORT @ {current_price:.2f} | Volume:{level.volume} | Phase:{level.wave_phase.value}")
                self._execute_short_sweep(current_price, level, htf_confidence_score)
        
        # MODE HFT: Mettre à jour le timestamp du dernier trade
        if signal_triggered:
            self.last_trade_time = datetime.now()
    
    def _execute_long(self, price: float, htf_confidence: float = 0.0) -> None:
        """Exécute un ordre d'achat
        
        Args:
            price: Prix d'entrée
            htf_confidence: Score de confiance HTF (0-100%) pour ajustement dynamique TP/SL
        """
        
        # Récupérer les multiplicateurs depuis la GUI (si disponible)
        sl_mult_gui = self.gui.get_sl_multiplier() if self.gui and hasattr(self.gui, 'get_sl_multiplier') else 1.0
        tp_mult_gui = self.gui.get_tp_multiplier() if self.gui and hasattr(self.gui, 'get_tp_multiplier') else 1.0
        vol_mult_gui = self.gui.get_volume_multiplier() if self.gui and hasattr(self.gui, 'get_volume_multiplier') else 1.0

        recommendation = self._get_ml_recommendation(OrderType.BUY)
        if recommendation and recommendation.avoid_trade:
            logger.info(
                f"[ML] Recommandation d'éviter le LONG (confidence={recommendation.confidence:.2f})"
            )
            return

        risk_multiplier = recommendation.risk_multiplier if recommendation else 1.0
        sl_multiplier_ml = recommendation.sl_multiplier if recommendation else 1.0
        tp_multiplier_ml = recommendation.tp_multiplier if recommendation else 1.0
        
        # ========================================================================
        # AJUSTEMENT DYNAMIQUE TP/SL SELON CONFIANCE HTF
        # ========================================================================
        sl_multiplier_htf = 1.0
        tp_multiplier_htf = 1.0
        
        if getattr(self.config, 'htf_confidence_enabled', False) and getattr(self.config, 'tick_priority_mode', False):
            tp_multiplier_htf, sl_multiplier_htf = self._get_dynamic_tp_sl_multipliers(htf_confidence)
            
            if htf_confidence >= self.config.confidence_high_min:
                confidence_level = "HAUTE"
            elif htf_confidence >= self.config.confidence_medium_min:
                confidence_level = "MOYENNE"
            else:
                confidence_level = "FAIBLE"
            
            logger.info(f"[🎯 AJUSTEMENT HTF] Confiance {confidence_level} ({htf_confidence:.1f}%) → TP×{tp_multiplier_htf:.2f} SL×{sl_multiplier_htf:.2f}")
        
        # Combiner tous les multiplicateurs
        sl_multiplier_total = sl_mult_gui * sl_multiplier_ml * sl_multiplier_htf
        tp_multiplier_total = tp_mult_gui * tp_multiplier_ml * tp_multiplier_htf
        volume_multiplier_total = vol_mult_gui * risk_multiplier

        # Calculer volatilité ATR pour volume dynamique
        volatility = None
        ml_confidence = recommendation.confidence if recommendation else None
        
        if self.config.volume_dynamic_enabled and self.last_market_context:
            # Utiliser getattr pour éviter AttributeError si volatility n'existe pas
            volatility = getattr(self.last_market_context, 'volatility', None)
        
        # Obtenir le volume avec ajustements dynamiques
        volume = self.position_manager.get_next_position_size(
            volume_mult=volume_multiplier_total,
            volatility=volatility,
            ml_confidence=ml_confidence
        )
        
        sl, tp = self.position_manager.get_next_sl_tp(
            price,
            OrderType.BUY,
            self.position_manager.current_portfolio_value,
            sl_mult=sl_multiplier_total,
            tp_mult=tp_multiplier_total,
        )

        metadata = self._build_trade_metadata(OrderType.BUY, recommendation)
        metadata.update(
            {
                "sl_multiplier_total": sl_multiplier_total,
                "tp_multiplier_total": tp_multiplier_total,
                "volume_multiplier_total": volume_multiplier_total,
                "htf_confidence": htf_confidence,
                "trade_type": "CORE",
            }
        )

        if recommendation:
            logger.info(
                (
                    "[ML] LONG: risk x{risk:.2f}, sl x{slm:.2f}, tp x{tpm:.2f}, secure={secure:.1f}$,"
                    " extension={extension:.1f}$, trailing={trail:.1f}$, confidence={conf:.2f}"
                ).format(
                    risk=recommendation.risk_multiplier,
                    slm=recommendation.sl_multiplier,
                    tpm=recommendation.tp_multiplier,
                    secure=recommendation.secure_profit,
                    extension=recommendation.extension_trigger,
                    trail=recommendation.trailing_distance,
                    conf=recommendation.confidence,
                )
            )

        # Calcul du Risk:Reward
        risk = abs(price - sl)
        reward = abs(tp - price)
        rr_ratio = reward / risk if risk > 0 else 0

        metadata.update(
            {
                "rr_ratio": rr_ratio,
                "entry_price": price,
                "stop_loss": sl,
                "take_profit": tp,
            }
        )

        logger.info(
            (
                "[SETUP LONG] Prix={price:.2f}, Vol={vol:.3f} (x{volmult:.2f}), SL={sl:.2f} (x{slm:.2f}),"
                " TP={tp:.2f} (x{tpm:.2f}), R:R={rr:.2f}"
            ).format(
                price=price,
                vol=volume,
                volmult=volume_multiplier_total,
                sl=sl,
                slm=sl_multiplier_total,
                tp=tp,
                tpm=tp_multiplier_total,
                rr=rr_ratio,
            )
        )

        success, ticket = self.position_manager.open_position(
            OrderType.BUY,
            price,
            volume,
            sl,
            tp,
            comment="HFT_LONG",
            metadata=metadata,
        )

        if success:
            self.orders_sent += 1
            self.last_trade_time = datetime.now()
            self.risk_manager.record_trade_opened(OrderType.BUY)  # Enregistrer dans Risk Manager
            if recommendation:
                self.active_recommendations[ticket] = recommendation
            self._register_trade_open(
                ticket,
                OrderType.BUY,
                price,
                volume,
                sl,
                tp,
                htf_confidence,
                dict(metadata),
                recommendation,
                rr_ratio,
            )
            logger.info(f"✅ ORDRE LONG EXÉCUTÉ - Ticket #{ticket}")
        else:
            self.orders_rejected += 1
            logger.error("❌ ORDRE LONG REJETÉ")
    
    def _execute_short(self, price: float, htf_confidence: float = 0.0) -> None:
        """Exécute un ordre de vente
        
        Args:
            price: Prix d'entrée
            htf_confidence: Score de confiance HTF (0-100%) pour ajustement dynamique TP/SL
        """
        sl_mult_gui = self.gui.get_sl_multiplier() if self.gui and hasattr(self.gui, 'get_sl_multiplier') else 1.0
        tp_mult_gui = self.gui.get_tp_multiplier() if self.gui and hasattr(self.gui, 'get_tp_multiplier') else 1.0
        vol_mult_gui = self.gui.get_volume_multiplier() if self.gui and hasattr(self.gui, 'get_volume_multiplier') else 1.0

        recommendation = self._get_ml_recommendation(OrderType.SELL)
        if recommendation and recommendation.avoid_trade:
            logger.info(
                f"[ML] Recommandation d'éviter le SHORT (confidence={recommendation.confidence:.2f})"
            )
            return

        risk_multiplier = recommendation.risk_multiplier if recommendation else 1.0
        sl_multiplier_ml = recommendation.sl_multiplier if recommendation else 1.0
        tp_multiplier_ml = recommendation.tp_multiplier if recommendation else 1.0
        
        # ========================================================================
        # AJUSTEMENT DYNAMIQUE TP/SL SELON CONFIANCE HTF
        # ========================================================================
        sl_multiplier_htf = 1.0
        tp_multiplier_htf = 1.0
        
        if getattr(self.config, 'htf_confidence_enabled', False) and getattr(self.config, 'tick_priority_mode', False):
            tp_multiplier_htf, sl_multiplier_htf = self._get_dynamic_tp_sl_multipliers(htf_confidence)
            
            if htf_confidence >= self.config.confidence_high_min:
                confidence_level = "HAUTE"
            elif htf_confidence >= self.config.confidence_medium_min:
                confidence_level = "MOYENNE"
            else:
                confidence_level = "FAIBLE"
            
            logger.info(f"[🎯 AJUSTEMENT HTF] Confiance {confidence_level} ({htf_confidence:.1f}%) → TP×{tp_multiplier_htf:.2f} SL×{sl_multiplier_htf:.2f}")
        
        # Combiner tous les multiplicateurs
        sl_multiplier_total = sl_mult_gui * sl_multiplier_ml * sl_multiplier_htf
        tp_multiplier_total = tp_mult_gui * tp_multiplier_ml * tp_multiplier_htf
        volume_multiplier_total = vol_mult_gui * risk_multiplier

        # Calculer volatilité ATR pour volume dynamique
        volatility = None
        ml_confidence = recommendation.confidence if recommendation else None
        
        if self.config.volume_dynamic_enabled and self.last_market_context:
            # Utiliser getattr pour éviter AttributeError si volatility n'existe pas
            volatility = getattr(self.last_market_context, 'volatility', None)
        
        # Obtenir le volume avec ajustements dynamiques
        volume = self.position_manager.get_next_position_size(
            volume_mult=volume_multiplier_total,
            volatility=volatility,
            ml_confidence=ml_confidence
        )
        
        sl, tp = self.position_manager.get_next_sl_tp(
            price,
            OrderType.SELL,
            self.position_manager.current_portfolio_value,
            sl_mult=sl_multiplier_total,
            tp_mult=tp_multiplier_total,
        )

        metadata = self._build_trade_metadata(OrderType.SELL, recommendation)
        metadata.update(
            {
                "sl_multiplier_total": sl_multiplier_total,
                "tp_multiplier_total": tp_multiplier_total,
                "volume_multiplier_total": volume_multiplier_total,
                "htf_confidence": htf_confidence,
                "trade_type": "CORE",
            }
        )

        if recommendation:
            logger.info(
                (
                    "[ML] SHORT: risk x{risk:.2f}, sl x{slm:.2f}, tp x{tpm:.2f}, secure={secure:.1f}$,"
                    " extension={extension:.1f}$, trailing={trail:.1f}$, confidence={conf:.2f}"
                ).format(
                    risk=recommendation.risk_multiplier,
                    slm=recommendation.sl_multiplier,
                    tpm=recommendation.tp_multiplier,
                    secure=recommendation.secure_profit,
                    extension=recommendation.extension_trigger,
                    trail=recommendation.trailing_distance,
                    conf=recommendation.confidence,
                )
            )

        risk = abs(sl - price)
        reward = abs(price - tp)
        rr_ratio = reward / risk if risk > 0 else 0

        metadata.update(
            {
                "rr_ratio": rr_ratio,
                "entry_price": price,
                "stop_loss": sl,
                "take_profit": tp,
            }
        )

        logger.info(
            (
                "[SETUP SHORT] Prix={price:.2f}, Vol={vol:.3f} (x{volmult:.2f}), SL={sl:.2f} (x{slm:.2f}),"
                " TP={tp:.2f} (x{tpm:.2f}), R:R={rr:.2f}"
            ).format(
                price=price,
                vol=volume,
                volmult=volume_multiplier_total,
                sl=sl,
                slm=sl_multiplier_total,
                tp=tp,
                tpm=tp_multiplier_total,
                rr=rr_ratio,
            )
        )

        success, ticket = self.position_manager.open_position(
            OrderType.SELL,
            price,
            volume,
            sl,
            tp,
            comment="HFT_SHORT",
            metadata=metadata,
        )

        if success:
            self.orders_sent += 1
            self.last_trade_time = datetime.now()
            self.risk_manager.record_trade_opened(OrderType.SELL)  # Enregistrer dans Risk Manager
            if recommendation:
                self.active_recommendations[ticket] = recommendation
            self._register_trade_open(
                ticket,
                OrderType.SELL,
                price,
                volume,
                sl,
                tp,
                htf_confidence,
                dict(metadata),
                recommendation,
                rr_ratio,
            )
            logger.info(f"✅ ORDRE SHORT EXÉCUTÉ - Ticket #{ticket}")
        else:
            self.orders_rejected += 1
            logger.error("❌ ORDRE SHORT REJETÉ")
    
    def get_statistics(self) -> dict:
        """Retourne les statistiques de la stratégie"""
        return {
            'is_running': self.is_running,
            'signals_generated': self.signals_generated,
            'orders_sent': self.orders_sent,
            'orders_rejected': self.orders_rejected,
            'open_positions': self.position_manager.get_open_positions_count(),
            'total_trades': len(self.position_manager.get_trades_history()),
            'ticks_received': self.tick_feed.get_tick_count(),
            'last_tick_time': self.tick_feed.last_tick_time,
            'last_signal_time': self.last_signal_time,
            'last_analysis_duration_ms': self.last_analysis_duration * 1000,
        }
    
    def _get_htf_trend_rust(self, timeframe: str) -> Optional[OrderType]:
        """
        Détermine la tendance sur un timeframe supérieur (M15/M30/H1/H4) via STC
        Utilise le module Rust pour performances optimales (10-20x plus rapide)
        
        Returns:
            OrderType.BUY si tendance haussière
            OrderType.SELL si tendance baissière
            None si neutre
        """
        try:
            # Mapper timeframe vers MT5
            tf_map = {
                'M15': mt5.TIMEFRAME_M15,
                'M30': mt5.TIMEFRAME_M30,
                'H1': mt5.TIMEFRAME_H1,
                'H4': mt5.TIMEFRAME_H4,
            }
            
            mt5_tf = tf_map.get(timeframe)
            if not mt5_tf:
                logger.warning(f"Timeframe {timeframe} non supporté")
                return None
            
            # Récupérer les bougies depuis MT5
            rates = mt5.copy_rates_from_pos(self.config.symbol, mt5_tf, 0, 100)
            if rates is None or len(rates) < 60:
                logger.debug(f"Pas assez de données pour {timeframe}")
                return None
            
            # Extraire les prix de clôture
            closes = [float(r['close']) for r in rates]
            
            # === UTILISER RUST POUR CALCUL STC (10-20x plus rapide) ===
            try:
                import hft_rust_core
                
                # Vérifier que STCCalculator existe
                if not hasattr(hft_rust_core, 'STCCalculator'):
                    raise AttributeError("STCCalculator non disponible - Module Rust à recompiler")
                
                # Créer calculateur STC Rust
                stc_calculator = hft_rust_core.STCCalculator()
                
                # Calculer STC avec Rust (ultra-rapide, <1ms vs 10-20ms Python)
                stc_values = stc_calculator.calculate(
                    closes,
                    self.config.stc_period,
                    self.config.stc_fast_length,
                    self.config.stc_slow_length
                )
                
                if not stc_values or len(stc_values) == 0:
                    return None
                
                # Prendre la dernière valeur
                stc_value = stc_values[-1]
                
                # Log pour debug (désactiver en production)
                # logger.debug(f"[RUST STC] {timeframe}: {stc_value:.2f}")
                
                # Utiliser les seuils configurés avec marge élargie pour HTF
                # HTF utilise des seuils moins stricts que M1 (plus permissifs)
                buy_threshold = self.config.stc_threshold_buy + 15.0
                sell_threshold = self.config.stc_threshold_sell - 15.0
                
                # Déterminer la tendance
                if stc_value < buy_threshold:
                    return OrderType.BUY
                elif stc_value > sell_threshold:
                    return OrderType.SELL
                else:
                    # Zone neutre réduite - Regarder tendance générale
                    if stc_value < 50:
                        return OrderType.BUY  # Légèrement haussier
                    elif stc_value > 50:
                        return OrderType.SELL  # Légèrement baissier
                    else:
                        return None  # Exactement 50 = neutre
                    
            except (ImportError, AttributeError) as e:
                # Fallback Python si Rust indisponible ou incomplet
                if not hasattr(self, '_rust_warning_shown'):
                    logger.warning(f"[FALLBACK PYTHON] Module Rust incomplet ({e}) - Utilisation Python (10-25x plus lent)")
                    logger.warning(f"[FALLBACK PYTHON] Pour activer Rust: cd hft_rust_core && maturin develop --release")
                    self._rust_warning_shown = True
                
                # Utiliser la méthode Python existante
                temp_history = deque(maxlen=100)
                for close in closes:
                    temp_history.append(close)
                
                # Sauvegarder l'état actuel
                original_m1 = self.indicators.price_history_m1.copy()
                
                # Temporairement remplacer par HTF
                self.indicators.price_history_m1 = temp_history
                stc_value = self.indicators.calculate_stc('M1')
                
                # Restaurer l'état original
                self.indicators.price_history_m1 = original_m1
                
                if stc_value is None:
                    return None
                
                # Utiliser les seuils configurés avec marge élargie pour HTF
                buy_threshold = self.config.stc_threshold_buy + 15.0
                sell_threshold = self.config.stc_threshold_sell - 15.0
                
                # Déterminer la tendance
                if stc_value < buy_threshold:
                    return OrderType.BUY
                elif stc_value > sell_threshold:
                    return OrderType.SELL
                else:
                    # Zone neutre - Regarder tendance générale
                    if stc_value < 50:
                        return OrderType.BUY
                    elif stc_value > 50:
                        return OrderType.SELL
                    else:
                        return None
            
            except Exception as rust_err:
                # Log seulement la première erreur pour éviter le spam
                if not hasattr(self, '_rust_error_logged'):
                    logger.error(f"[RUST ERROR] Erreur calcul STC: {rust_err}")
                    self._rust_error_logged = True
                return None
                
        except Exception as e:
            logger.error(f"Erreur calcul tendance {timeframe}: {e}")
            return None
    
    def _execute_long_sweep(self, price: float, level, htf_confidence: float = 0.0) -> None:
        """
        Exécute un ordre LONG dans le cadre d'un sweep
        Utilise le volume prédéfini du SweepLevel (martingale progressive)
        
        Args:
            price: Prix d'entrée
            level: SweepLevel contenant volume et phase Elliott
            htf_confidence: Score de confiance HTF (0-100%)
        """
        sl_mult_gui = self.gui.get_sl_multiplier() if self.gui and hasattr(self.gui, 'get_sl_multiplier') else 1.0
        tp_mult_gui = self.gui.get_tp_multiplier() if self.gui and hasattr(self.gui, 'get_tp_multiplier') else 1.0
        
        recommendation = self._get_ml_recommendation(OrderType.BUY)
        sl_multiplier_ml = recommendation.sl_multiplier if recommendation else 1.0
        tp_multiplier_ml = recommendation.tp_multiplier if recommendation else 1.0
        
        # Ajustement HTF
        sl_multiplier_htf = 1.0
        tp_multiplier_htf = 1.0
        if getattr(self.config, 'htf_confidence_enabled', False):
            tp_multiplier_htf, sl_multiplier_htf = self._get_dynamic_tp_sl_multipliers(htf_confidence)
        
        sl_multiplier_total = sl_mult_gui * sl_multiplier_ml * sl_multiplier_htf
        tp_multiplier_total = tp_mult_gui * tp_multiplier_ml * tp_multiplier_htf
        
        # 🌊 SWEEP: Utiliser le volume du niveau (martingale calculé)
        volume = level.volume
        
        # ✅ OPTIMISATION 4: TP/SL adaptatif selon amplitude du sweep
        tp_adaptive, sl_adaptive = self.sweep_manager.get_adaptive_tp_sl(price)
        
        # Calculer TP/SL finaux
        sl = price - (sl_adaptive * sl_multiplier_total)
        tp = price + (tp_adaptive * tp_multiplier_total)
        
        metadata = self._build_trade_metadata(OrderType.BUY, recommendation)
        metadata.update({
            "sweep_phase": level.wave_phase.value,
            "sweep_level_price": level.price,
            "adaptive_tp": tp_adaptive,
            "adaptive_sl": sl_adaptive,
            "sl_multiplier_total": sl_multiplier_total,
            "tp_multiplier_total": tp_multiplier_total,
            "htf_confidence": htf_confidence,
            "order_number": level.order_number,
            "trade_type": "SWEEP",
            "entry_price": price,
            "stop_loss": sl,
            "take_profit": tp,
            "sweep_speed": self.sweep_manager.active_sweep.sweep_speed.value if self.sweep_manager.active_sweep else None,
            "volume_multiplier_total": None,
        })
        
        # Calculer Risk:Reward
        risk = abs(price - sl)
        reward = abs(tp - price)
        rr_ratio = reward / risk if risk > 0 else 0
        
        logger.info(f"[🌊 SWEEP LONG] Vol={volume:.3f} | SL={sl:.2f} (-{sl_adaptive:.2f}$×{sl_multiplier_total:.2f}) | TP={tp:.2f} (+{tp_adaptive:.2f}$×{tp_multiplier_total:.2f}) | R:R={rr_ratio:.2f} | Phase={level.wave_phase.value}")
        
        success, ticket = self.position_manager.open_position(
            OrderType.BUY,
            price,
            volume,
            sl,
            tp,
            comment=f"SWEEP_LONG_{level.wave_phase.value}",
            metadata=metadata,
        )
        
        if success:
            self.orders_sent += 1
            self.last_trade_time = datetime.now()
            self.risk_manager.record_trade_opened(OrderType.BUY)
            sweep_info = {
                "order_number": level.order_number,
                "phase": level.wave_phase.value,
                "sweep_speed": self.sweep_manager.active_sweep.sweep_speed.value if self.sweep_manager.active_sweep else None,
            }
            self._register_trade_open(
                ticket,
                OrderType.BUY,
                price,
                volume,
                sl,
                tp,
                htf_confidence,
                dict(metadata),
                recommendation,
                rr_ratio,
                sweep_info=sweep_info,
            )
            self.sweep_manager.mark_level_executed(level, ticket)
            logger.info(f"✅ SWEEP LONG EXÉCUTÉ - Ticket #{ticket} | Phase:{level.wave_phase.value}")
        else:
            self.orders_rejected += 1
            logger.error(f"❌ SWEEP LONG REJETÉ - Phase:{level.wave_phase.value}")
    
    def _execute_short_sweep(self, price: float, level, htf_confidence: float = 0.0) -> None:
        """
        Exécute un ordre SHORT dans le cadre d'un sweep
        Utilise le volume prédéfini du SweepLevel (martingale progressive)
        
        Args:
            price: Prix d'entrée
            level: SweepLevel contenant volume et phase Elliott
            htf_confidence: Score de confiance HTF (0-100%)
        """
        sl_mult_gui = self.gui.get_sl_multiplier() if self.gui and hasattr(self.gui, 'get_sl_multiplier') else 1.0
        tp_mult_gui = self.gui.get_tp_multiplier() if self.gui and hasattr(self.gui, 'get_tp_multiplier') else 1.0
        
        recommendation = self._get_ml_recommendation(OrderType.SELL)
        sl_multiplier_ml = recommendation.sl_multiplier if recommendation else 1.0
        tp_multiplier_ml = recommendation.tp_multiplier if recommendation else 1.0
        
        # Ajustement HTF
        sl_multiplier_htf = 1.0
        tp_multiplier_htf = 1.0
        if getattr(self.config, 'htf_confidence_enabled', False):
            tp_multiplier_htf, sl_multiplier_htf = self._get_dynamic_tp_sl_multipliers(htf_confidence)
        
        sl_multiplier_total = sl_mult_gui * sl_multiplier_ml * sl_multiplier_htf
        tp_multiplier_total = tp_mult_gui * tp_multiplier_ml * tp_multiplier_htf
        
        # 🌊 SWEEP: Utiliser le volume du niveau (martingale calculé)
        volume = level.volume
        
        # ✅ OPTIMISATION 4: TP/SL adaptatif selon amplitude du sweep
        tp_adaptive, sl_adaptive = self.sweep_manager.get_adaptive_tp_sl(price)
        
        # Calculer TP/SL finaux
        sl = price + (sl_adaptive * sl_multiplier_total)
        tp = price - (tp_adaptive * tp_multiplier_total)
        
        metadata = self._build_trade_metadata(OrderType.SELL, recommendation)
        metadata.update({
            "sweep_phase": level.wave_phase.value,
            "sweep_level_price": level.price,
            "adaptive_tp": tp_adaptive,
            "adaptive_sl": sl_adaptive,
            "sl_multiplier_total": sl_multiplier_total,
            "tp_multiplier_total": tp_multiplier_total,
            "htf_confidence": htf_confidence,
            "order_number": level.order_number,
            "trade_type": "SWEEP",
            "entry_price": price,
            "stop_loss": sl,
            "take_profit": tp,
            "sweep_speed": self.sweep_manager.active_sweep.sweep_speed.value if self.sweep_manager.active_sweep else None,
            "volume_multiplier_total": None,
        })
        
        # Calculer Risk:Reward
        risk = abs(sl - price)
        reward = abs(price - tp)
        rr_ratio = reward / risk if risk > 0 else 0
        
        logger.info(f"[🌊 SWEEP SHORT] Vol={volume:.3f} | SL={sl:.2f} (+{sl_adaptive:.2f}$×{sl_multiplier_total:.2f}) | TP={tp:.2f} (-{tp_adaptive:.2f}$×{tp_multiplier_total:.2f}) | R:R={rr_ratio:.2f} | Phase={level.wave_phase.value}")
        
        success, ticket = self.position_manager.open_position(
            OrderType.SELL,
            price,
            volume,
            sl,
            tp,
            comment=f"SWEEP_SHORT_{level.wave_phase.value}",
            metadata=metadata,
        )
        
        if success:
            self.orders_sent += 1
            self.last_trade_time = datetime.now()
            self.risk_manager.record_trade_opened(OrderType.SELL)
            sweep_info = {
                "order_number": level.order_number,
                "phase": level.wave_phase.value,
                "sweep_speed": self.sweep_manager.active_sweep.sweep_speed.value if self.sweep_manager.active_sweep else None,
            }
            self._register_trade_open(
                ticket,
                OrderType.SELL,
                price,
                volume,
                sl,
                tp,
                htf_confidence,
                dict(metadata),
                recommendation,
                rr_ratio,
                sweep_info=sweep_info,
            )
            self.sweep_manager.mark_level_executed(level, ticket)
            logger.info(f"✅ SWEEP SHORT EXÉCUTÉ - Ticket #{ticket} | Phase:{level.wave_phase.value}")
        else:
            self.orders_rejected += 1
            logger.error(f"❌ SWEEP SHORT REJETÉ - Phase:{level.wave_phase.value}")
