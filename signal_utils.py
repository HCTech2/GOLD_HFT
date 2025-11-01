"""
Chargement centralisé des fichiers de signaux avec tolérance aux erreurs et cache mtime.
"""
from __future__ import annotations
import os
import json
import shutil
import logging
import time
from datetime import datetime
from collections import OrderedDict
import pandas as pd
from typing import List, Optional

# ✅ OPTIMISATION MÉMOIRE: Cache LRU avec timestamp et limite de taille
_FILE_CACHE: OrderedDict[str, dict] = OrderedDict()
_CACHE_MAX_SIZE = 100  # Max 100 fichiers en cache (~10-20MB)
_CACHE_MAX_AGE_SECONDS = 3600  # Expire après 1h


def _cleanup_cache():
    """Purge les entrées obsolètes du cache"""
    now = time.time()
    keys_to_remove = []
    
    # Supprimer les entrées expirées
    for key, entry in _FILE_CACHE.items():
        if now - entry.get('cached_at', 0) > _CACHE_MAX_AGE_SECONDS:
            keys_to_remove.append(key)
    
    for key in keys_to_remove:
        _FILE_CACHE.pop(key, None)
    
    # Limiter la taille du cache (LRU - supprime les plus anciennes)
    while len(_FILE_CACHE) > _CACHE_MAX_SIZE:
        _FILE_CACHE.popitem(last=False)
    
    if keys_to_remove:
        logging.debug(f"🧹 Cache signaux purgé: {len(keys_to_remove)} entrées expirées")


def _build_signal_file_path(pair: str, timeframe: str) -> str:
    try:
        with open(os.path.join("D:", "Prototype", "Production", "config.json"), "r", encoding="utf-8") as f:
            cfg = json.load(f)
        base = cfg.get("signal_file_dir")
        if base:
            # config uses placeholders {pair}/{timeframe}/
            base_dir = base.format(pair=pair, timeframe=timeframe)
            return os.path.join(base_dir, f"Signaux_{pair}_{timeframe}.csv").replace("\\", "/")
    except Exception:
        pass
    # Fallback par défaut
    return os.path.join("D:/Prototype/Production/DATA/Live/Signaux/.Resultat", pair, timeframe, f"Signaux_{pair}_{timeframe}.csv")


def load_last_signals(pair: str, timeframe: str, limit: int = 1, active_strategies: Optional[List[str]] = None) -> pd.DataFrame:
    """
    Charge les derniers signaux pour une paire/TF depuis le dossier live.
    - Tolère fichiers vides ou mal formés (plusieurs encodages, skip des lignes invalides)
    - Met en cache par mtime pour éviter relecture constante
    - Option de filtrage par stratégies si fourni
    """
    signal_file = _build_signal_file_path(pair, timeframe)
    try:
        if not os.path.exists(signal_file):
            logging.error(f"Le fichier {signal_file} n'existe pas.")
            return pd.DataFrame()
        if os.path.getsize(signal_file) == 0:
            logging.warning(f"Le fichier {signal_file} existe mais est vide.")
            return pd.DataFrame()
    except Exception as e:
        logging.error(f"Accès au fichier {signal_file} impossible: {e}")
        return pd.DataFrame()

    # Cache mtime
    try:
        mtime = os.path.getmtime(signal_file)
    except Exception:
        mtime = None
    if mtime is not None:
        entry = _FILE_CACHE.get(signal_file)
        if entry and entry.get("mtime") == mtime:
            cached = entry.get("df")
            # Mettre à jour l'ordre LRU (move to end)
            _FILE_CACHE.move_to_end(signal_file)
            return cached.head(limit) if cached is not None else pd.DataFrame()

    methods = [
        lambda: pd.read_csv(signal_file, encoding="utf-8"),
        lambda: pd.read_csv(signal_file, encoding="iso-8859-1"),
        lambda: pd.read_csv(signal_file, encoding="utf-8", on_bad_lines="skip"),
        lambda: pd.read_csv(signal_file, encoding="iso-8859-1", on_bad_lines="skip"),
        lambda: pd.read_csv(signal_file, encoding="utf-8", sep=",", on_bad_lines="skip"),
        lambda: pd.read_csv(signal_file, encoding="utf-8", engine="python"),
        lambda: pd.read_fwf(signal_file, encoding="utf-8"),
    ]

    df = pd.DataFrame()
    last_error = None
    for fn in methods:
        try:
            df = fn()
            if not df.empty:
                break
        except pd.errors.EmptyDataError:
            last_error = "empty"
            continue
        except pd.errors.ParserError as e:
            last_error = f"parser: {e}"
            continue
        except Exception as e:
            last_error = str(e)
            continue

    if df.empty:
        logging.error(f"Impossible de lire {signal_file}: {last_error}")
        try:
            backup_path = f"{signal_file}.corrupted.{datetime.now().strftime('%Y%m%d%H%M%S')}"
            shutil.copy2(signal_file, backup_path)
            logging.warning(f"Fichier corrompu sauvegardé: {backup_path}")
            with open(signal_file, "w", encoding="utf-8") as f:
                f.write("TAG,Date,Paire,Prix,BUY/SELL,Strategie\n")
        except Exception as e:
            logging.error(f"Backup/Reset échoué pour {signal_file}: {e}")
        return pd.DataFrame()

    required = ["TAG", "Date", "Paire", "Prix", "BUY/SELL"]
    missing = [c for c in required if c not in df.columns]
    if missing:
        logging.error(f"Colonnes manquantes dans {signal_file}: {missing}")
        return pd.DataFrame()

    try:
        df["Date"] = pd.to_datetime(df["Date"], errors="coerce", utc=True)
        df.dropna(subset=["Date"], inplace=True)
        df.drop_duplicates(subset=["Date", "Paire", "BUY/SELL", "Prix"], inplace=True)
        df.sort_values(by="Date", ascending=False, inplace=True)
        if "Strategie" not in df.columns:
            df["Strategie"] = "Inconnu"
        if active_strategies:
            df = df[df["Strategie"].isin(active_strategies)]
    except Exception as e:
        logging.error(f"Nettoyage des signaux échoué pour {signal_file}: {e}")

    if mtime is not None:
        # ✅ AJOUT: Nettoyage périodique du cache
        if len(_FILE_CACHE) > _CACHE_MAX_SIZE * 0.9:
            _cleanup_cache()
        
        _FILE_CACHE[signal_file] = {
            "mtime": mtime, 
            "df": df.copy(),
            "cached_at": time.time()  # ✅ NOUVEAU: timestamp pour expiration
        }
        # Maintenir l'ordre LRU
        _FILE_CACHE.move_to_end(signal_file)

    return df.head(limit) if not df.empty else df
