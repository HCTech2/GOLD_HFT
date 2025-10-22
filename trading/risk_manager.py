#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Gestionnaire de risque avec Circuit Breaker et protections avancées
"""

import logging
import MetaTrader5 as mt5
from datetime import datetime, timedelta
from typing import Dict, List, Optional
from dataclasses import dataclass

from config.trading_config import TradingConfig, OrderType
from models.data_models import TradeRecord

logger = logging.getLogger(__name__)


@dataclass
class RiskLimits:
    """Limites de risque configurables"""
    max_daily_loss: float = 500.0  # Perte journalière maximale en $
    max_daily_trades: int = 50  # Nombre max de trades par jour
    max_consecutive_losses: int = 5  # Nombre max de pertes consécutives
    max_drawdown_percent: float = 10.0  # Drawdown max en % du capital initial
    max_correlated_positions: int = 3  # Positions max dans la même direction
    max_portfolio_risk_percent: float = 20.0  # Risque max du portefeuille en %
    cooldown_after_loss_streak_minutes: int = 30  # Pause après série de pertes


class RiskManager:
    """
    Gestionnaire de risque avec Circuit Breaker
    
    Protections:
    - Limite de pertes journalières
    - Limite de trades journaliers
    - Détection série de pertes consécutives
    - Protection contre drawdown excessif
    - Limite positions corrélées
    - Cooldown automatique après pertes
    """
    
    def __init__(self, config: TradingConfig, limits: Optional[RiskLimits] = None):
        self.config = config
        self.limits = limits or RiskLimits()
        
        # État du circuit breaker
        self.circuit_breaker_active = False
        self.circuit_breaker_reason = ""
        self.circuit_breaker_activated_at: Optional[datetime] = None
        
        # Statistiques journalières
        self.daily_pnl = 0.0
        self.daily_trades_count = 0
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        
        # Statistiques de pertes
        self.consecutive_losses = 0
        self.last_loss_time: Optional[datetime] = None
        self.in_cooldown = False
        self.cooldown_until: Optional[datetime] = None
        
        # Capital initial
        self.initial_capital = config.initial_portfolio
        self.peak_capital = config.initial_portfolio
        
        logger.info("=" * 80)
        logger.info("🛡️ RISK MANAGER INITIALISÉ")
        
        if not config.circuit_breaker_enabled:
            logger.warning("⚠️ CIRCUIT BREAKER DÉSACTIVÉ - Aucune protection active")
        else:
            logger.info("✅ Circuit Breaker ACTIVÉ - Protections:")
            
            if config.risk_daily_loss_enabled:
                logger.info(f"   ✓ Perte journalière: Max {self.limits.max_daily_loss}$")
            else:
                logger.info(f"   ✗ Perte journalière: DÉSACTIVÉE")
            
            if config.risk_daily_trades_enabled:
                logger.info(f"   ✓ Trades journaliers: Max {self.limits.max_daily_trades}")
            else:
                logger.info(f"   ✗ Trades journaliers: DÉSACTIVÉ")
            
            if config.risk_consecutive_losses_enabled:
                logger.info(f"   ✓ Pertes consécutives: Max {self.limits.max_consecutive_losses} (cooldown {self.limits.cooldown_after_loss_streak_minutes}min)")
            else:
                logger.info(f"   ✗ Pertes consécutives: DÉSACTIVÉ")
            
            if config.risk_drawdown_enabled:
                logger.info(f"   ✓ Drawdown: Max {self.limits.max_drawdown_percent}%")
            else:
                logger.info(f"   ✗ Drawdown: DÉSACTIVÉ")
            
            if config.risk_correlation_enabled:
                logger.info(f"   ✓ Corrélation: Max {self.limits.max_correlated_positions} positions/direction")
            else:
                logger.info(f"   ✗ Corrélation: DÉSACTIVÉE")
            
            if config.risk_portfolio_enabled:
                logger.info(f"   ✓ Risque portefeuille: Max {self.limits.max_portfolio_risk_percent}%")
            else:
                logger.info(f"   ✗ Risque portefeuille: DÉSACTIVÉ")
        
        logger.info("=" * 80)
    
    def check_can_trade(self, order_type: OrderType, open_positions: List[TradeRecord]) -> tuple[bool, str]:
        """
        Vérifie si un nouveau trade est autorisé
        
        Returns:
            (can_trade, reason) - True si autorisé, False sinon avec raison
        """
        
        # Si Circuit Breaker désactivé globalement, autoriser
        if not self.config.circuit_breaker_enabled:
            return True, "✅ Circuit Breaker désactivé"
        
        # Réinitialiser les stats journalières si nouveau jour
        self._check_daily_reset()
        
        # 1. Vérifier circuit breaker
        if self.circuit_breaker_active:
            return False, f"⛔ CIRCUIT BREAKER ACTIF: {self.circuit_breaker_reason}"
        
        # 2. Vérifier cooldown après série de pertes (si activé)
        if self.config.risk_consecutive_losses_enabled and self.in_cooldown:
            if datetime.now() < self.cooldown_until:
                remaining = (self.cooldown_until - datetime.now()).total_seconds() / 60
                return False, f"🕐 COOLDOWN ACTIF: {remaining:.1f} min restantes (série de {self.consecutive_losses} pertes)"
            else:
                # Sortir du cooldown
                self.in_cooldown = False
                self.cooldown_until = None
                logger.info("✅ Fin du cooldown - Trading réactivé")
        
        # 3. Vérifier perte journalière (si activé)
        if self.config.risk_daily_loss_enabled:
            account_info = mt5.account_info()
            if account_info:
                daily_pnl = self._calculate_daily_pnl(account_info)
                
                if daily_pnl <= -self.limits.max_daily_loss:
                    self._activate_circuit_breaker(
                        f"Perte journalière {daily_pnl:.2f}$ atteinte (limite: -{self.limits.max_daily_loss}$)"
                    )
                    return False, f"⛔ PERTE JOURNALIÈRE LIMITE ATTEINTE: {daily_pnl:.2f}$"
        
        # 4. Vérifier nombre de trades journaliers (si activé)
        if self.config.risk_daily_trades_enabled:
            if self.daily_trades_count >= self.limits.max_daily_trades:
                return False, f"📊 LIMITE TRADES JOURNALIERS ATTEINTE: {self.daily_trades_count}/{self.limits.max_daily_trades}"
        
        # 5. Vérifier drawdown (si activé)
        if self.config.risk_drawdown_enabled:
            account_info = mt5.account_info()
            if account_info:
                current_capital = account_info.equity
                drawdown_percent = ((self.peak_capital - current_capital) / self.peak_capital) * 100
                
                if drawdown_percent > self.limits.max_drawdown_percent:
                    self._activate_circuit_breaker(
                        f"Drawdown {drawdown_percent:.1f}% dépasse la limite {self.limits.max_drawdown_percent}%"
                    )
                    return False, f"⛔ DRAWDOWN EXCESSIF: {drawdown_percent:.1f}%"
                
                # Mettre à jour le pic de capital
                if current_capital > self.peak_capital:
                    self.peak_capital = current_capital
        
        # 6. Vérifier corrélation des positions (si activé)
        if self.config.risk_correlation_enabled:
            same_direction_count = sum(1 for pos in open_positions if pos.order_type == order_type)
            
            if same_direction_count >= self.limits.max_correlated_positions:
                return False, f"🔗 TROP DE POSITIONS CORRÉLÉES: {same_direction_count} positions {order_type.name}"
        
        # 7. Vérifier risque total du portefeuille (si activé)
        if self.config.risk_portfolio_enabled:
            account_info = mt5.account_info()
            if account_info:
                total_risk = self._calculate_total_portfolio_risk(open_positions, account_info)
                
                if total_risk > self.limits.max_portfolio_risk_percent:
                    return False, f"⚠️ RISQUE PORTEFEUILLE TROP ÉLEVÉ: {total_risk:.1f}%"
        
        # Tout est OK
        return True, "✅ Conditions de trading respectées"
    
    def record_trade_opened(self, order_type: OrderType) -> None:
        """Enregistre l'ouverture d'un trade"""
        self.daily_trades_count += 1
        logger.debug(f"[RISK] Trade ouvert ({order_type.name}) - Total journalier: {self.daily_trades_count}")
    
    def record_trade_closed(self, trade: TradeRecord) -> None:
        """Enregistre la clôture d'un trade et met à jour les statistiques"""
        
        profit = trade.profit if trade.profit is not None else 0.0
        self.daily_pnl += profit
        
        # Gérer les pertes consécutives (seulement si activé)
        if self.config.risk_consecutive_losses_enabled:
            if profit < 0:
                self.consecutive_losses += 1
                self.last_loss_time = datetime.now()
                
                logger.warning(f"[RISK] Perte enregistrée: {profit:.2f}$ - Série: {self.consecutive_losses} pertes consécutives")
                
                # Activer cooldown si trop de pertes
                if self.consecutive_losses >= self.limits.max_consecutive_losses:
                    self._activate_cooldown()
            else:
                # Réinitialiser le compteur de pertes
                if self.consecutive_losses > 0:
                    logger.info(f"[RISK] ✅ Perte consécutive réinitialisée après gain de {profit:.2f}$")
                self.consecutive_losses = 0
        
        logger.debug(f"[RISK] P&L journalier: {self.daily_pnl:.2f}$ | Trades: {self.daily_trades_count}")
    
    def _activate_circuit_breaker(self, reason: str) -> None:
        """Active le circuit breaker"""
        self.circuit_breaker_active = True
        self.circuit_breaker_reason = reason
        self.circuit_breaker_activated_at = datetime.now()
        
        logger.critical("=" * 80)
        logger.critical("⛔⛔⛔ CIRCUIT BREAKER ACTIVÉ ⛔⛔⛔")
        logger.critical(f"Raison: {reason}")
        logger.critical(f"Heure: {self.circuit_breaker_activated_at.strftime('%Y-%m-%d %H:%M:%S')}")
        logger.critical("Trading automatiquement STOPPÉ")
        logger.critical("=" * 80)
    
    def _activate_cooldown(self) -> None:
        """Active un cooldown après série de pertes"""
        self.in_cooldown = True
        self.cooldown_until = datetime.now() + timedelta(minutes=self.limits.cooldown_after_loss_streak_minutes)
        
        logger.warning("=" * 80)
        logger.warning(f"🕐 COOLDOWN ACTIVÉ: {self.consecutive_losses} pertes consécutives")
        logger.warning(f"Trading suspendu jusqu'à {self.cooldown_until.strftime('%H:%M:%S')}")
        logger.warning(f"Durée: {self.limits.cooldown_after_loss_streak_minutes} minutes")
        logger.warning("=" * 80)
    
    def deactivate_circuit_breaker(self) -> None:
        """Désactive manuellement le circuit breaker"""
        if self.circuit_breaker_active:
            logger.warning("🔓 Circuit Breaker désactivé manuellement")
            self.circuit_breaker_active = False
            self.circuit_breaker_reason = ""
            self.circuit_breaker_activated_at = None
    
    def reset_daily_stats(self) -> None:
        """Réinitialise les statistiques journalières"""
        logger.info(f"[RISK] Réinitialisation stats journalières - P&L: {self.daily_pnl:.2f}$, Trades: {self.daily_trades_count}")
        self.daily_pnl = 0.0
        self.daily_trades_count = 0
        self.daily_reset_time = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    
    def _check_daily_reset(self) -> None:
        """Vérifie si on doit réinitialiser les stats (nouveau jour)"""
        now = datetime.now()
        if now.date() > self.daily_reset_time.date():
            self.reset_daily_stats()
    
    def _calculate_daily_pnl(self, account_info) -> float:
        """Calcule le P&L journalier depuis MT5"""
        # Récupérer les deals du jour
        today_start = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
        deals = mt5.history_deals_get(today_start, datetime.now())
        
        if not deals:
            return 0.0
        
        daily_profit = sum(deal.profit for deal in deals if deal.magic == 234000)
        return daily_profit
    
    def _calculate_total_portfolio_risk(self, open_positions: List[TradeRecord], account_info) -> float:
        """Calcule le risque total du portefeuille en %"""
        if not open_positions:
            return 0.0
        
        total_risk = 0.0
        
        for pos in open_positions:
            # Calculer le risque par position (distance au SL * volume)
            risk_per_position = abs(pos.entry_price - pos.stop_loss) * pos.volume * 100
            total_risk += risk_per_position
        
        # Convertir en pourcentage du capital
        risk_percent = (total_risk / account_info.equity) * 100
        return risk_percent
    
    def get_risk_status(self) -> Dict:
        """Retourne l'état actuel du gestionnaire de risque"""
        account_info = mt5.account_info()
        
        status = {
            'circuit_breaker_active': self.circuit_breaker_active,
            'circuit_breaker_reason': self.circuit_breaker_reason,
            'in_cooldown': self.in_cooldown,
            'cooldown_remaining_minutes': 0,
            'daily_pnl': self.daily_pnl,
            'daily_trades_count': self.daily_trades_count,
            'consecutive_losses': self.consecutive_losses,
            'current_drawdown_percent': 0.0,
            'can_trade': not self.circuit_breaker_active and not self.in_cooldown,
        }
        
        # Calculer temps restant du cooldown
        if self.in_cooldown and self.cooldown_until:
            remaining = (self.cooldown_until - datetime.now()).total_seconds() / 60
            status['cooldown_remaining_minutes'] = max(0, remaining)
        
        # Calculer drawdown actuel
        if account_info:
            current_capital = account_info.equity
            drawdown = ((self.peak_capital - current_capital) / self.peak_capital) * 100
            status['current_drawdown_percent'] = drawdown
        
        return status
    
    def get_risk_metrics(self) -> str:
        """Retourne les métriques de risque formatées"""
        status = self.get_risk_status()
        
        lines = [
            "🛡️ === MÉTRIQUES DE RISQUE ===",
            f"Circuit Breaker: {'⛔ ACTIF' if status['circuit_breaker_active'] else '✅ Inactif'}",
        ]
        
        if status['circuit_breaker_active']:
            lines.append(f"   Raison: {status['circuit_breaker_reason']}")
        
        if status['in_cooldown']:
            lines.append(f"Cooldown: 🕐 ACTIF ({status['cooldown_remaining_minutes']:.1f} min restantes)")
        
        lines.extend([
            f"P&L Journalier: {status['daily_pnl']:.2f}$ (limite: -{self.limits.max_daily_loss}$)",
            f"Trades Journaliers: {status['daily_trades_count']}/{self.limits.max_daily_trades}",
            f"Pertes Consécutives: {status['consecutive_losses']}/{self.limits.max_consecutive_losses}",
            f"Drawdown: {status['current_drawdown_percent']:.1f}% (max: {self.limits.max_drawdown_percent}%)",
            f"Statut Trading: {'✅ AUTORISÉ' if status['can_trade'] else '⛔ BLOQUÉ'}",
        ])
        
        return "\n".join(lines)
