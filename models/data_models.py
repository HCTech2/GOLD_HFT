#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modèles de données pour le bot HFT
"""

from dataclasses import dataclass, field
from datetime import datetime
from typing import Optional
from config.trading_config import OrderType, PositionState


@dataclass
class Tick:
    """Représente un tick de marché"""
    symbol: str
    bid: float
    ask: float
    timestamp: datetime
    volume: int = 0
    
    @property
    def mid_price(self) -> float:
        """Prix moyen entre bid et ask"""
        return (self.bid + self.ask) / 2
    
    @property
    def spread(self) -> float:
        """Spread en dollars"""
        return abs(self.ask - self.bid)


@dataclass
class OHLC:
    """Représente une bougie OHLC"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0


@dataclass
class TradeRecord:
    """Enregistrement d'un trade"""
    ticket: int
    symbol: str
    order_type: OrderType
    volume: float
    entry_price: float
    entry_time: datetime
    stop_loss: float
    take_profit: float
    state: PositionState = PositionState.OPEN
    exit_price: Optional[float] = None
    exit_time: Optional[datetime] = None
    profit: float = 0.0
    entry_tick_count: int = 0
    exit_tick_count: int = 0
    metadata: dict = field(default_factory=dict)
