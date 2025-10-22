"""Torch-based LSTM temporal model used to estimate future trade profitability."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

try:  # pragma: no cover - optional dependency
    import torch
    from torch import nn
    TensorType = torch.Tensor
except ImportError:  # pragma: no cover - optional dependency
    torch = None  # type: ignore
    nn = None  # type: ignore
    TensorType = Any


if nn is not None:
    BaseModule = nn.Module
else:  # pragma: no cover - fallback when torch absent
    class BaseModule:  # type: ignore[misc]
        """Fallback base class when PyTorch is not installed."""

        def __init__(self, *args: Any, **kwargs: Any) -> None:  # noqa: D401
            super().__init__()



@dataclass
class LSTMTemporalConfig:
    input_dim: int
    hidden_size: int = 64
    num_layers: int = 2
    dropout: float = 0.2
    bidirectional: bool = False


class LSTMTemporalModel(BaseModule):
    """Simple LSTM + dense head for binary profit prediction."""

    def __init__(self, config: LSTMTemporalConfig, device: Optional[str] = None) -> None:
        if torch is None or nn is None:  # pragma: no cover - guard
            raise ImportError(
                "PyTorch est requis pour LSTMTemporalModel. Installez-le via `pip install torch`."
            )
        if nn is None:
            raise ImportError(
                "PyTorch est requis pour LSTMTemporalModel. Installez-le via `pip install torch`."
            )
        super().__init__()
        self.config = config
        self.device = torch.device(device or ("cuda" if torch.cuda.is_available() else "cpu"))

        hidden = config.hidden_size
        num_directions = 2 if config.bidirectional else 1

        self.lstm = nn.LSTM(
            input_size=config.input_dim,
            hidden_size=hidden,
            num_layers=config.num_layers,
            dropout=config.dropout if config.num_layers > 1 else 0.0,
            batch_first=True,
            bidirectional=config.bidirectional,
        )
        self.dropout = nn.Dropout(config.dropout)
        self.head = nn.Sequential(
            nn.Linear(hidden * num_directions, hidden),
            nn.ReLU(),
            nn.Dropout(config.dropout),
            nn.Linear(hidden, 1),
            nn.Sigmoid(),
        )
        self.to(self.device)

    def forward(self, batch: Any) -> Any:  # type: ignore[override]
        if torch is None:
            raise RuntimeError("PyTorch n'est pas disponible")
        batch = batch.to(self.device)
        outputs, _ = self.lstm(batch)
        last_hidden = outputs[:, -1, :]
        return self.head(self.dropout(last_hidden))

    def predict_proba(self, batch: Any) -> Any:
        if torch is None:
            raise RuntimeError("PyTorch n'est pas disponible")
        self.eval()
        with torch.no_grad():
            return self.forward(batch)

    def save(self, path: str | Path) -> Path:
        if torch is None:
            raise RuntimeError("PyTorch n'est pas disponible")
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "state_dict": self.state_dict(),
            "config": self.config,
        }
        torch.save(payload, path)
        return path

    @classmethod
    def load(cls, path: str | Path, device: Optional[str] = None) -> "LSTMTemporalModel":
        if torch is None:
            raise RuntimeError("PyTorch n'est pas disponible")
        path = Path(path)
        payload = torch.load(path, map_location=device or "cpu")
        model = cls(payload["config"], device=device)
        model.load_state_dict(payload["state_dict"])
        return model
