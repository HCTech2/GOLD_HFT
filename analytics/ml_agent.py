#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Agent d'apprentissage en ligne pour adapter les paramètres de gestion de position.
Le modèle est volontairement léger (perceptron linéaire) afin d'évoluer en temps réel
sans dépendre de bibliothèques lourdes.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime
from pathlib import Path
from typing import Optional

import numpy as np

from analytics.market_observer import MarketContext
from config.trading_config import OrderType, TradingConfig


@dataclass
class TradeExperience:
    """Représente une expérience de trade pour l'apprentissage en ligne."""

    order_type: OrderType
    profit: float
    max_profit: float
    max_drawdown: float
    duration_seconds: float
    context: MarketContext


@dataclass
class MLRecommendation:
    """Paramètres de gestion de position générés par le modèle ML."""

    risk_multiplier: float
    sl_multiplier: float
    tp_multiplier: float
    secure_profit: float
    extension_trigger: float
    trailing_distance: float
    avoid_trade: bool
    confidence: float


class HFTLearningAgent:
    """Agent de ML en ligne basé sur un perceptron régularisé."""

    def __init__(self, config: TradingConfig, state_path: Optional[Path] = None) -> None:
        self.config = config
        self.learning_rate = 0.05
        self.regularization = 1e-4
        self.state_path = state_path or Path("data/ml_state.npz")
        self.weight_shape = 9  # biais + 8 features
        self.weights = np.zeros(self.weight_shape, dtype=np.float64)
        self.loss_decay = 0.97
        self.avg_profit = 0.0
        self.avg_loss = 0.0
        self.samples_seen = 0

        self._load_state()

    # ------------------------------------------------------------------
    # Persistance
    # ------------------------------------------------------------------
    def _load_state(self) -> None:
        if not self.state_path.exists():
            return

        try:
            data = np.load(self.state_path, allow_pickle=True)
            self.weights = data.get("weights", self.weights)
            self.avg_profit = float(data.get("avg_profit", self.avg_profit))
            self.avg_loss = float(data.get("avg_loss", self.avg_loss))
            self.samples_seen = int(data.get("samples_seen", self.samples_seen))
        except Exception:
            self.weights = np.zeros(self.weight_shape, dtype=np.float64)

    def _save_state(self) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        np.savez(
            self.state_path,
            weights=self.weights,
            avg_profit=self.avg_profit,
            avg_loss=self.avg_loss,
            samples_seen=self.samples_seen,
        )

    # ------------------------------------------------------------------
    # Caractéristiques d'entrée
    # ------------------------------------------------------------------
    def _encode_features(self, context: MarketContext, order_type: OrderType) -> np.ndarray:
        direction = 1.0 if order_type == OrderType.BUY else -1.0
        ichimoku_strength = context.ichimoku_cross_strength or 0.0
        volatility = context.volatility_pp
        volume_pressure = context.volume_pressure
        session_score = context.session_score
        stc_m1 = (context.stc_m1 or 50.0) / 100.0
        stc_m5 = (context.stc_m5 or 50.0) / 100.0
        favorable_flag = 1.0 if context.favorable_window else 0.0

        return np.array(
            [
                1.0,
                direction,
                ichimoku_strength * direction,
                volatility,
                volume_pressure,
                session_score,
                stc_m1 * direction,
                stc_m5 * direction,
                favorable_flag,
            ],
            dtype=np.float64,
        )

    # ------------------------------------------------------------------
    # Recommandations de gestion
    # ------------------------------------------------------------------
    def recommend(self, context: MarketContext, order_type: OrderType) -> MLRecommendation:
        features = self._encode_features(context, order_type)
        prediction = float(np.dot(self.weights, features))
        confidence = float(np.tanh(prediction / 15.0))  # borne [-1, 1]

        base_multiplier = 1.0 + 0.6 * confidence
        risk_multiplier = float(np.clip(base_multiplier, 0.5, 2.0))

        if confidence >= 0:
            sl_multiplier = float(np.clip(1.0 - 0.25 * confidence, 0.6, 1.0))
            tp_multiplier = float(np.clip(1.0 + 0.5 * confidence, 1.0, 2.5))
        else:
            sl_multiplier = float(np.clip(1.0 - 0.1 * confidence, 1.0, 1.6))
            tp_multiplier = float(np.clip(1.0 + 0.2 * confidence, 0.6, 1.2))

        secure_profit = float(np.clip(5.0 * risk_multiplier, 2.0, 12.0))
        extension_trigger = secure_profit + float(np.clip(3.0 + abs(prediction) * 0.2, 3.0, 20.0))
        trailing_distance = float(np.clip(max(context.volatility_pp * 1.5, 1.0), 1.0, 15.0))

        avoid_trade = confidence < -0.55

        return MLRecommendation(
            risk_multiplier=risk_multiplier,
            sl_multiplier=sl_multiplier,
            tp_multiplier=tp_multiplier,
            secure_profit=secure_profit,
            extension_trigger=extension_trigger,
            trailing_distance=trailing_distance,
            avoid_trade=avoid_trade,
            confidence=confidence,
        )

    # ------------------------------------------------------------------
    # Apprentissage
    # ------------------------------------------------------------------
    def update(self, experience: TradeExperience) -> None:
        features = self._encode_features(experience.context, experience.order_type)
        prediction = float(np.dot(self.weights, features))
        target = experience.profit
        error = target - prediction

        self.weights += self.learning_rate * error * features
        self.weights *= (1.0 - self.learning_rate * self.regularization)

        self.avg_profit = self.loss_decay * self.avg_profit + (1 - self.loss_decay) * max(target, 0.0)
        self.avg_loss = self.loss_decay * self.avg_loss + (1 - self.loss_decay) * min(target, 0.0)
        self.samples_seen += 1

        self._save_state()

    # ------------------------------------------------------------------
    # Utilitaires
    # ------------------------------------------------------------------
    def reconstruct_context(self, context_dict: dict) -> MarketContext:
        if not context_dict:
            raise ValueError("context_dict is empty")

        data = dict(context_dict)

        trend = data.get("trend_bias")
        if trend is not None and not isinstance(trend, OrderType):
            data["trend_bias"] = OrderType(trend)

        timestamp = data.get("timestamp")
        if isinstance(timestamp, str):
            data["timestamp"] = datetime.fromisoformat(timestamp)
        elif timestamp is None:
            data["timestamp"] = datetime.utcnow()

        float_fields = (
            "ichimoku_cross_strength",
            "volatility_pp",
            "volume_ratio",
            "volume_pressure",
            "session_score",
            "stc_m1",
            "stc_m5",
        )
        for key in float_fields:
            if key in data and data[key] is not None:
                data[key] = float(data[key])

        data["favorable_window"] = bool(data.get("favorable_window", False))

        return MarketContext(**data)

    @staticmethod
    def recommendation_to_dict(recommendation: MLRecommendation) -> dict:
        return asdict(recommendation)

    @staticmethod
    def recommendation_from_dict(data: dict) -> MLRecommendation:
        return MLRecommendation(**data)