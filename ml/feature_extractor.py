"""Feature extraction utilities for the HFT ML pipeline."""

from __future__ import annotations

from dataclasses import dataclass
from typing import List, Optional, Tuple

import numpy as np
import pandas as pd

from .trade_database import DB_PATH, TradeDatabase


@dataclass
class FeatureExtractionConfig:
    sequence_window: int = 20
    min_samples: int = 200
    stc_columns: Tuple[str, ...] = ("stc_m1", "stc_m5")
    ichimoku_columns: Tuple[str, ...] = ("ichimoku_tenkan", "ichimoku_kijun")
    volatility_columns: Tuple[str, ...] = ("atr", "spread", "volume_ratio", "volume_pressure")
    time_features: Tuple[str, ...] = ("session_label",)


class FeatureExtractor:
    """Transform raw TradeEvents into ML-ready feature matrices."""

    def __init__(self, db: Optional[TradeDatabase] = None, config: Optional[FeatureExtractionConfig] = None) -> None:
        self.db = db or TradeDatabase(DB_PATH)
        self.config = config or FeatureExtractionConfig()

    # ------------------------------------------------------------------
    # Loading utilities
    # ------------------------------------------------------------------
    def load_dataframe(self, limit: Optional[int] = None) -> pd.DataFrame:
        query = "SELECT * FROM trades ORDER BY timestamp ASC"
        if limit:
            query += f" LIMIT {int(limit)}"
        df = pd.read_sql_query(query, self.db.get_connection())
        if df.empty:
            raise ValueError("Trade database is empty; cannot build dataset")
        df["timestamp"] = pd.to_datetime(df["timestamp"], unit="s")
        return df

    # ------------------------------------------------------------------
    # Static features
    # ------------------------------------------------------------------
    def _extract_static_features(self, df: pd.DataFrame) -> pd.DataFrame:
        static_cols: List[str] = [
            "entry_price",
            "volume",
            "htf_confidence",
            "order_number",
            "rr_ratio",
        ]

        for col in self.config.stc_columns + self.config.ichimoku_columns + self.config.volatility_columns:
            if col in df.columns:
                static_cols.append(col)

        if "features" in df.columns:
            features_expanded = df["features"].apply(self._json_to_series)
            df = pd.concat([df.drop(columns=["features"]), features_expanded], axis=1)

        static_frame = df[static_cols].copy()
        static_frame = static_frame.replace([np.inf, -np.inf], np.nan).fillna(method="ffill").fillna(0.0)
        return static_frame

    # ------------------------------------------------------------------
    # Sequential features for LSTM
    # ------------------------------------------------------------------
    def _extract_sequences(self, df: pd.DataFrame) -> np.ndarray:
        window = self.config.sequence_window
        seq_features: List[np.ndarray] = []
        numeric_df = df.select_dtypes(include=[np.number]).replace([np.inf, -np.inf], np.nan).fillna(method="ffill").fillna(0.0)
        values = numeric_df.values
        if len(values) < window:
            raise ValueError(f"Not enough samples for sequence window {window}")

        for idx in range(window, len(values) + 1):
            seq_slice = values[idx - window : idx]
            seq_features.append(seq_slice)
        return np.stack(seq_features)

    # ------------------------------------------------------------------
    # Targets
    # ------------------------------------------------------------------
    def _last_sequence_targets(self, df: pd.DataFrame) -> pd.Series:
        window = self.config.sequence_window
        target = (df["profit_loss"] > 0).astype(int)
        return target.iloc[window - 1 :]

    # ------------------------------------------------------------------
    # Public interface
    # ------------------------------------------------------------------
    def prepare_dataset(self, limit: Optional[int] = None) -> Tuple[pd.DataFrame, np.ndarray, pd.Series]:
        df = self.load_dataframe(limit=limit)
        if len(df) < self.config.min_samples:
            raise ValueError(
                f"Need at least {self.config.min_samples} trades for training; got {len(df)}"
            )
        static_frame = self._extract_static_features(df)
        sequences = self._extract_sequences(df)
        targets = self._last_sequence_targets(df)
        static_frame = static_frame.iloc[-len(targets) :]
        return static_frame, sequences, targets

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    @staticmethod
    def _json_to_series(value: str) -> pd.Series:
        if not value:
            return pd.Series(dtype=float)
        if isinstance(value, dict):
            data = value
        else:
            data = pd.read_json(value, typ="series") if value.startswith("{") else {}
        return pd.Series(data)