#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestionnaire de positions pour le trading HFT
"""

import threading
import MetaTrader5 as mt5
import time
from datetime import datetime
from typing import Dict, List, Tuple, Optional, Callable
import logging

from config.trading_config import TradingConfig, OrderType, PositionState
from models.data_models import TradeRecord

logger = logging.getLogger(__name__)


class HFTPositionManager:
    """Gestionnaire des positions optimisé pour HFT"""
    
    def __init__(self, config: TradingConfig, gui=None):
        self.config = config
        self.gui = gui  # Référence à la GUI pour accéder aux multiplicateurs
        self.positions: Dict[int, TradeRecord] = {}
        self.current_portfolio_value = config.initial_portfolio
        self.position_counter = 0
        self.lock = threading.Lock()
        self.trades_history: List[TradeRecord] = []
        self.tick_count_at_entry = 0
        self.known_tickets: set = set()
        self.close_callbacks: List[Callable[[TradeRecord], None]] = []
        self.sync_existing_positions()
        
        # Démarrer le thread de surveillance
        self.monitor_stop_event = threading.Event()
        self.monitor_thread = None
        self.start_position_monitor()
    
    def register_close_callback(self, callback: Callable[[TradeRecord], None]) -> None:
        """Permet d'exécuter des callbacks lors de la clôture des positions."""
        self.close_callbacks.append(callback)

    def _notify_trade_closed(self, trade: TradeRecord) -> None:
        for callback in list(self.close_callbacks):
            try:
                callback(trade)
            except Exception as exc:
                logger.exception("Erreur lors de l'exécution d'un callback de clôture", exc_info=exc)

    def sync_existing_positions(self) -> None:
        """Synchronise les positions existantes depuis MT5"""
        positions = mt5.positions_get(symbol=self.config.symbol)
        
        if positions is None:
            logger.info(f"Aucune position existante pour {self.config.symbol}")
            return
        
        logger.info(f"=== Synchronisation des positions pour {self.config.symbol} ===")
        bot_positions = 0
        other_positions = 0
        
        for pos in positions:
            is_bot_position = pos.magic == 234000
            
            if is_bot_position:
                trade = TradeRecord(
                    ticket=pos.ticket,
                    symbol=pos.symbol,
                    order_type=OrderType.BUY if pos.type == mt5.ORDER_TYPE_BUY else OrderType.SELL,
                    volume=pos.volume,
                    entry_price=pos.price_open,
                    entry_time=datetime.fromtimestamp(pos.time),
                    stop_loss=pos.sl,
                    take_profit=pos.tp,
                    state=PositionState.OPEN,
                    metadata={
                        "trailing_stage": 0,
                        "trailing_plan": {
                            "secure_profit": self.config.trailing_secure_base,
                            "extension_trigger": self.config.trailing_extension_base,
                            "trailing_distance": self.config.trailing_distance_base,
                        },
                    },
                )
                self.positions[pos.ticket] = trade
                bot_positions += 1
                logger.info(f"[BOT] Position #{pos.ticket}: {trade.order_type.name}, Vol={pos.volume}, "
                           f"Prix={pos.price_open:.2f}, SL={pos.sl:.2f}, TP={pos.tp:.2f}")
            else:
                other_positions += 1
                logger.info(f"[EXTERNE] Position #{pos.ticket}: Magic={pos.magic}")
        
        logger.info(f"Total: {bot_positions} position(s) du bot, {other_positions} position(s) externe(s)")
        self.known_tickets = {pos.ticket for pos in positions} if positions else set()
    
    def get_next_position_size(self, volume_mult: float = 1.0, volatility: float = None, ml_confidence: float = None) -> float:
        """
        Obtient la taille de position suivante avec multiplicateur dynamique
        
        Args:
            volume_mult: Multiplicateur de base
            volatility: Volatilité ATR actuelle (optionnel)
            ml_confidence: Confiance du ML (0-1) (optionnel)
            
        Returns:
            Volume normalisé adapté
        """
        with self.lock:
            num_positions = len(self.positions)
            if num_positions < len(self.config.position_sizes):
                base_volume = self.config.position_sizes[num_positions]
            else:
                base_volume = self.config.position_sizes[-1]
        
        # Appliquer le multiplicateur de base
        adjusted_volume = base_volume * volume_mult
        
        # === VOLUME DYNAMIQUE SELON VOLATILITÉ ET ML ===
        if self.config.volume_dynamic_enabled:
            
            # 1. Ajustement selon VOLATILITÉ (réduire si volatilité élevée)
            if volatility is not None and self.config.max_atr_threshold > 0:
                # Ratio de volatilité (0 = faible, 1 = très élevé)
                vol_ratio = min(volatility / self.config.max_atr_threshold, 1.0)
                
                # Facteur de réduction: 1.0 si vol faible, min_multiplier si vol élevée
                vol_factor = 1.0 - (vol_ratio * (1.0 - self.config.volume_min_multiplier))
                vol_factor = max(self.config.volume_min_multiplier, min(1.0, vol_factor))
                
                adjusted_volume *= vol_factor
                
                logger.debug(f"[VOLUME DYN] Volatilité ATR={volatility:.2f}$ -> Facteur={vol_factor:.2f}")
            
            # 2. Ajustement selon CONFIANCE ML (augmenter si ML très confiant)
            if ml_confidence is not None and ml_confidence > 0.8:
                # Confiance > 80% = augmenter le volume
                confidence_boost = 1.0 + ((ml_confidence - 0.8) / 0.2) * (self.config.volume_max_multiplier - 1.0)
                confidence_boost = min(self.config.volume_max_multiplier, confidence_boost)
                
                adjusted_volume *= confidence_boost
                
                logger.debug(f"[VOLUME DYN] Confiance ML={ml_confidence:.2%} -> Boost={confidence_boost:.2f}")
        
        return self.normalize_volume(adjusted_volume)
    
    def get_next_sl_tp(self, entry_price: float, order_type: OrderType, 
                       current_portfolio: float, sl_mult: float = 1.0, tp_mult: float = 1.0) -> Tuple[float, float]:
        """Calcule le SL et TP dynamiquement avec multiplicateurs et spread"""
        
        # Récupérer le spread actuel du symbole
        symbol_info = mt5.symbol_info(self.config.symbol)
        spread_in_price = 0.0
        if symbol_info:
            spread_in_price = symbol_info.spread * symbol_info.point
        
        # Appliquer les multiplicateurs
        sl_distance = self.config.base_sl_distance * sl_mult
        tp_distance = self.config.base_tp_distance * tp_mult
        
        # Ajouter le spread au TP pour garantir le profit net
        tp_distance += spread_in_price * self.config.spread_compensation_multiplier
        
        if order_type == OrderType.BUY:
            stop_loss = entry_price - sl_distance
            take_profit = entry_price + tp_distance
        else:  # SELL
            stop_loss = entry_price + sl_distance
            take_profit = entry_price - tp_distance
        
        return stop_loss, take_profit
    
    def check_margin_available(self, symbol: str, volume: float, order_type: OrderType) -> Tuple[bool, str]:
        """Vérifie si la marge est suffisante pour ouvrir une position"""
        try:
            account_info = mt5.account_info()
            if account_info is None:
                return False, "Impossible de récupérer les informations du compte"
            
            symbol_info = mt5.symbol_info(symbol)
            if symbol_info is None:
                return False, f"Symbole {symbol} non trouvé"
            
            if not symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_FULL:
                return False, f"Trading non autorisé pour {symbol}"
            
            mt5_order_type = mt5.ORDER_TYPE_BUY if order_type == OrderType.BUY else mt5.ORDER_TYPE_SELL
            margin_required = mt5.order_calc_margin(mt5_order_type, symbol, volume, symbol_info.ask if order_type == OrderType.BUY else symbol_info.bid)
            
            if margin_required is None:
                return False, "Impossible de calculer la marge requise"
            
            free_margin = account_info.margin_free
            
            if margin_required * 1.2 > free_margin:
                return False, f"Marge insuffisante: Requis={margin_required:.2f}, Disponible={free_margin:.2f}"
            
            margin_level = account_info.margin_level if account_info.margin_level else 0
            
            if margin_level > 0 and margin_level < 200:
                return False, f"Niveau de marge trop bas: {margin_level:.2f}%"
            
            logger.info(f"[MARGE OK] Requise={margin_required:.2f}, Disponible={free_margin:.2f}, Niveau={margin_level:.2f}%")
            return True, "Marge suffisante"
            
        except Exception as e:
            return False, f"Erreur lors de la vérification de la marge: {e}"
    
    def normalize_volume(self, volume: float) -> float:
        """Normalise le volume selon les contraintes du symbole MT5"""
        symbol_info = mt5.symbol_info(self.config.symbol)
        if symbol_info is None:
            logger.error(f"Impossible de normaliser le volume: symbole {self.config.symbol} non trouvé")
            return volume
        
        volume_min = symbol_info.volume_min
        volume_max = symbol_info.volume_max
        volume_step = symbol_info.volume_step
        
        normalized = round(volume / volume_step) * volume_step
        normalized = max(volume_min, min(volume_max, normalized))
        normalized = round(normalized, 2)
        
        if normalized != volume:
            logger.info(f"Volume normalisé: {volume} -> {normalized} (step={volume_step}, min={volume_min}, max={volume_max})")
        
        return normalized
    
    def open_position(
        self,
        order_type: OrderType,
        price: float,
        volume: float,
        sl: float,
        tp: float,
        comment: str = "",
        metadata: Optional[dict] = None,
    ) -> Tuple[bool, Optional[int]]:
        """Ouvre une nouvelle position avec gestion du filling mode"""
        
        # Normaliser le volume
        volume = self.normalize_volume(volume)
        
        # Vérifier la marge
        margin_ok, margin_msg = self.check_margin_available(self.config.symbol, volume, order_type)
        if not margin_ok:
            logger.error(f"[POSITION REFUSÉE] {margin_msg}")
            return False, None
        
        # Déterminer le filling mode supporté
        symbol_info = mt5.symbol_info(self.config.symbol)
        if symbol_info is None:
            logger.error(f"Symbole {self.config.symbol} non trouvé")
            return False, None
        
        # Détection du filling mode (bit flags)
        filling_mode_flags = symbol_info.filling_mode
        
        if filling_mode_flags & 1:  # Bit 0: FOK
            filling_mode = mt5.ORDER_FILLING_FOK
            filling_name = "FOK"
        elif filling_mode_flags & 2:  # Bit 1: IOC
            filling_mode = mt5.ORDER_FILLING_IOC
            filling_name = "IOC"
        elif filling_mode_flags & 4:  # Bit 2: RETURN
            filling_mode = mt5.ORDER_FILLING_RETURN
            filling_name = "RETURN"
        else:
            logger.error(f"Aucun filling mode supporté pour {self.config.symbol}")
            return False, None
        
        logger.info(f"[FILLING MODE] {filling_name} sélectionné (flags={bin(filling_mode_flags)})")
        
        # Préparer la requête
        mt5_order_type = mt5.ORDER_TYPE_BUY if order_type == OrderType.BUY else mt5.ORDER_TYPE_SELL
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.config.symbol,
            "volume": volume,
            "type": mt5_order_type,
            "price": price,
            "sl": sl,
            "tp": tp,
            "deviation": 20,
            "magic": 234000,
            "comment": comment or f"HFT_{order_type.name}",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": filling_mode,
        }
        
        logger.info(f"[ORDRE] {order_type.name} {volume} lots @ {price:.2f}, SL={sl:.2f}, TP={tp:.2f}")
        
        # Envoyer l'ordre
        result = mt5.order_send(request)
        
        if result is None:
            logger.error(f"[ERREUR] order_send a retourné None")
            return False, None
        
        if result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"[ORDRE REJETÉ] RetCode={result.retcode}, Comment={result.comment}")
            return False, None
        
        # Succès
        ticket = result.order
        logger.info(f"[POSITION OUVERTE] Ticket #{ticket}, Prix={result.price:.2f}")
        
        # Enregistrer la position
        trade_metadata = dict(metadata) if metadata else {}
        trade_metadata.setdefault("trailing_stage", 0)
        trade_metadata.setdefault(
            "trailing_plan",
            {
                "secure_profit": self.config.trailing_secure_base,
                "extension_trigger": self.config.trailing_extension_base,
                "trailing_distance": self.config.trailing_distance_base,
            },
        )

        trade = TradeRecord(
            ticket=ticket,
            symbol=self.config.symbol,
            order_type=order_type,
            volume=volume,
            entry_price=result.price,
            entry_time=datetime.now(),
            stop_loss=sl,
            take_profit=tp,
            state=PositionState.OPEN,
            metadata=trade_metadata,
        )
        
        with self.lock:
            self.positions[ticket] = trade
        
        return True, ticket
    
    def close_position(self, ticket: int, reason: str = "") -> bool:
        """Ferme une position existante"""
        
        with self.lock:
            if ticket not in self.positions:
                logger.warning(f"Position #{ticket} introuvable")
                return False
            
            trade = self.positions[ticket]
        
        # Vérifier que la position existe encore dans MT5
        position = mt5.positions_get(ticket=ticket)
        if not position or len(position) == 0:
            logger.warning(f"Position #{ticket} déjà fermée dans MT5")
            with self.lock:
                trade.state = PositionState.CLOSED
                trade.exit_time = datetime.now()
                trade.metadata.setdefault("close_reason", reason or "external")
                self.trades_history.append(trade)
                del self.positions[ticket]
            self._notify_trade_closed(trade)
            return True
        
        pos = position[0]
        
        # Ordre de fermeture inverse
        close_type = mt5.ORDER_TYPE_SELL if pos.type == mt5.ORDER_TYPE_BUY else mt5.ORDER_TYPE_BUY
        price = mt5.symbol_info_tick(self.config.symbol).bid if close_type == mt5.ORDER_TYPE_SELL else mt5.symbol_info_tick(self.config.symbol).ask
        
        request = {
            "action": mt5.TRADE_ACTION_DEAL,
            "symbol": self.config.symbol,
            "volume": pos.volume,
            "type": close_type,
            "position": ticket,
            "price": price,
            "deviation": 20,
            "magic": 234000,
            "comment": f"Close_{reason}" if reason else "Close",
            "type_time": mt5.ORDER_TIME_GTC,
            "type_filling": mt5.ORDER_FILLING_FOK,
        }
        
        logger.info(f"[FERMETURE] Position #{ticket}, Raison: {reason}")
        
        result = mt5.order_send(request)
        
        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(f"[ERREUR FERMETURE] Ticket #{ticket}, RetCode={result.retcode if result else 'None'}")
            return False
        
        # Mettre à jour l'enregistrement
        with self.lock:
            trade.exit_price = result.price
            trade.exit_time = datetime.now()
            trade.state = PositionState.CLOSED
            trade.profit = (result.price - trade.entry_price) * trade.volume * 100 if trade.order_type == OrderType.BUY else (trade.entry_price - result.price) * trade.volume * 100
            trade.metadata.setdefault("close_reason", reason or "manual")
            
            self.trades_history.append(trade)
            del self.positions[ticket]
        
        logger.info(f"[POSITION FERMÉE] Ticket #{ticket}, Profit={trade.profit:.2f}")
        self._notify_trade_closed(trade)
        return True
    
    def start_position_monitor(self) -> None:
        """Démarre le thread de surveillance des positions"""
        if self.monitor_thread is None or not self.monitor_thread.is_alive():
            self.monitor_stop_event.clear()
            self.monitor_thread = threading.Thread(target=self._monitor_new_positions, daemon=True)
            self.monitor_thread.start()
            logger.info("Thread de surveillance des positions démarré")
    
    def stop_position_monitor(self) -> None:
        """Arrête le thread de surveillance"""
        self.monitor_stop_event.set()
        if self.monitor_thread:
            self.monitor_thread.join(timeout=2)
        logger.info("Thread de surveillance des positions arrêté")
    
    def _monitor_new_positions(self) -> None:
        """Surveille les nouvelles positions créées dans MT5"""
        while not self.monitor_stop_event.is_set():
            try:
                positions = mt5.positions_get(symbol=self.config.symbol)
                
                if positions is not None:
                    current_tickets = {pos.ticket for pos in positions if pos.magic == 234000}
                    new_tickets = current_tickets - self.known_tickets
                    closed_tickets = self.known_tickets - current_tickets
                    
                    # Nouvelles positions
                    for ticket in new_tickets:
                        pos = next((p for p in positions if p.ticket == ticket), None)
                        if pos:
                            logger.info(f"[NOUVELLE POSITION DÉTECTÉE] #{ticket}")
                            with self.lock:
                                if ticket not in self.positions:
                                    trade = TradeRecord(
                                        ticket=ticket,
                                        symbol=pos.symbol,
                                        order_type=OrderType.BUY if pos.type == mt5.ORDER_TYPE_BUY else OrderType.SELL,
                                        volume=pos.volume,
                                        entry_price=pos.price_open,
                                        entry_time=datetime.fromtimestamp(pos.time),
                                        stop_loss=pos.sl,
                                        take_profit=pos.tp,
                                        state=PositionState.OPEN,
                                        metadata={
                                            "trailing_stage": 0,
                                            "trailing_plan": {
                                                "secure_profit": self.config.trailing_secure_base,
                                                "extension_trigger": self.config.trailing_extension_base,
                                                "trailing_distance": self.config.trailing_distance_base,
                                            },
                                        },
                                    )
                                    self.positions[ticket] = trade
                    
                    # Positions fermées
                    for ticket in closed_tickets:
                        logger.info(f"[POSITION FERMÉE DÉTECTÉE] #{ticket}")
                        with self.lock:
                            if ticket in self.positions:
                                trade = self.positions[ticket]
                                trade.state = PositionState.CLOSED
                                trade.exit_time = datetime.now()
                                trade.metadata.setdefault("close_reason", "external_monitor")
                                self.trades_history.append(trade)
                                del self.positions[ticket]
                                notify_trade = trade
                            else:
                                notify_trade = None

                        if notify_trade:
                            self._notify_trade_closed(notify_trade)
                    
                    self.known_tickets = current_tickets
                
                time.sleep(1)  # Vérifier toutes les secondes
                
            except Exception as e:
                logger.error(f"Erreur dans le monitoring des positions: {e}")
                time.sleep(1)
    
    def get_open_positions_count(self) -> int:
        """Retourne le nombre de positions ouvertes"""
        with self.lock:
            return len(self.positions)
    
    def get_position_by_ticket(self, ticket: int) -> Optional[TradeRecord]:
        """Récupère une position par son ticket"""
        with self.lock:
            return self.positions.get(ticket)
    
    def get_all_positions(self) -> List[TradeRecord]:
        """Retourne toutes les positions ouvertes"""
        with self.lock:
            return list(self.positions.values())
    
    def get_unrealized_profit(self, ticket: int) -> float:
        """
        Calcule le profit non réalisé d'une position spécifique en temps réel.
        Retourne le profit en dollars.
        """
        try:
            # Vérifier que la position existe dans MT5
            position = mt5.positions_get(ticket=ticket)
            if not position or len(position) == 0:
                return 0.0
            
            pos = position[0]
            
            # Le profit est directement disponible depuis MT5
            return pos.profit
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul du profit pour #{ticket}: {e}")
            return 0.0
    
    def get_total_unrealized_profit(self) -> float:
        """
        Calcule le profit total non réalisé de toutes les positions du bot.
        Retourne le profit cumulé en dollars.
        """
        total_profit = 0.0
        
        try:
            # Récupérer toutes les positions du symbole avec le magic number du bot
            positions = mt5.positions_get(symbol=self.config.symbol)
            
            if positions:
                for pos in positions:
                    # Ne compter que les positions du bot (magic 234000)
                    if pos.magic == 234000:
                        total_profit += pos.profit
            
            return total_profit
            
        except Exception as e:
            logger.error(f"Erreur lors du calcul du profit total: {e}")
            return 0.0

    def update_trade_metadata(self, ticket: int, updates: dict) -> None:
        """Met à jour les métadonnées d'un trade ouvert."""
        with self.lock:
            trade = self.positions.get(ticket)
            if trade:
                trade.metadata.update(updates)
    
    def _modify_position_sl_tp(self, position, new_sl: Optional[float], new_tp: Optional[float]) -> bool:
        """Modifie le SL/TP d'une position existante."""
        current_sl = position.sl if position.sl not in (None, 0.0) else 0.0
        current_tp = position.tp if position.tp not in (None, 0.0) else 0.0

        request = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": position.symbol,
            "position": position.ticket,
            "sl": float(new_sl) if new_sl is not None else float(current_sl),
            "tp": float(new_tp) if new_tp is not None else float(current_tp),
            "magic": position.magic,
        }

        result = mt5.order_send(request)

        if result is None or result.retcode != mt5.TRADE_RETCODE_DONE:
            logger.error(
                f"[TRAILING] Échec de modification SL/TP (ticket={position.ticket}) retcode={getattr(result, 'retcode', 'None')}"
            )
            return False

        symbol_info = mt5.symbol_info(position.symbol)
        digits = symbol_info.digits if symbol_info else 2
        fmt = lambda val: f"{val:.{digits}f}"
        logger.info(
            f"[TRAILING] SL/TP mis à jour pour #{position.ticket}: SL={fmt(request['sl'])}, TP={fmt(request['tp'])}"
        )
        return True

    def apply_trailing_strategy(
        self,
        trade: TradeRecord,
        secure_profit: float,
        extension_trigger: float,
        trailing_distance: float,
    ) -> bool:
        """Applique le trailing stop en deux étapes sur une position."""

        if trade.state != PositionState.OPEN:
            return False

        position_data = mt5.positions_get(ticket=trade.ticket)
        if not position_data:
            return False

        position = position_data[0]
        symbol_info = mt5.symbol_info(position.symbol)
        if symbol_info is None:
            logger.error("Impossible de récupérer les informations du symbole pour le trailing")
            return False

        digits = symbol_info.digits

        def round_price(value: float) -> float:
            return round(value, digits)

        current_sl = position.sl if position.sl not in (None, 0.0) else None
        current_tp = position.tp if position.tp not in (None, 0.0) else None
        stage = int(trade.metadata.get("trailing_stage", 0))
        profit = float(position.profit)

        volume_value = max(position.volume * 100.0, 1e-6)
        secure_offset = secure_profit / volume_value
        extension_offset = extension_trigger / volume_value
        trailing_offset = trailing_distance / volume_value
        sign = 1.0 if trade.order_type == OrderType.BUY else -1.0
        min_step = symbol_info.point * 0.5
        now_iso = datetime.utcnow().isoformat()
        updated = False

        with self.lock:
            last_unrealized = float(trade.metadata.get("last_unrealized_profit", profit))
            max_unrealized = float(trade.metadata.get("max_unrealized_profit", profit))
            min_unrealized = float(trade.metadata.get("max_unrealized_drawdown", profit))
            trade.metadata["last_unrealized_profit"] = profit
            trade.metadata["max_unrealized_profit"] = max(max_unrealized, profit)
            trade.metadata["max_unrealized_drawdown"] = min(min_unrealized, profit)

        # Étape 1 : sécurisation du profit minimal
        if stage == 0 and profit >= secure_profit:
            new_sl = round_price(trade.entry_price + sign * secure_offset)
            new_tp = round_price(trade.entry_price + sign * extension_offset)

            if self._modify_position_sl_tp(position, new_sl, new_tp):
                with self.lock:
                    trade.stop_loss = new_sl
                    trade.take_profit = new_tp
                    trade.metadata.update(
                        {
                            "trailing_stage": 1,
                            "secure_profit": secure_profit,
                            "extension_trigger": extension_trigger,
                            "trailing_distance": trailing_distance,
                            "stage1_activated_at": now_iso,
                            "last_trailing_update": now_iso,
                        }
                    )

                stage = 1
                updated = True

                position_data = mt5.positions_get(ticket=trade.ticket)
                if position_data:
                    position = position_data[0]
                    current_sl = position.sl if position.sl not in (None, 0.0) else new_sl
                    current_tp = position.tp if position.tp not in (None, 0.0) else new_tp

        # Étape 2 : trailing dynamique
        if stage >= 1 and profit >= extension_trigger:
            current_price = position.price_current

            if trade.order_type == OrderType.BUY:
                base_secure_price = trade.entry_price + secure_offset
                candidate_sl = max(current_price - trailing_offset, base_secure_price)
                improvement = (
                    current_sl is None or candidate_sl > current_sl + min_step
                )
                new_sl = round_price(candidate_sl)
                new_tp = round_price(current_price + trailing_offset)
            else:
                base_secure_price = trade.entry_price - secure_offset
                candidate_sl = min(current_price + trailing_offset, base_secure_price)
                improvement = (
                    current_sl is None or candidate_sl < current_sl - min_step
                )
                new_sl = round_price(candidate_sl)
                new_tp = round_price(current_price - trailing_offset)

            if stage < 2 or improvement:
                if self._modify_position_sl_tp(position, new_sl, new_tp):
                    with self.lock:
                        trade.stop_loss = new_sl
                        trade.take_profit = new_tp
                        trade.metadata.update(
                            {
                                "trailing_stage": 2,
                                "stage2_activated_at": trade.metadata.get("stage2_activated_at") or now_iso,
                                "last_trailing_update": now_iso,
                            }
                        )

                    updated = True
                    stage = 2
                    current_sl = new_sl
                    current_tp = new_tp

                    position_data = mt5.positions_get(ticket=trade.ticket)
                    if position_data:
                        position = position_data[0]
                        current_sl = position.sl if position.sl not in (None, 0.0) else current_sl
                        current_tp = position.tp if position.tp not in (None, 0.0) else current_tp

        # Maintien du trailing en phase 2 (suivi continu)
        elif stage == 2:
            current_price = position.price_current

            if trade.order_type == OrderType.BUY:
                base_secure_price = trade.entry_price + secure_offset
                candidate_sl = max(current_price - trailing_offset, base_secure_price)
                improvement = (
                    current_sl is None or candidate_sl > current_sl + min_step
                )
                new_sl = round_price(candidate_sl)
                new_tp = round_price(current_price + trailing_offset)
            else:
                base_secure_price = trade.entry_price - secure_offset
                candidate_sl = min(current_price + trailing_offset, base_secure_price)
                improvement = (
                    current_sl is None or candidate_sl < current_sl - min_step
                )
                new_sl = round_price(candidate_sl)
                new_tp = round_price(current_price - trailing_offset)

            if improvement:
                if self._modify_position_sl_tp(position, new_sl, new_tp):
                    with self.lock:
                        trade.stop_loss = new_sl
                        trade.take_profit = new_tp
                        trade.metadata["last_trailing_update"] = now_iso

                    updated = True
                    current_sl = new_sl
                    current_tp = new_tp

        return updated

    def get_trades_history(self) -> List[TradeRecord]:
        """Retourne l'historique des trades"""
        with self.lock:
            return list(self.trades_history)
