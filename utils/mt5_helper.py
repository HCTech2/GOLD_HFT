#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Fonctions utilitaires pour MetaTrader 5
"""

import MetaTrader5 as mt5
import time
from typing import Optional, Callable, Any
import logging

logger = logging.getLogger(__name__)


def retry_on_failure(max_attempts: int = 3, delay: float = 1.0):
    """Décorateur pour retenter une fonction en cas d'échec"""
    
    def decorator(func: Callable) -> Callable:
        def wrapper(*args, **kwargs) -> Any:
            last_exception = None
            
            for attempt in range(1, max_attempts + 1):
                try:
                    return func(*args, **kwargs)
                except Exception as e:
                    last_exception = e
                    if attempt < max_attempts:
                        logger.warning(f"{func.__name__} échec (tentative {attempt}/{max_attempts}): {e}")
                        time.sleep(delay)
                    else:
                        logger.error(f"{func.__name__} échec après {max_attempts} tentatives: {e}")
            
            raise last_exception
        
        return wrapper
    return decorator


@retry_on_failure(max_attempts=3, delay=0.5)
def get_symbol_info_safe(symbol: str) -> Optional[mt5.SymbolInfo]:
    """Récupère les informations d'un symbole avec retry"""
    info = mt5.symbol_info(symbol)
    if info is None:
        raise ValueError(f"Symbole {symbol} non trouvé")
    return info


@retry_on_failure(max_attempts=3, delay=0.5)
def get_tick_safe(symbol: str) -> Optional[mt5.Tick]:
    """Récupère le dernier tick avec retry"""
    tick = mt5.symbol_info_tick(symbol)
    if tick is None:
        raise ValueError(f"Impossible de récupérer le tick pour {symbol}")
    return tick


def format_price(price: float, symbol: str) -> str:
    """Formate un prix selon les décimales du symbole"""
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return f"{price:.2f}"
    
    digits = symbol_info.digits
    return f"{price:.{digits}f}"


def calculate_position_value(symbol: str, volume: float, price: float) -> Optional[float]:
    """Calcule la valeur d'une position"""
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return None
    
    contract_size = symbol_info.trade_contract_size
    return volume * contract_size * price


def calculate_pip_value(symbol: str, volume: float) -> Optional[float]:
    """Calcule la valeur d'un pip pour un volume donné"""
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return None
    
    point = symbol_info.point
    contract_size = symbol_info.trade_contract_size
    
    # Pour XAU/USD, 1 pip = 0.01
    pip_size = 10 * point  # 10 points = 1 pip
    return volume * contract_size * pip_size


def get_account_summary() -> dict:
    """Retourne un résumé du compte"""
    account = mt5.account_info()
    if account is None:
        return {}
    
    return {
        'login': account.login,
        'server': account.server,
        'balance': account.balance,
        'equity': account.equity,
        'profit': account.profit,
        'margin': account.margin,
        'margin_free': account.margin_free,
        'margin_level': account.margin_level if account.margin_level else 0,
        'leverage': account.leverage,
    }


def check_trading_allowed(symbol: str) -> tuple[bool, str]:
    """Vérifie si le trading est autorisé pour un symbole"""
    symbol_info = mt5.symbol_info(symbol)
    if symbol_info is None:
        return False, f"Symbole {symbol} non trouvé"
    
    if not symbol_info.visible:
        return False, f"Symbole {symbol} non visible (activer dans Market Watch)"
    
    if symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_DISABLED:
        return False, f"Trading désactivé pour {symbol}"
    
    if symbol_info.trade_mode == mt5.SYMBOL_TRADE_MODE_CLOSEONLY:
        return False, f"Fermetures uniquement pour {symbol}"
    
    # Vérifier les horaires de trading
    now = mt5.symbol_info_tick(symbol).time if mt5.symbol_info_tick(symbol) else 0
    if now == 0:
        return False, f"Impossible de récupérer l'heure du serveur"
    
    return True, "Trading autorisé"


def get_positions_summary(symbol: Optional[str] = None) -> dict:
    """Retourne un résumé des positions"""
    if symbol:
        positions = mt5.positions_get(symbol=symbol)
    else:
        positions = mt5.positions_get()
    
    if positions is None or len(positions) == 0:
        return {
            'count': 0,
            'total_volume': 0.0,
            'total_profit': 0.0,
            'long_count': 0,
            'short_count': 0,
        }
    
    long_count = sum(1 for p in positions if p.type == mt5.ORDER_TYPE_BUY)
    short_count = sum(1 for p in positions if p.type == mt5.ORDER_TYPE_SELL)
    total_volume = sum(p.volume for p in positions)
    total_profit = sum(p.profit for p in positions)
    
    return {
        'count': len(positions),
        'total_volume': total_volume,
        'total_profit': total_profit,
        'long_count': long_count,
        'short_count': short_count,
    }


def format_duration(seconds: float) -> str:
    """Formate une durée en secondes en texte lisible"""
    if seconds < 1:
        return f"{seconds*1000:.1f}ms"
    elif seconds < 60:
        return f"{seconds:.1f}s"
    elif seconds < 3600:
        minutes = int(seconds // 60)
        secs = int(seconds % 60)
        return f"{minutes}m {secs}s"
    else:
        hours = int(seconds // 3600)
        minutes = int((seconds % 3600) // 60)
        return f"{hours}h {minutes}m"
