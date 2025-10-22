"""Infrastructure de persistance des trades pour le moteur ML.

Ce module enregistre chaque évènement de trading (entrées, sorties,
résultats) dans une base SQLite optimisée pour l'apprentissage automatique.
Il fournit également des fonctions utilitaires pour calculer des métriques
temps réel (win rate glissant, drawdown) afin d'alimenter le monitoring.
"""

from __future__ import annotations

import json
import sqlite3
import threading
import time
from dataclasses import dataclass, asdict, field
from pathlib import Path
from typing import Any, Dict, Iterable, List, Optional, Tuple


DB_DIR = Path(__file__).resolve().parent / "data"
DB_PATH = DB_DIR / "trades.db"


@dataclass
class TradeEvent:
	"""Évènement de trading complet utilisé pour l'entraînement ML."""

	timestamp: float
	symbol: str
	direction: str  # "BUY" ou "SELL"
	strategy: str
	entry_price: float
	exit_price: Optional[float]
	volume: float
	profit_loss: Optional[float]
	duration_sec: Optional[float]
	order_number: int
	sweep_phase: Optional[str]
	confidence: Optional[float]
	htf_confidence: Optional[float]
	stc_m1: Optional[float]
	stc_m5: Optional[float]
	ichimoku_tenkan: Optional[float]
	ichimoku_kijun: Optional[float]
	atr: Optional[float]
	spread: Optional[float]
	features: Dict[str, Any] = field(default_factory=dict)
	metadata: Dict[str, Any] = field(default_factory=dict)

	def to_db_tuple(self) -> Tuple[Any, ...]:
		"""Transforme l'évènement en tuple prêt pour insertion SQLite."""

		data = asdict(self)
		return (
			data["timestamp"],
			data["symbol"],
			data["direction"],
			data["strategy"],
			data["entry_price"],
			data["exit_price"],
			data["volume"],
			data["profit_loss"],
			data["duration_sec"],
			data["order_number"],
			data["sweep_phase"],
			data["confidence"],
			data["htf_confidence"],
			data["stc_m1"],
			data["stc_m5"],
			data["ichimoku_tenkan"],
			data["ichimoku_kijun"],
			data["atr"],
			data["spread"],
			json.dumps(data["features"], ensure_ascii=False),
			json.dumps(data["metadata"], ensure_ascii=False),
		)


class TradeDatabase:
	"""Gestion centralisée de la base SQLite des trades."""

	def __init__(
		self,
		db_path: Path = DB_PATH,
		buffer_size: int = 100,
		autocommit_interval: float = 30.0,
	) -> None:
		self.db_path = db_path
		self.buffer_size = buffer_size
		self.autocommit_interval = autocommit_interval

		DB_DIR.mkdir(parents=True, exist_ok=True)
		self._lock = threading.RLock()
		self._buffer: List[TradeEvent] = []
		self._last_flush = time.time()

		# Connexion SQLite thread-safe (check_same_thread=False).
		self._conn = sqlite3.connect(self.db_path, check_same_thread=False)
		self._conn.execute("PRAGMA journal_mode=WAL;")
		self._conn.execute("PRAGMA synchronous=NORMAL;")
		self._create_schema()

	# ------------------------------------------------------------------
	# Initialisation
	# ------------------------------------------------------------------
	def _create_schema(self) -> None:
		with self._conn:
			self._conn.execute(
				"""
				CREATE TABLE IF NOT EXISTS trades (
					id INTEGER PRIMARY KEY AUTOINCREMENT,
					timestamp REAL NOT NULL,
					symbol TEXT NOT NULL,
					direction TEXT NOT NULL,
					strategy TEXT NOT NULL,
					entry_price REAL NOT NULL,
					exit_price REAL,
					volume REAL NOT NULL,
					profit_loss REAL,
					duration_sec REAL,
					order_number INTEGER,
					sweep_phase TEXT,
					confidence REAL,
					htf_confidence REAL,
					stc_m1 REAL,
					stc_m5 REAL,
					ichimoku_tenkan REAL,
					ichimoku_kijun REAL,
					atr REAL,
					spread REAL,
					features TEXT,
					metadata TEXT
				);
				"""
			)
			self._conn.execute(
				"""
				CREATE INDEX IF NOT EXISTS idx_trades_symbol_ts
				ON trades(symbol, timestamp);
				"""
			)
			self._conn.execute(
				"""
				CREATE INDEX IF NOT EXISTS idx_trades_direction
				ON trades(direction);
				"""
			)

	# ------------------------------------------------------------------
	# Insertion & flush
	# ------------------------------------------------------------------
	def append(self, event: TradeEvent) -> None:
		"""Ajoute un évènement en mémoire tampon avant persistance."""

		with self._lock:
			self._buffer.append(event)

			should_flush = len(self._buffer) >= self.buffer_size
			should_flush |= (time.time() - self._last_flush) >= self.autocommit_interval

			if should_flush:
				self.flush()

	def flush(self) -> None:
		"""Vide le buffer dans la base SQLite."""

		if not self._buffer:
			return

		with self._lock:
			batch = [event.to_db_tuple() for event in self._buffer]
			self._buffer.clear()
			self._last_flush = time.time()

		with self._conn:
			self._conn.executemany(
				"""
				INSERT INTO trades (
					timestamp, symbol, direction, strategy,
					entry_price, exit_price, volume, profit_loss,
					duration_sec, order_number, sweep_phase,
					confidence, htf_confidence, stc_m1, stc_m5,
					ichimoku_tenkan, ichimoku_kijun, atr, spread,
					features, metadata
				) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
				""",
				batch,
			)

	# ------------------------------------------------------------------
	# Requêtes utilitaires
	# ------------------------------------------------------------------
	def fetch_recent(self, limit: int = 200) -> List[Dict[str, Any]]:
		"""Retourne les derniers trades pour analyses rapides."""

		cursor = self._conn.execute(
			"SELECT * FROM trades ORDER BY timestamp DESC LIMIT ?",
			(limit,),
		)
		columns = [col[0] for col in cursor.description]
		rows = cursor.fetchall()
		return [dict(zip(columns, row)) for row in rows]

	def compute_rolling_stats(self, window: int = 100) -> Dict[str, Any]:
		"""Calcule des métriques glissantes pour le monitoring ML."""

		cursor = self._conn.execute(
			"""
			SELECT profit_loss FROM trades
			WHERE profit_loss IS NOT NULL
			ORDER BY timestamp DESC LIMIT ?
			""",
			(window,),
		)
		pl_values = [row[0] for row in cursor.fetchall()]
		if not pl_values:
			return {"win_rate": None, "avg_profit": None, "avg_loss": None}

		wins = [pl for pl in pl_values if pl > 0]
		losses = [pl for pl in pl_values if pl <= 0]

		win_rate = len(wins) / len(pl_values) if pl_values else 0.0
		avg_profit = sum(wins) / len(wins) if wins else 0.0
		avg_loss = sum(losses) / len(losses) if losses else 0.0

		return {
			"win_rate": win_rate,
			"avg_profit": avg_profit,
			"avg_loss": avg_loss,
			"sample_size": len(pl_values),
		}

	def get_connection(self) -> sqlite3.Connection:
		"""Expose la connexion (lecture seule de préférence)."""

		return self._conn

	def get_trade_count(self) -> int:
		"""Retourne le nombre total de trades dans la base."""
		
		cursor = self._conn.execute("SELECT COUNT(*) FROM trades")
		return cursor.fetchone()[0]

	def get_all_trades(self) -> List[Dict[str, Any]]:
		"""Retourne tous les trades de la base."""
		
		return self.fetch_recent(limit=1000000)  # Assez grand pour tous les trades

	# ------------------------------------------------------------------
	# Nettoyage
	# ------------------------------------------------------------------
	def close(self) -> None:
		self.flush()
		self._conn.close()

	# ------------------------------------------------------------------
	# Helpers context manager
	# ------------------------------------------------------------------
	def __enter__(self) -> "TradeDatabase":
		return self

	def __exit__(self, exc_type, exc, tb) -> None:
		self.close()


__all__ = ["TradeEvent", "TradeDatabase", "DB_PATH"]
