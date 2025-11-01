import sys
import logging
from datetime import datetime

# Assure l'import du module Sleeper dans Production
from pathlib import Path
sys.path.append(str(Path(__file__).parent))

import Sleeper  # noqa: E402


def run_once():
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    config = Sleeper.load_config()
    if not config:
        print("Config introuvable. Abandon.")
        return 1

    paires = config.get('PAIRES', [])
    timeframes = config.get('TIMEFRAMES', [])
    if not paires or not timeframes:
        print("Aucune paire/timeframe dans la config. Abandon.")
        return 1

    print(f"Exécution unique à {datetime.now().strftime('%H:%M:%S')} pour {len(paires)} paires x {len(timeframes)} TF…")

    # Exécuter la stratégie une fois pour chaque paire/timeframe
    for symbol in paires:
        for tf in timeframes:
            try:
                Sleeper.apply_strategy_with_config(symbol, tf)
            except Exception as e:
                logging.error(f"Erreur apply_strategy_with_config({symbol}, {tf}): {e}")

    # Fusionner les fichiers en attente, nettoyage
    try:
        merges = Sleeper.merge_pending_signals(max_age_seconds=0)
        if merges:
            logging.info(f"Fusions exécutées: {merges}")
    except Exception as e:
        logging.error(f"Erreur merge_pending_signals: {e}")

    try:
        Sleeper.cleanup_orphaned_files()
    except Exception as e:
        logging.error(f"Erreur cleanup_orphaned_files: {e}")

    print("Terminé.")
    return 0


if __name__ == "__main__":
    sys.exit(run_once())
