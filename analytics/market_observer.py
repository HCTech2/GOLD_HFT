#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Analyse avancée du marché pour la stratégie SWEEP HFT.
Fournit un contexte enrichi (volatilité, pression volumique, sessions) afin
que la stratégie et le module de Machine Learning puissent ajuster les risques.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Optional

import numpy as np

from config.trading_config import TradingConfig, OrderType
from data.tick_buffer import TickBuffer
from indicators.hft_indicators import HFTIndicators


@dataclass
class MarketContext:
    """Représente l'état courant du marché."""

    timestamp: datetime
    trend_bias: Optional[OrderType]
    stc_m1: Optional[float]
    stc_m5: Optional[float]
    ichimoku_cross_strength: float
    volatility_pp: float
    volume_ratio: float
    volume_pressure: float
    session_label: str
    session_score: float
    favorable_window: bool


class MarketObserver:
    """Calcule les métriques avancées du marché."""

    def __init__(self, config: TradingConfig, indicators: HFTIndicators) -> None:
        self.config = config
        self.indicators = indicators

    # ------------------------------------------------------------------
    # Métriques principales
    # ------------------------------------------------------------------
    def compute_context(self, tick_buffer: TickBuffer) -> MarketContext:
        """Construit un contexte de marché complet."""

        m1_candles = tick_buffer.get_m1_candles(120)
        m5_candles = tick_buffer.get_m5_candles(120)
        timestamp = datetime.utcnow()

        stc_m1 = self.indicators.calculate_stc("M1")
        stc_m5 = self.indicators.calculate_stc("M5")
        trend_bias = self._infer_trend_bias(stc_m1, stc_m5)

        ichimoku_cross_strength = self._estimate_ichimoku_cross_strength()
        volatility_pp = self._compute_volatility(m1_candles)
        volume_ratio, volume_pressure = self._compute_volume_signals(m1_candles)
        session_label, session_score = self._evaluate_session_weight(m1_candles)

        favorable_window = (
            (trend_bias is not None)
            and volume_pressure > 0
            and session_score > 0.5
            and ichimoku_cross_strength >= 0
        )

        return MarketContext(
            timestamp=timestamp,
            trend_bias=trend_bias,
            stc_m1=stc_m1,
            stc_m5=stc_m5,
            ichimoku_cross_strength=ichimoku_cross_strength,
            volatility_pp=volatility_pp,
            volume_ratio=volume_ratio,
            volume_pressure=volume_pressure,
            session_label=session_label,
            session_score=session_score,
            favorable_window=favorable_window,
        )

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _infer_trend_bias(
        self,
        stc_m1: Optional[float],
        stc_m5: Optional[float],
    ) -> Optional[OrderType]:
        if stc_m1 is None or stc_m5 is None:
            return None

        # ZONE HAUSSIÈRE : survente ou double confirmation sous 50
        if stc_m1 <= self.config.stc_threshold_buy or (
            stc_m1 < 50 and stc_m5 < 50
        ):
            return OrderType.BUY

        # ZONE BAISSIÈRE : surachat ou double confirmation au-dessus de 50
        if stc_m1 >= self.config.stc_threshold_sell or (
            stc_m1 > 50 and stc_m5 > 50
        ):
            return OrderType.SELL

        return None

    def _estimate_ichimoku_cross_strength(self) -> float:
        tenkan, kijun, _, _ = self.indicators.calculate_ichimoku("M1")
        if tenkan is None or kijun is None:
            return 0.0
        return tenkan - kijun

    def _compute_volatility(self, candles) -> float:
        if len(candles) < 20:
            return 0.0
        closes = np.array([c.close for c in candles[-60:]])
        returns = np.diff(closes)
        if len(returns) == 0:
            return 0.0
        return float(np.std(returns))

    def _compute_volume_signals(self, candles):
        if len(candles) < 30:
            return 1.0, 0.0

        volumes = np.array([c.volume for c in candles])
        avg_volume = np.mean(volumes[-60:]) if len(volumes) >= 60 else np.mean(volumes)
        recent_volume = np.sum(volumes[-5:]) / max(1, 5)
        volume_ratio = recent_volume / max(avg_volume, 1e-6)
        volume_pressure = float(volume_ratio - 1.0)
        return float(volume_ratio), volume_pressure

    def _evaluate_session_weight(self, candles):
        if not candles:
            return "UNKNOWN", 0.0

        last_ts = candles[-1].timestamp
        hour = last_ts.hour

        london_start, london_end = self.config.kill_zone_london
        ny_start, ny_end = self.config.kill_zone_ny

        if london_start <= hour <= london_end:
            return "LONDON", 0.8
        if ny_start <= hour <= ny_end:
            return "NEW_YORK", 1.0
        return "ASIA", 0.4

    @staticmethod
    def serialize_context(context: MarketContext) -> dict:
        """Convertit un MarketContext en dictionnaire sérialisable."""
        return {
            "timestamp": context.timestamp.isoformat(),
            "trend_bias": context.trend_bias.value if context.trend_bias else None,
            "stc_m1": context.stc_m1,
            "stc_m5": context.stc_m5,
            "ichimoku_cross_strength": context.ichimoku_cross_strength,
            "volatility_pp": context.volatility_pp,
            "volume_ratio": context.volume_ratio,
            "volume_pressure": context.volume_pressure,
            "session_label": context.session_label,
            "session_score": context.session_score,
            "favorable_window": context.favorable_window,
        }
