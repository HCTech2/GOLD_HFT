#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Configuration du système de logging
"""

import logging
import sys
from pathlib import Path
from datetime import datetime


def setup_logging(log_level: str = "INFO", log_file: str = None) -> logging.Logger:
    """
    Configure le système de logging pour l'application
    
    Args:
        log_level: Niveau de log (DEBUG, INFO, WARNING, ERROR, CRITICAL)
        log_file: Chemin du fichier de log (optionnel)
    
    Returns:
        Logger configuré
    """
    
    # Créer le logger racine
    logger = logging.getLogger()
    logger.setLevel(getattr(logging, log_level.upper()))
    
    # Supprimer les handlers existants
    logger.handlers.clear()
    
    # Format détaillé
    formatter = logging.Formatter(
        '%(asctime)s.%(msecs)03d | %(levelname)-8s | %(name)-20s | %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    
    # Handler console (stdout)
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setLevel(getattr(logging, log_level.upper()))
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    # Handler fichier (si spécifié)
    if log_file:
        log_path = Path(log_file)
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        file_handler = logging.FileHandler(log_file, encoding='utf-8')
        file_handler.setLevel(logging.DEBUG)  # Tout écrire dans le fichier
        file_handler.setFormatter(formatter)
        logger.addHandler(file_handler)
        
        logger.info(f"Logs écrits dans: {log_file}")
    
    return logger


def get_logger(name: str) -> logging.Logger:
    """Retourne un logger avec le nom spécifié"""
    return logging.getLogger(name)


class LoggerContext:
    """Context manager pour logs temporaires"""
    
    def __init__(self, logger: logging.Logger, prefix: str):
        self.logger = logger
        self.prefix = prefix
        self.start_time = None
    
    def __enter__(self):
        self.start_time = datetime.now()
        self.logger.info(f"[{self.prefix}] Début")
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        duration = (datetime.now() - self.start_time).total_seconds()
        if exc_type is None:
            self.logger.info(f"[{self.prefix}] Terminé en {duration:.3f}s")
        else:
            self.logger.error(f"[{self.prefix}] Erreur après {duration:.3f}s: {exc_val}")
        return False
