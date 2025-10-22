# 🛡️ CONFIGURATION CIRCUIT BREAKER

## Vue d'ensemble

Le **Circuit Breaker** dispose maintenant de paramètres **activables/désactivables** individuellement dans `config/trading_config.py`.

Vous pouvez désactiver chaque protection séparément ou désactiver tout le système globalement.

---

## ⚙️ PARAMÈTRES DISPONIBLES

### 🔴 Activation Globale

```python
circuit_breaker_enabled: bool = True  # Master switch pour TOUT le système
```

**Effet:**
- `True` : Les protections actives sont appliquées
- `False` : **TOUTES les protections sont désactivées** (mode dangereux ⚠️)

---

## 🛡️ PROTECTIONS INDIVIDUELLES

### 1️⃣ Protection Perte Journalière

```python
risk_daily_loss_enabled: bool = True     # Activer/Désactiver
risk_max_daily_loss: float = 500.0       # Limite en $
```

**Comportement:**
- ✅ **Activé** : Trading arrêté si pertes du jour dépassent 500$
- ❌ **Désactivé** : Aucune limite de perte journalière

**Recommandation:** ✅ **GARDER ACTIVÉ** (protection essentielle)

---

### 2️⃣ Protection Overtrading

```python
risk_daily_trades_enabled: bool = True   # Activer/Désactiver
risk_max_daily_trades: int = 50          # Nombre max de trades
```

**Comportement:**
- ✅ **Activé** : Trading arrêté après 50 trades dans la journée
- ❌ **Désactivé** : Nombre illimité de trades

**Recommandation:** ✅ **GARDER ACTIVÉ** (évite le revenge trading)

---

### 3️⃣ Protection Pertes Consécutives

```python
risk_consecutive_losses_enabled: bool = True     # Activer/Désactiver
risk_max_consecutive_losses: int = 5             # Nombre max de pertes
risk_cooldown_after_loss_streak_minutes: int = 30  # Durée pause (minutes)
```

**Comportement:**
- ✅ **Activé** : Après 5 pertes d'affilée → Cooldown 30 minutes
- ❌ **Désactivé** : Aucune détection de série de pertes

**Recommandation:** ✅ **GARDER ACTIVÉ** (détecte problèmes stratégie)

---

### 4️⃣ Protection Drawdown

```python
risk_drawdown_enabled: bool = True           # Activer/Désactiver
risk_max_drawdown_percent: float = 10.0      # Drawdown max en %
```

**Comportement:**
- ✅ **Activé** : Trading arrêté si capital baisse de >10% depuis le pic
- ❌ **Désactivé** : Aucune limite de drawdown

**Recommandation:** ✅ **GARDER ACTIVÉ** (protection capital)

---

### 5️⃣ Protection Corrélation

```python
risk_correlation_enabled: bool = True            # Activer/Désactiver
risk_max_correlated_positions: int = 3           # Max positions même direction
```

**Comportement:**
- ✅ **Activé** : Maximum 3 positions BUY ou 3 positions SELL simultanément
- ❌ **Désactivé** : Nombre illimité de positions dans une direction

**Recommandation:** ✅ **GARDER ACTIVÉ** (diversification)

---

### 6️⃣ Protection Risque Portefeuille

```python
risk_portfolio_enabled: bool = True              # Activer/Désactiver
risk_max_portfolio_risk_percent: float = 20.0    # Risque max total en %
```

**Comportement:**
- ✅ **Activé** : Refuse nouveaux trades si risque total >20% du capital
- ❌ **Désactivé** : Aucune limite de risque global

**Recommandation:** ✅ **GARDER ACTIVÉ** (protection globale)

---

## 📋 CONFIGURATIONS RECOMMANDÉES

### 🟢 Configuration CONSERVATIVE (Recommandé)

```python
# Protection maximale
circuit_breaker_enabled: bool = True
risk_daily_loss_enabled: bool = True
risk_daily_trades_enabled: bool = True
risk_consecutive_losses_enabled: bool = True
risk_drawdown_enabled: bool = True
risk_correlation_enabled: bool = True
risk_portfolio_enabled: bool = True

# Limites strictes
risk_max_daily_loss: float = 300.0           # 300$ max/jour
risk_max_daily_trades: int = 30              # 30 trades max/jour
risk_max_consecutive_losses: int = 3         # 3 pertes → cooldown
risk_max_drawdown_percent: float = 8.0       # Drawdown 8% max
risk_max_correlated_positions: int = 2       # 2 positions max/direction
risk_max_portfolio_risk_percent: float = 15.0  # Risque 15% max
```

**Pour qui:** Débutants, comptes <5000$, trading automatisé 24/7

---

### 🟡 Configuration ÉQUILIBRÉE (Par défaut)

```python
# Protection standard
circuit_breaker_enabled: bool = True
risk_daily_loss_enabled: bool = True
risk_daily_trades_enabled: bool = True
risk_consecutive_losses_enabled: bool = True
risk_drawdown_enabled: bool = True
risk_correlation_enabled: bool = True
risk_portfolio_enabled: bool = True

# Limites standards
risk_max_daily_loss: float = 500.0           # 500$ max/jour
risk_max_daily_trades: int = 50              # 50 trades max/jour
risk_max_consecutive_losses: int = 5         # 5 pertes → cooldown
risk_max_drawdown_percent: float = 10.0      # Drawdown 10% max
risk_max_correlated_positions: int = 3       # 3 positions max/direction
risk_max_portfolio_risk_percent: float = 20.0  # Risque 20% max
```

**Pour qui:** Traders expérimentés, comptes >5000$, stratégies testées

---

### 🔴 Configuration AGRESSIVE (Déconseillé)

```python
# Protections minimales
circuit_breaker_enabled: bool = True
risk_daily_loss_enabled: bool = True         # Garder au minimum cette protection
risk_daily_trades_enabled: bool = False      # ❌ Désactivé
risk_consecutive_losses_enabled: bool = False  # ❌ Désactivé
risk_drawdown_enabled: bool = True           # Garder drawdown
risk_correlation_enabled: bool = False       # ❌ Désactivé
risk_portfolio_enabled: bool = False         # ❌ Désactivé

# Limites élevées
risk_max_daily_loss: float = 1000.0          # 1000$ max/jour
risk_max_drawdown_percent: float = 15.0      # Drawdown 15% max
```

**Pour qui:** Experts uniquement, comptes >10000$, surveillance manuelle

**⚠️ ATTENTION:** Configuration à haut risque - Peut entraîner pertes importantes

---

### 🔥 Mode SANS PROTECTION (Très dangereux)

```python
# TOUT désactivé
circuit_breaker_enabled: bool = False  # ⛔ DANGEREUX
```

**⚠️⚠️⚠️ NE PAS UTILISER EN PRODUCTION ⚠️⚠️⚠️**

Uniquement pour:
- Tests en compte démo
- Backtesting
- Développement/Debug

**Risque:** Perte totale du compte possible

---

## 📊 LOGS D'INITIALISATION

### Avec toutes les protections activées:

```
================================================================================
🛡️ RISK MANAGER INITIALISÉ
✅ Circuit Breaker ACTIVÉ - Protections:
   ✓ Perte journalière: Max 500.0$
   ✓ Trades journaliers: Max 50
   ✓ Pertes consécutives: Max 5 (cooldown 30min)
   ✓ Drawdown: Max 10.0%
   ✓ Corrélation: Max 3 positions/direction
   ✓ Risque portefeuille: Max 20.0%
================================================================================
```

### Avec certaines protections désactivées:

```
================================================================================
🛡️ RISK MANAGER INITIALISÉ
✅ Circuit Breaker ACTIVÉ - Protections:
   ✓ Perte journalière: Max 500.0$
   ✓ Trades journaliers: Max 50
   ✗ Pertes consécutives: DÉSACTIVÉ
   ✓ Drawdown: Max 10.0%
   ✗ Corrélation: DÉSACTIVÉE
   ✓ Risque portefeuille: Max 20.0%
================================================================================
```

### Avec Circuit Breaker complètement désactivé:

```
================================================================================
🛡️ RISK MANAGER INITIALISÉ
⚠️ CIRCUIT BREAKER DÉSACTIVÉ - Aucune protection active
================================================================================
```

---

## 🎯 SCÉNARIOS D'UTILISATION

### Scénario 1: Compte petit (< 2000$)

```python
# Protection maximale
circuit_breaker_enabled = True
risk_max_daily_loss = 200.0              # 10% du capital max/jour
risk_max_drawdown_percent = 8.0          # Drawdown 8% max
risk_max_correlated_positions = 2        # Diversification stricte
```

**Objectif:** Survivre et grandir lentement

---

### Scénario 2: Compte moyen (2000$ - 10000$)

```python
# Protection standard
circuit_breaker_enabled = True
risk_max_daily_loss = 500.0              # Config par défaut
risk_max_drawdown_percent = 10.0
risk_max_correlated_positions = 3
```

**Objectif:** Équilibre risque/rendement

---

### Scénario 3: Compte gros (> 10000$)

```python
# Protection ajustée
circuit_breaker_enabled = True
risk_max_daily_loss = 1000.0             # 1000$/jour acceptable
risk_max_daily_trades = 100              # Volume élevé OK
risk_max_drawdown_percent = 12.0         # Tolérance plus élevée
```

**Objectif:** Maximiser profits avec risque contrôlé

---

### Scénario 4: Backtesting

```python
# Désactiver protections pour analyser stratégie brute
circuit_breaker_enabled = False
```

**Objectif:** Voir performance réelle sans interventions

**⚠️ SEULEMENT en BACKTEST - Jamais en LIVE**

---

## 🔧 COMMENT MODIFIER

### Méthode 1: Éditer directement le fichier

```python
# Ouvrir: Production/config/trading_config.py

@dataclass
class TradingConfig:
    # ...
    
    # Modifier ici
    circuit_breaker_enabled: bool = True  # True ou False
    risk_daily_loss_enabled: bool = True  # True ou False
    risk_max_daily_loss: float = 500.0    # Ajuster la valeur
    # ...
```

### Méthode 2: Via l'interface GUI (à venir)

Un onglet **"⚙️ Paramètres"** sera ajouté pour modifier ces valeurs en temps réel.

---

## 🐛 TESTS

### Tester avec protections désactivées (compte démo):

```python
# Désactiver temporairement
circuit_breaker_enabled = False
```

Lancer le bot et observer:
- Pas de messages `⛔ CIRCUIT BREAKER`
- Pas de cooldown après pertes
- Trades illimités

### Tester une protection spécifique:

```python
# Tester seulement la protection de perte journalière
circuit_breaker_enabled = True
risk_daily_loss_enabled = True
risk_max_daily_loss = 50.0  # Seuil très bas pour test

# Désactiver les autres
risk_daily_trades_enabled = False
risk_consecutive_losses_enabled = False
risk_drawdown_enabled = False
risk_correlation_enabled = False
risk_portfolio_enabled = False
```

Après 50$ de pertes, le Circuit Breaker devrait se déclencher.

---

## ✅ RÉSUMÉ

**Paramètres disponibles:**
- ✅ 1 switch global (`circuit_breaker_enabled`)
- ✅ 6 switches individuels pour chaque protection
- ✅ Valeurs de seuils ajustables
- ✅ Logs détaillés des protections actives

**Recommandation:**
- 🟢 **Garder TOUTES les protections activées** en production
- 🟡 Ajuster les **seuils** selon votre capital et expérience
- 🔴 Ne désactiver que pour **backtesting** ou **debug**

**Le Circuit Breaker peut sauver votre compte ! Ne le désactivez pas sans raison valable.** 🛡️
