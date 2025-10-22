#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modèle de Tick - Représente un tick de marché
"""

from dataclasses import dataclass
from datetime import datetime


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
