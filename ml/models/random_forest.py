"""Random Forest wrapper tailored for the HFT ML pipeline.

The implementation delegates to scikit-learn when it is available while
providing convenient helpers for persistence and lazy initialisation.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Iterable, Optional
import pickle

try:
    from sklearn.ensemble import RandomForestClassifier  # type: ignore
except ImportError:  # pragma: no cover - optional dependency
    RandomForestClassifier = None  # type: ignore


@dataclass
class RandomForestModel:
    """Thin wrapper around :class:`RandomForestClassifier`.

    Parameters
    ----------
    n_estimators:
        Number of trees to build. Defaults to 400 (see architecture doc).
    max_depth:
        Optional depth limit for the ensemble.
    random_state:
        Seed for deterministic behaviour across training runs.
    class_weight:
        Optional mapping to rebalance classes if win/loss ratio is skewed.
    """

    n_estimators: int = 400
    max_depth: Optional[int] = None
    random_state: int = 17
    class_weight: Optional[dict[str, float]] = None
    _model: Any = field(default=None, init=False, repr=False)

    # ------------------------------------------------------------------
    # Internal utilities
    # ------------------------------------------------------------------
    def _ensure_dependency(self) -> None:
        if RandomForestClassifier is None:  # pragma: no cover - runtime guard
            raise ImportError(
                "scikit-learn est requis pour RandomForestModel. "
                "Installez-le via `pip install scikit-learn`."
            )

    def _ensure_trained(self) -> Any:
        if self._model is None:
            raise RuntimeError("Le modèle RandomForest n'est pas encore entraîné.")
        return self._model

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------
    def fit(self, X: Iterable[Any], y: Iterable[Any]) -> "RandomForestModel":
        """Train the underlying sklearn model and return self."""

        self._ensure_dependency()
        self._model = RandomForestClassifier(
            n_estimators=self.n_estimators,
            max_depth=self.max_depth,
            random_state=self.random_state,
            class_weight=self.class_weight,
        )
        self._model.fit(X, y)
        return self

    def predict(self, X: Iterable[Any]) -> Any:
        model = self._ensure_trained()
        return model.predict(X)

    def predict_proba(self, X: Iterable[Any]) -> Any:
        model = self._ensure_trained()
        if not hasattr(model, "predict_proba"):
            raise AttributeError("Le modèle RandomForest ne supporte pas predict_proba().")
        return model.predict_proba(X)

    @property
    def feature_importances_(self) -> Any:
        model = self._ensure_trained()
        return model.feature_importances_

    def save(self, path: str | Path) -> Path:
        """Persist the trained model (pickle)."""
        model = self._ensure_trained()
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("wb") as buffer:
            pickle.dump(
                {
                    "params": {
                        "n_estimators": self.n_estimators,
                        "max_depth": self.max_depth,
                        "random_state": self.random_state,
                        "class_weight": self.class_weight,
                    },
                    "model": model,
                },
                buffer,
            )
        return path

    @classmethod
    def load(cls, path: str | Path) -> "RandomForestModel":
        """Restore a model saved with :meth:`save`."""
        path = Path(path)
        with path.open("rb") as buffer:
            payload = pickle.load(buffer)
        instance = cls(**payload["params"])
        instance._model = payload["model"]
        return instance

    @property
    def is_trained(self) -> bool:
        return self._model is not None
