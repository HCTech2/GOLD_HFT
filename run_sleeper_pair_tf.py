import sys
import os
import logging
from pathlib import Path
import pandas as pd
from datetime import datetime, timedelta, timezone

# Import du module Sleeper
sys.path.append(str(Path(__file__).parent))
import Sleeper  # noqa: E402


def _compute_last_month_range(now_utc: datetime):
    """
    Retourne (start_date_str, end_date_str) pour le dernier mois glissant en UTC.
    Format YYYY-MM-DD. end inclusif.
    """
    end_date = now_utc.date()
    start_date = end_date - timedelta(days=30)
    return start_date.strftime('%Y-%m-%d'), end_date.strftime('%Y-%m-%d')


def run_for(symbol: str, timeframe: str, last_month: bool = False) -> int:
    logging.basicConfig(level=logging.INFO, format='%(asctime)s [%(levelname)s] %(message)s')
    print(f"Lancement Sleeper pour {symbol} / {timeframe} …")

    # Option: limiter au dernier mois via variables d'environnement lues par Sleeper.get_all_csvs
    prev_start = os.environ.get('SLEEPER_START_DATE')
    prev_end = os.environ.get('SLEEPER_END_DATE')
    if last_month:
        s, e = _compute_last_month_range(datetime.now(timezone.utc))
        os.environ['SLEEPER_START_DATE'] = s
        os.environ['SLEEPER_END_DATE'] = e
        logging.info(f"Fenêtre limitée au dernier mois: {s} -> {e}")

    try:
        Sleeper.apply_strategy_with_config(symbol, timeframe)
    except Exception as e:
        logging.error(f"apply_strategy_with_config a échoué: {e}")
        return 1

    # Fusion et nettoyage
    try:
        merges = Sleeper.merge_pending_signals(max_age_seconds=0)
        if merges:
            logging.info(f"Fusions effectuées: {merges}")
    except Exception as e:
        logging.error(f"Post-traitement (merge) a échoué: {e}")

    # Résumé des signaux
    target_file = os.path.normpath(f"D:/Prototype/Production/DATA/Live/Signaux/.Resultat/{symbol}/{timeframe}/Signaux_{symbol}_{timeframe}.csv")
    if os.path.exists(target_file):
        try:
            df = pd.read_csv(target_file)
            # Filtrer le résumé sur la même fenêtre si last_month
            if last_month:
                s = os.environ.get('SLEEPER_START_DATE')
                e = os.environ.get('SLEEPER_END_DATE')
                if s and e and 'Date' in df.columns:
                    df['Date'] = pd.to_datetime(df['Date'], utc=True, errors='coerce')
                    mask = (df['Date'] >= pd.Timestamp(s, tz='UTC')) & (df['Date'] <= pd.Timestamp(e + ' 23:59:59', tz='UTC'))
                    df = df.loc[mask]
            n = len(df)
            buys = (df.get('BUY/SELL') == 'BUY').sum() if 'BUY/SELL' in df.columns else None
            sells = (df.get('BUY/SELL') == 'SELL').sum() if 'BUY/SELL' in df.columns else None
            print(f"Fichier: {target_file}")
            print(f"Total signaux: {n}; BUY: {buys}; SELL: {sells}")
            print(df.tail(5).to_string(index=False))
        except Exception as e:
            logging.error(f"Lecture du fichier de signaux a échoué: {e}")
    else:
        print(f"Aucun fichier de signaux trouvé pour {symbol}/{timeframe}")

    return 0


if __name__ == "__main__":
    # Utilisation: python run_sleeper_pair_tf.py [SYMBOL] [TIMEFRAME] [--last-month]
    # Exemples:
    #   python run_sleeper_pair_tf.py USDCAD M5 --last-month
    #   python run_sleeper_pair_tf.py .WTICrude M5
    symbol = ".WTICrude"
    timeframe = "M5"
    last_month = False
    args = [a for a in sys.argv[1:] if a]
    if len(args) >= 1 and not args[0].startswith('-'):
        symbol = args[0]
    if len(args) >= 2 and not args[1].startswith('-'):
        timeframe = args[1]
    if any(a == "--last-month" for a in args[2:] + ([] if len(args) < 2 else [])) or any(a == "--last-month" for a in args if a.startswith('--')):
        last_month = True
    sys.exit(run_for(symbol, timeframe, last_month=last_month))
