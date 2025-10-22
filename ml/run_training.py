"""Command-line runner for the ML training pipeline."""

from __future__ import annotations

import argparse
import json
import logging
import sys
from dataclasses import asdict
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, Optional

from .trainer import MLTrainer, MLTrainerConfig, TrainingReport

DEFAULT_REPORT_PATH = Path("ml/reports/last_training.json")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Lance l'entraînement des modèles ML du bot HFT.",
    )
    parser.add_argument("--dataset-limit", type=int, default=None, help="Nombre maximum de trades à charger.")
    parser.add_argument("--test-size", type=float, default=0.2, help="Proportion du jeu de test (0-1).")
    parser.add_argument("--random-state", type=int, default=42, help="Seed pour la reproductibilité.")
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("ml/models/active"),
        help="Répertoire racine de sauvegarde des modèles entraînés.",
    )
    parser.add_argument("--no-persist", action="store_true", help="Ne pas sauvegarder les modèles entraînés.")
    parser.add_argument("--skip-rf", action="store_true", help="Ignorer l'entraînement du RandomForest.")
    parser.add_argument("--skip-lstm", action="store_true", help="Ignorer l'entraînement de l'LSTM.")
    parser.add_argument("--skip-rl", action="store_true", help="Ignorer l'entraînement Q-learning.")
    parser.add_argument("--lstm-epochs", type=int, default=5, help="Nombre d'epochs pour l'LSTM.")
    parser.add_argument("--lstm-lr", type=float, default=1e-3, help="Taux d'apprentissage pour l'LSTM.")
    parser.add_argument("--lstm-batch-size", type=int, default=64, help="Taille de batch pour l'LSTM.")
    parser.add_argument(
        "--sequence-device",
        type=str,
        default=None,
        help="Device PyTorch à utiliser (ex: cuda, cpu).",
    )
    parser.add_argument(
        "--report-path",
        type=Path,
        default=DEFAULT_REPORT_PATH,
        help="Chemin du rapport JSON généré.",
    )
    parser.add_argument(
        "--log-level",
        type=str,
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Niveau de log",
    )
    return parser


def report_to_dict(report: TrainingReport) -> Dict[str, Any]:
    def path_to_str(path: Optional[Path]) -> Optional[str]:
        return str(path) if path else None

    data: Dict[str, Any] = {
        "metrics": report.metrics,
        "sample_counts": report.sample_counts,
        "artifacts": {
            "random_forest": path_to_str(report.artifacts.random_forest_path),
            "lstm": path_to_str(report.artifacts.lstm_path),
            "q_learning": path_to_str(report.artifacts.q_learning_path),
        },
    }
    return data


def main(argv: Optional[list[str]] = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    logging.basicConfig(
        level=getattr(logging, args.log_level.upper(), logging.INFO),
        format="%(asctime)s | %(levelname)s | %(name)s | %(message)s",
    )
    logger = logging.getLogger("ml.run_training")

    config = MLTrainerConfig(
        dataset_limit=args.dataset_limit,
        test_size=args.test_size,
        random_state=args.random_state,
        persist_models=not args.no_persist,
        output_dir=args.output_dir,
        lstm_epochs=args.lstm_epochs,
        lstm_learning_rate=args.lstm_lr,
        lstm_batch_size=args.lstm_batch_size,
        sequence_device=args.sequence_device,
        train_random_forest=not args.skip_rf,
        train_lstm=not args.skip_lstm,
        train_q_learning=not args.skip_rl,
    )

    trainer = MLTrainer(config=config, logger=logger)

    try:
        report = trainer.run()
    except Exception as exc:
        logger.error("Échec de l'entraînement: %s", exc, exc_info=True)
        return 1

    if args.report_path:
        report_path = args.report_path
        report_path.parent.mkdir(parents=True, exist_ok=True)
        report_payload = {
            "generated_at": datetime.utcnow().isoformat() + "Z",
            "config": asdict(config),
            "results": report_to_dict(report),
        }
        report_path.write_text(json.dumps(report_payload, indent=2), encoding="utf-8")
        logger.info("Rapport sauvegardé: %s", report_path)

    logger.info("Entraînement terminé avec succès")
    return 0


if __name__ == "__main__":
    sys.exit(main())
