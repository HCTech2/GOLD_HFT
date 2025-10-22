"""
Gestionnaire de sauvegarde/chargement automatique des paramètres utilisateur
"""
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any

logger = logging.getLogger(__name__)

class SettingsManager:
    """Gère la persistance des paramètres utilisateur"""
    
    def __init__(self, settings_file: str = "config/user_settings.json"):
        self.settings_file = Path(settings_file)
        self.settings: Dict[str, Any] = {}
        
    def load_settings(self) -> Dict[str, Any]:
        """
        Charge les paramètres sauvegardés
        
        Returns:
            Dict contenant les paramètres, vide si fichier inexistant
        """
        if not self.settings_file.exists():
            logger.info(f"📂 Aucune sauvegarde trouvée dans {self.settings_file}")
            return {}
            
        try:
            with open(self.settings_file, 'r', encoding='utf-8') as f:
                self.settings = json.load(f)
            logger.info(f"✅ Paramètres chargés depuis {self.settings_file}")
            logger.info(f"   - {len(self.settings)} paramètres restaurés")
            return self.settings
            
        except Exception as e:
            logger.error(f"❌ Erreur lors du chargement des paramètres: {e}")
            return {}
    
    def save_settings(self, settings: Dict[str, Any]) -> bool:
        """
        Sauvegarde les paramètres actuels
        
        Args:
            settings: Dictionnaire des paramètres à sauvegarder
            
        Returns:
            True si succès, False sinon
        """
        try:
            # Créer le répertoire si nécessaire
            self.settings_file.parent.mkdir(parents=True, exist_ok=True)
            
            # Sauvegarder avec indentation pour lisibilité
            with open(self.settings_file, 'w', encoding='utf-8') as f:
                json.dump(settings, f, indent=2, ensure_ascii=False)
            
            logger.info(f"💾 Paramètres sauvegardés dans {self.settings_file}")
            logger.info(f"   - {len(settings)} paramètres enregistrés")
            return True
            
        except Exception as e:
            logger.error(f"❌ Erreur lors de la sauvegarde des paramètres: {e}")
            return False
    
    def get_setting(self, key: str, default: Any = None) -> Any:
        """Récupère une valeur spécifique"""
        return self.settings.get(key, default)
    
    def set_setting(self, key: str, value: Any) -> None:
        """Définit une valeur spécifique"""
        self.settings[key] = value
    
    def get_all_settings(self) -> Dict[str, Any]:
        """Retourne tous les paramètres"""
        return self.settings.copy()
    
    def clear_settings(self) -> bool:
        """Efface tous les paramètres sauvegardés"""
        try:
            if self.settings_file.exists():
                self.settings_file.unlink()
                logger.info(f"🗑️ Paramètres effacés: {self.settings_file}")
            self.settings = {}
            return True
        except Exception as e:
            logger.error(f"❌ Erreur lors de l'effacement: {e}")
            return False


# Paramètres sauvegardables (whitelist)
SAVEABLE_PARAMS = {
    # Protections Circuit Breaker
    'circuit_breaker_enabled',
    'risk_daily_loss_enabled',
    'risk_max_daily_loss',
    'risk_daily_trades_enabled',
    'risk_max_daily_trades',
    'risk_drawdown_enabled',
    'risk_max_drawdown_percent',
    'risk_consecutive_losses_enabled',
    'risk_max_consecutive_losses',
    'risk_hourly_loss_enabled',
    'risk_max_hourly_loss',
    'risk_position_size_enabled',
    'risk_max_position_size',
    
    # Trading
    'max_positions',
    'max_simultaneous_orders',
    'min_seconds_between_trades',
    'kill_zone_enabled',
    
    # STC
    'stc_threshold_buy',
    'stc_threshold_sell',
    
    # HTF
    'mtf_filter_enabled',
    'mtf_require_alignment',
    'mtf_alignment_threshold',
    
    # ML
    'ml_enabled',
    
    # Profit réactif
    'reactive_profit_enabled',
    'profit_threshold_per_position',
    'profit_threshold_cumulative',
    
    # Volumes
    'base_volume',
    'volume_min',
    'volume_max',
    
    # SL/TP
    'base_sl_distance',
    'base_tp_distance',
}


def extract_saveable_config(config) -> Dict[str, Any]:
    """
    Extrait les paramètres sauvegardables d'un objet TradingConfig
    
    Args:
        config: Instance de TradingConfig
        
    Returns:
        Dict contenant uniquement les paramètres whitelistés
    """
    settings = {}
    for param in SAVEABLE_PARAMS:
        if hasattr(config, param):
            value = getattr(config, param)
            settings[param] = value
    
    return settings


def apply_saved_settings(config, settings: Dict[str, Any]) -> int:
    """
    Applique les paramètres sauvegardés à un objet TradingConfig
    
    Args:
        config: Instance de TradingConfig à modifier
        settings: Dict des paramètres sauvegardés
        
    Returns:
        Nombre de paramètres appliqués
    """
    applied = 0
    
    for key, value in settings.items():
        if key in SAVEABLE_PARAMS and hasattr(config, key):
            try:
                setattr(config, key, value)
                applied += 1
                logger.debug(f"   ✓ {key} = {value}")
            except Exception as e:
                logger.warning(f"   ✗ Impossible d'appliquer {key}: {e}")
    
    return applied
