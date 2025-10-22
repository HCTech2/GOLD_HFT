#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Modèle OHLC - Représente une bougie
"""

from dataclasses import dataclass
from datetime import datetime


@dataclass
class OHLC:
    """Représente une bougie OHLC"""
    timestamp: datetime
    open: float
    high: float
    low: float
    close: float
    volume: int = 0
