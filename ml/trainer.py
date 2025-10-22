"""Training orchestration utilities for the HFT ML pipeline."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Iterable, Optional, Sequence

import numpy as np

from .feature_extractor import FeatureExtractor
from .models import LSTMTemporalConfig, LSTMTemporalModel, QLearningAgent, RandomForestModel

try:  # Optional dependency: scikit-learn
    from sklearn.metrics import accuracy_score, f1_score, roc_auc_score
    from sklearn.model_selection import train_test_split

    SKLEARN_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency optional
    SKLEARN_AVAILABLE = False

try:  # Optional dependency: PyTorch
    import torch
    from torch import nn
    from torch.utils.data import DataLoader, TensorDataset

    TORCH_AVAILABLE = True
except ImportError:  # pragma: no cover - dependency optional
    torch = None  # type: ignore
    nn = None  # type: ignore
    DataLoader = TensorDataset = None  # type: ignore
    TORCH_AVAILABLE = False


@dataclass
class MLTrainerConfig:
    """Parameters controlling the ML training workflow."""

    dataset_limit: Optional[int] = None
    test_size: float = 0.2
    random_state: int = 42
    persist_models: bool = True
    output_dir: Path = Path("ml/models/active")
    lstm_epochs: int = 5
    lstm_learning_rate: float = 1e-3
    lstm_batch_size: int = 64
    sequence_device: Optional[str] = None
    train_random_forest: bool = True
    train_lstm: bool = True
    train_q_learning: bool = True

    def __post_init__(self) -> None:
        if not 0.0 < self.test_size < 1.0:
            raise ValueError("test_size doit être dans l'intervalle (0, 1)")
        self.output_dir = Path(self.output_dir)


@dataclass
class TrainingArtifacts:
    random_forest_path: Optional[Path] = None
    lstm_path: Optional[Path] = None
    q_learning_path: Optional[Path] = None


@dataclass
class TrainingReport:
    metrics: Dict[str, Dict[str, float]] = field(default_factory=dict)
    artifacts: TrainingArtifacts = field(default_factory=TrainingArtifacts)
    sample_counts: Dict[str, int] = field(default_factory=dict)


class MLTrainer:
    """High-level facade coordinating dataset preparation and model training."""

    def __init__(
        self,
        extractor: Optional[FeatureExtractor] = None,
        config: Optional[MLTrainerConfig] = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self.extractor = extractor or FeatureExtractor()
        self.config = config or MLTrainerConfig()
        self.logger = logger or logging.getLogger(__name__)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def run(self) -> TrainingReport:
        """Execute the end-to-end training workflow."""

        static, sequences, targets = self._prepare_dataset()
        report = TrainingReport(sample_counts={"samples": len(targets)})

        if self.config.train_random_forest:
            rf_metrics, rf_path = self._train_random_forest(static, targets)
            if rf_metrics:
                report.metrics["random_forest"] = rf_metrics
            report.artifacts.random_forest_path = rf_path

        if self.config.train_lstm:
            lstm_metrics, lstm_path = self._train_lstm(sequences, targets)
            if lstm_metrics:
                report.metrics["lstm"] = lstm_metrics
            report.artifacts.lstm_path = lstm_path

        if self.config.train_q_learning:
            q_table_size, q_path = self._train_q_learning(static, targets)
            report.metrics["q_learning"] = {"states": float(q_table_size)}
            report.artifacts.q_learning_path = q_path

        return report

    # ------------------------------------------------------------------
    # Dataset preparation
    # ------------------------------------------------------------------
    def _prepare_dataset(self) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        self.logger.info("Chargement du dataset depuis TradeDatabase…")
        static_df, sequences, targets_series = self.extractor.prepare_dataset(limit=self.config.dataset_limit)

        static_values = static_df.to_numpy(dtype=np.float32)
        sequences = sequences.astype(np.float32)
        targets = targets_series.to_numpy(dtype=np.int64)

        if len(targets) < 2:
            raise ValueError("Le dataset doit contenir au moins 2 échantillons")

        self.logger.info("Dataset prêt: %s exemples", len(targets))
        return static_values, sequences, targets

    # ------------------------------------------------------------------
    # Random Forest training
    # ------------------------------------------------------------------
    def _train_random_forest(
        self, static: np.ndarray, targets: np.ndarray
    ) -> tuple[Dict[str, float], Optional[Path]]:
        if not SKLEARN_AVAILABLE:
            self.logger.warning("scikit-learn manquant, RandomForest ignoré")
            return {}, None

        stratify = targets if len(np.unique(targets)) > 1 else None
        X_train, X_test, y_train, y_test = train_test_split(
            static,
            targets,
            test_size=self.config.test_size,
            random_state=self.config.random_state,
            stratify=stratify,
        )

        self.logger.info("Entraînement RandomForest (%s échantillons)", len(y_train))
        model = RandomForestModel(random_state=self.config.random_state)
        model.fit(X_train, y_train)

        y_pred = model.predict(X_test)
        metrics: Dict[str, float] = {
            "accuracy": float(accuracy_score(y_test, y_pred)),
            "f1": float(f1_score(y_test, y_pred, zero_division=0)),
        }

        try:
            y_proba = model.predict_proba(X_test)[:, 1]
            metrics["roc_auc"] = float(roc_auc_score(y_test, y_proba))
        except Exception:  # pragma: no cover - predict_proba absent ou échec num
            pass

        path: Optional[Path] = None
        if self.config.persist_models:
            path = self._persist_artifact(model.save, "random_forest.pkl")
            self.logger.info("RandomForest sauvegardé: %s", path)

        return metrics, path

    # ------------------------------------------------------------------
    # LSTM training
    # ------------------------------------------------------------------
    def _train_lstm(
        self, sequences: np.ndarray, targets: np.ndarray
    ) -> tuple[Dict[str, float], Optional[Path]]:
        if not TORCH_AVAILABLE:
            self.logger.warning("PyTorch manquant, LSTM ignoré")
            return {}, None

        stratify = targets if len(np.unique(targets)) > 1 else None
        idx_train, idx_test = self._train_test_split_indices(len(targets), stratify)

        X_train = torch.from_numpy(sequences[idx_train])  # type: ignore[arg-type]
        y_train = torch.from_numpy(targets[idx_train].astype(np.float32)).unsqueeze(1)  # type: ignore[arg-type]
        X_test = torch.from_numpy(sequences[idx_test])  # type: ignore[arg-type]
        y_test = torch.from_numpy(targets[idx_test].astype(np.float32)).unsqueeze(1)  # type: ignore[arg-type]

        dataset = TensorDataset(X_train, y_train)
        loader = DataLoader(
            dataset,
            batch_size=self.config.lstm_batch_size,
            shuffle=True,
        )

        config = LSTMTemporalConfig(input_dim=sequences.shape[-1])
        model = LSTMTemporalModel(config, device=self.config.sequence_device)
        criterion = nn.BCELoss()
        optimiser = torch.optim.Adam(model.parameters(), lr=self.config.lstm_learning_rate)

        self.logger.info("Entraînement LSTM (%s échantillons, %s epochs)", len(dataset), self.config.lstm_epochs)
        model.train()
        for epoch in range(self.config.lstm_epochs):
            epoch_loss = 0.0
            for batch_X, batch_y in loader:
                optimiser.zero_grad()
                preds = model(batch_X)
                loss = criterion(preds, batch_y.to(model.device).float())
                loss.backward()
                optimiser.step()
                epoch_loss += loss.item() * len(batch_X)

            epoch_loss /= max(1, len(dataset))
            self.logger.debug("LSTM epoch %s loss=%.4f", epoch + 1, epoch_loss)

        model.eval()
        with torch.no_grad():
            preds = model.predict_proba(X_test).cpu().numpy()
        y_pred = (preds >= 0.5).astype(int)
        y_true = y_test.cpu().numpy()

        metrics = {
            "accuracy": float((y_pred == y_true).mean()),
            "f1": float(self._safe_f1_binary(y_true, y_pred)),
        }

        path: Optional[Path] = None
        if self.config.persist_models:
            path = self._persist_artifact(model.save, "lstm_temporal.pt")
            self.logger.info("LSTM sauvegardé: %s", path)

        return metrics, path

    # ------------------------------------------------------------------
    # Q-learning training
    # ------------------------------------------------------------------
    def _train_q_learning(
        self, static: np.ndarray, targets: np.ndarray
    ) -> tuple[int, Optional[Path]]:
        agent = QLearningAgent()
        rewards = np.where(targets > 0, 1.0, -1.0)
        states = [tuple(np.round(row, 4)) for row in static]

        for idx, state in enumerate(states[:-1]):
            action = agent.select_action(state)
            reward = rewards[idx]
            next_state = states[idx + 1]
            agent.update(state, action, reward, next_state)
            agent.decay_epsilon()

        path: Optional[Path] = None
        if self.config.persist_models:
            path = self._persist_artifact(agent.save, "q_learning.json")
            self.logger.info("Q-learning sauvegardé: %s", path)

        return len(agent._q_table), path

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------
    def _train_test_split_indices(self, length: int, stratify: Optional[Sequence[int]]) -> tuple[np.ndarray, np.ndarray]:
        indices = np.arange(length)
        if SKLEARN_AVAILABLE:
            return train_test_split(
                indices,
                test_size=self.config.test_size,
                random_state=self.config.random_state,
                stratify=stratify,
            )

        rng = np.random.default_rng(self.config.random_state)
        rng.shuffle(indices)
        split = int(length * (1 - self.config.test_size))
        split = min(max(split, 1), length - 1)
        return indices[:split], indices[split:]

    def _persist_artifact(self, saver: Any, filename: str) -> Path:
        timestamp = datetime.utcnow().strftime("%Y%m%d_%H%M%S")
        path = self.config.output_dir / timestamp / filename
        path.parent.mkdir(parents=True, exist_ok=True)
        saver(path)
        return path

    @staticmethod
    def _safe_f1_binary(y_true: np.ndarray, y_pred: np.ndarray) -> float:
        positives = y_true.sum() + y_pred.sum()
        if positives == 0:
            return 0.0
        tp = ((y_true == 1) & (y_pred == 1)).sum()
        precision = tp / max(1, y_pred.sum())
        recall = tp / max(1, y_true.sum())
        if precision + recall == 0:
            return 0.0
        return 2 * precision * recall / (precision + recall)


__all__ = [
    "MLTrainer",
    "MLTrainerConfig",
    "TrainingReport",
    "TrainingArtifacts",
]
