"""
Utilities for pip calculations and trade management.
"""
import math

def pip_size_from_symbol(point, digits, symbol):
    """
    Détermine la taille d'un "pip" en s'alignant sur le tick (point) du broker.

    Contexte:
    - Pour cette application, 1 pip = 1 tick (la plus petite variation de prix fournie par le broker).
    - Cela supprime les heuristiques basées sur digits (x10) qui peuvent produire des facteurs x10/x100 indésirables.

    Args:
        point (float): Valeur du point MT5 (souvent égale au tick size minimal)
        digits (int): Nombre de décimales du symbole (utilisé uniquement pour fallback)
        symbol (str): Nom du symbole (non utilisé ici)

    Returns:
        float: taille d'un pip (égale au tick/point)
    """
    try:
        # Stratégie: utiliser directement le point comme taille de pip (pip=tick)
        if point and point > 0:
            return float(point)
        # Fallback: si point non disponible, approx avec digits
        if digits is not None and digits >= 0:
            return 10.0 ** (-int(digits))
        # Fallback ultime par sécurité
        return 0.0001
    except Exception:
        # Fallback raisonnable
        try:
            return float(point)
        except Exception:
            return 0.0001

def compute_sl_tp(price, side, sl_pips, tp_pips, pip_size):
    """
    Calculate stop loss and take profit prices based on trader's logic from Balance_config.json
    
    Args:
        price: Entry price (bid for buy, ask for sell)
        side: 1 for buy, -1 for sell
        sl_pips: Stop loss in pips (default: 50 pips from config)
        tp_pips: Take profit in pips (default: 100 pips from config)
        pip_size: Pip size for the symbol
        
    Returns:
        tuple: (sl_price, tp_price)
    """
    # Configurable risk-reward ratio as per trader's configuration
    # Default values from Balance_config.json: SL=50 pips, TP=100 pips (1:2 ratio)
    sl_distance = sl_pips * pip_size
    tp_distance = tp_pips * pip_size
    
    if side > 0:  # Buy
        sl_price = price - sl_distance
        tp_price = price + tp_distance
    else:  # Sell
        sl_price = price + sl_distance
        tp_price = price - tp_distance
        
    return sl_price, tp_price

def price_from_pips(price, pips, pip_size):
    """
    Convertit un nombre de pips en prix absolu.
    Args:
        price (float): Prix de base
        pips (float): Nombre de pips à ajouter ou retirer
        pip_size (float): Valeur d'un pip pour le symbole
    Returns:
        float: Nouveau prix
    """
    return price + (pips * pip_size)

def trailing_two_stage(current_price, side, open_price, stage1_pips, stage2_pips, pip_size):
    """
    Calculate two-stage trailing stop levels
    
    Args:
        current_price: Current price
        side: 1 for buy, -1 for sell  
        open_price: Position open price
        stage1_pips: First trailing trigger in pips
        stage2_pips: Second trailing trigger in pips
        pip_size: Pip size for symbol
        
    Returns:
        tuple: (break_even_level, trailing1_level, trailing2_level)
    """
    stage1_distance = stage1_pips * pip_size
    stage2_distance = stage2_pips * pip_size
    
    if side > 0:  # Buy position
        be_level = open_price  # Break even level
        t1_level = open_price + stage1_distance  # First trailing trigger
        t2_level = open_price + stage2_distance  # Second trailing trigger
    else:  # Sell position  
        be_level = open_price
        t1_level = open_price - stage1_distance
        t2_level = open_price - stage2_distance
        
    return be_level, t1_level, t2_level
