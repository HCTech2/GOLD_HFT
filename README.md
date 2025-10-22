# 🤖 GOLD_HFT - Bot de Trading Haute Fréquence XAU/USD

**GOLD_HFT** est un système de trading algorithmique haute fréquence pour l'or (XAU/USD) intégrant machine learning, analyse multi-timeframe et gestion avancée des risques. Le bot utilise des indicateurs techniques optimisés (STC, Ichimoku), un circuit breaker intelligent et une stratégie de martingale additive progressive ("Sweep") pour maximiser les profits tout en protégeant le capital.

Le système combine une architecture Python/Rust hybride pour des performances optimales, avec une interface graphique temps réel et des capacités d'apprentissage automatique (Random Forest, LSTM, Q-Learning) pour s'adapter aux conditions de marché changeantes.

Conçu pour MetaTrader 5, GOLD_HFT offre une protection multi-niveaux contre les risques (perte journalière, drawdown, corrélation, overtrading) tout en exploitant les micro-mouvements du marché de l'or avec une précision de l'ordre de la milliseconde.

---

## 📋 Table des Matières

1. [Installation Rapide](#-installation-rapide)
2. [Comment Ça Fonctionne](#-comment-ça-fonctionne)
3. [Architecture du Système](#-architecture-du-système)
4. [Guide de Démarrage](#-guide-de-démarrage)
5. [Configuration](#-configuration)
6. [Stratégies de Trading](#-stratégies-de-trading)
7. [Gestion des Risques](#-gestion-des-risques)
8. [Machine Learning](#-machine-learning)
9. [Optimisation et Performances](#-optimisation-et-performances)
10. [Documentation Technique](#-documentation-technique)
11. [Dépannage](#-dépannage)
12. [Contribution](#-contribution)

---

## 🚀 Installation Rapide

### Prérequis
- **Python 3.11+** (recommandé)
- **MetaTrader 5** installé et connecté à un broker
- **Windows 10/11** (pour MT5)

### Installation

```powershell
# 1. Cloner ou télécharger le projet
cd D:\MCP\GOLD_HFT

# 2. Créer un environnement virtuel
python -m venv .venv

# 3. Activer l'environnement
.\.venv\Scripts\Activate.ps1

# 4. Installer les dépendances
pip install -r requirements.txt

# 5. (Optionnel) Compiler Rust pour performances maximales
cd hft_rust_core
pip install maturin
maturin develop --release
cd ..

# 6. Lancer le bot
python run_hft_bot.py
```

### Démarrage Express

```powershell
# Utiliser le lanceur Windows
.\start_bot.bat
```

📚 **Voir aussi**: [GUIDE_DEMARRAGE_RAPIDE.md](GUIDE_DEMARRAGE_RAPIDE.md) pour un tutoriel détaillé

---

## 🎯 Comment Ça Fonctionne

### Vue d'Ensemble

GOLD_HFT analyse le marché de l'or en **temps réel** (flux de ticks MT5) et prend des décisions de trading basées sur :

1. **Analyse Technique Multi-Timeframe**
   - **M1/M5** : Décisions d'entrée rapides (STC + Ichimoku)
   - **M15/M30/H1/H4** : Filtrage HTF (Higher Timeframe) pour confirmer la tendance
   - **Score de confiance** : 0-100% basé sur l'alignement des 4 timeframes HTF

2. **Indicateurs Optimisés**
   - **STC (Schaff Trend Cycle)** : Détection précoce des retournements
   - **Ichimoku Kinko Hyo** : Confirmation tendance et support/résistance
   - **ATR (Average True Range)** : Volatilité dynamique pour SL/TP
   - **Volume Analysis** : Validation par volume de tick

3. **Machine Learning Adaptatif**
   - **Random Forest** : Classification direction (BUY/SELL/HOLD)
   - **LSTM** : Prédiction séries temporelles
   - **Q-Learning** : Optimisation entrée/sortie
   - **Entraînement continu** : Le bot apprend de ses trades

4. **Gestion des Risques Intelligente**
   - **Circuit Breaker** : Arrêt automatique si limites dépassées
   - **Risk Manager** : 6 protections indépendantes
   - **Trailing Stop 2 phases** : Sécurisation progressive des profits
   - **Corrélation Control** : Limite positions simultanées

5. **Stratégie Sweep Progressive**
   - **Martingale additive** : Augmentation progressive des lots (1x, 2x, 3x, 4x)
   - **Détection Elliott Wave** : Entrées sur retracements
   - **Sortie échelonnée** : Maximisation profits sur tendances fortes

### Workflow d'un Trade

```
┌─────────────────────────────────────────────────────────────────┐
│  1. RÉCEPTION TICK MT5                                          │
│     └─> Mise à jour buffer Rust (si disponible) ou Python      │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  2. CALCUL INDICATEURS                                          │
│     ├─> STC (Fast=23, Slow=50, Cycle=10)                       │
│     ├─> Ichimoku (9/26/52) avec nuage                          │
│     ├─> ATR (14) pour volatilité                               │
│     └─> HTF Confidence (M15/M30/H1/H4)                         │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  3. GÉNÉRATION SIGNAL                                           │
│     ├─> STC Crossover + Ichimoku Alignment                     │
│     ├─> HTF Confidence > 60% (configurable)                    │
│     ├─> Volume Confirmation                                     │
│     └─> ML Recommendation (si activé)                          │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  4. VALIDATION CIRCUIT BREAKER                                  │
│     ├─> Perte journalière < max (\$500 par défaut)             │
│     ├─> Trades journaliers < max (50 par défaut)              │
│     ├─> Pas de streak pertes (5 par défaut)                   │
│     ├─> Drawdown < max (10% par défaut)                       │
│     ├─> Corrélation OK (3 positions max/direction)            │
│     └─> Risque portefeuille < max (20% par défaut)            │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  5. CALCUL VOLUME & LEVELS                                      │
│     ├─> Volume = Base × ML_Multiplier × Sweep_Multiplier      │
│     ├─> SL = Prix ± (ATR × 2.5)                               │
│     ├─> TP = Prix ± (ATR × 4.0)                               │
│     └─> Trailing = 2 phases (secure + extension)              │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│  6. EXÉCUTION ORDRE MT5                                         │
│     └─> Envoi + Suivi + Trailing + ML Learning                │
└─────────────────────────────────────────────────────────────────┘
```

---

## 🏗️ Architecture du Système

### Structure des Dossiers

```
GOLD_HFT/
├── 📄 run_hft_bot.py          # ⭐ Point d'entrée principal
├── 📄 start_bot.bat            # Lanceur Windows
├── 📄 train_ml.bat             # Wizard entraînement ML
├── 📄 requirements.txt         # Dépendances Python
│
├── 📁 config/                  # Configuration
│   ├── trading_config.py       # Dataclass configuration principale
│   ├── settings_manager.py     # Sauvegarde/chargement paramètres
│   └── __init__.py
│
├── 📁 gui/                     # Interface Graphique
│   ├── main_window.py          # Fenêtre Tkinter principale
│   ├── indicator_worker.py     # Thread worker calculs
│   └── __init__.py
│
├── 📁 trading/                 # Logique Trading
│   ├── strategy.py             # Stratégie HFT (STC, Ichimoku, HTF)
│   ├── position_manager.py     # Gestion positions MT5
│   ├── risk_manager.py         # Circuit Breaker + Risk Control
│   ├── sweep_manager.py        # Martingale additive
│   └── __init__.py
│
├── 📁 utils/                   # Utilitaires
│   ├── logger.py               # Configuration logging
│   ├── mt5_helper.py           # Helpers MetaTrader 5
│   └── __init__.py
│
├── 📁 ml/                      # Machine Learning
│   ├── trainer.py              # Entraînement modèles
│   ├── trade_database.py       # SQLite trades
│   ├── data/                   # Base de données générée
│   └── __init__.py
│
├── 📁 indicators/              # Indicateurs Techniques
│   ├── hft_indicators.py       # STC, Ichimoku, ATR, etc.
│   ├── zigzag.py               # ZigZag (optionnel)
│   └── __init__.py
│
└── 📁 hft_rust_core/           # Accélération Rust (optionnel)
    ├── src/                    # Code source Rust
    ├── Cargo.toml              # Configuration Cargo
    └── pyproject.toml          # Configuration Maturin
```

### Modules Clés

| Module | Responsabilité | Technologie |
|--------|----------------|-------------|
| **HFTStrategy** | Analyse, signaux, décisions | Python + Rust (optionnel) |
| **PositionManager** | Gestion ordres MT5, trailing | Python + MetaTrader5 |
| **RiskManager** | Circuit Breaker, 6 protections | Python |
| **SweepManager** | Martingale progressive | Python |
| **MLTrainer** | Random Forest, LSTM, Q-Learning | Python + scikit-learn, TensorFlow |
| **HFTIndicators** | STC, Ichimoku, ATR | Python + Rust (25x plus rapide) |
| **HFTBotGUI** | Interface temps réel | Python + Tkinter |

📚 **Voir aussi**: [ARCHITECTURE_MODULAIRE.md](ARCHITECTURE_MODULAIRE.md)

---

## 📖 Guide de Démarrage

### Étape 1 : Configuration MetaTrader 5

1. **Installer MT5** : [Télécharger MT5](https://www.metatrader5.com/)
2. **Créer un compte démo** chez un broker (TitanFX, XM, IC Markets)
3. **Activer Algo Trading** : Outils → Options → Expert Advisors → ☑ Autoriser le trading automatique
4. **Vérifier symbole** : XAUUSD ou XAUUSD-m (micro lots)

### Étape 2 : Premier Lancement

```powershell
# Lancer le bot
python run_hft_bot.py
```

Le bot vous proposera de configurer le **Circuit Breaker** :

```
⚙️  Configurer le Circuit Breaker avant lancement? (o/n) [défaut: n]:
```

**Recommandation débutant** : Tapez `o` puis choisir **Preset 2 - CONSERVATIVE**

### Étape 3 : Interface Graphique

L'interface se divise en 4 sections :

```
┌────────────────────────────────────────────────────────┐
│  📊 DASHBOARD                                          │
│  Portfolio | Win Rate | Drawdown | Positions          │
├────────────────────────────────────────────────────────┤
│  🎛️ CONTRÔLES                                          │
│  [▶ Démarrer] [⏸ Pause] [⏹ Arrêter]                  │
│  Sliders: SL/TP Multiplier, Spread Max, Volume Base   │
├────────────────────────────────────────────────────────┤
│  📝 LOGS TEMPS RÉEL                                    │
│  2025-10-22 16:30:45 - BUY Signal (HTF: 75%)         │
│  2025-10-22 16:30:50 - Order #12345 opened @2650.50  │
├────────────────────────────────────────────────────────┤
│  🤖 MACHINE LEARNING                                   │
│  [🎓 Entraîner] Status: 150 trades • Accuracy: 68%   │
└────────────────────────────────────────────────────────┘
```

### Étape 4 : Surveillance

1. **Dashboard** : Vérifiez le portfolio, win rate, drawdown
2. **Logs** : Surveillez les signaux et ordres
3. **Circuit Breaker** : Observez les alertes de protection
4. **HTF Confidence** : Score tendance multi-timeframe

### Étape 5 : Arrêt

1. Cliquez **⏹ Arrêter** dans l'interface
2. Le bot ferme proprement les ressources
3. Les paramètres sont sauvegardés automatiquement

📚 **Voir aussi**: 
- [GUIDE_DEMARRAGE.md](GUIDE_DEMARRAGE.md) - Guide complet
- [GUIDE_DEMARRAGE_RAPIDE.md](GUIDE_DEMARRAGE_RAPIDE.md) - Tutoriel 5 minutes
- [README_V2_QUICK_START.md](README_V2_QUICK_START.md) - Quick start v2.0

---

## ⚙️ Configuration

### Configuration Interactive

Au lancement, le bot propose un menu de configuration :

```
📚 PRESETS DISPONIBLES:
   [1] Configuration actuelle (personnaliser)
   [2] 🟢 CONSERVATIVE - Protection maximale (débutant)
   [3] 🟡 ÉQUILIBRÉE - Standard (recommandé)
   [4] 🔴 AGRESSIVE - Protection minimale (expert)
   [5] ⚫ DÉSACTIVÉ - Aucune protection (backtest uniquement)
```

### Paramètres Circuit Breaker

| Protection | Conservative | Équilibrée | Agressive |
|------------|--------------|------------|-----------|
| **Perte journalière** | \$200 | \$500 | \$1000 |
| **Trades/jour** | 30 | 50 | Illimité |
| **Pertes consécutives** | 3 | 5 | Illimité |
| **Drawdown max** | 8% | 10% | 15% |
| **Corrélation** | 2 pos | 3 pos | Illimité |
| **Risque portefeuille** | 15% | 20% | Illimité |

### Sauvegarde Automatique

Les paramètres modifiés via l'interface sont **automatiquement sauvegardés** à la fermeture du bot dans `config/saved_settings.json`.

📚 **Voir aussi**: 
- [GUIDE_CONFIGURATION_INTERACTIVE.md](GUIDE_CONFIGURATION_INTERACTIVE.md)
- [CIRCUIT_BREAKER_INTERFACE_INTERACTIVE.md](CIRCUIT_BREAKER_INTERFACE_INTERACTIVE.md)
- [GUIDE_SAUVEGARDE_PARAMETRES.md](GUIDE_SAUVEGARDE_PARAMETRES.md)
- [SYSTEME_PARAMETRAGE.md](SYSTEME_PARAMETRAGE.md)

---

## 📊 Stratégies de Trading

### 1. Stratégie STC + Ichimoku (Principale)

**Signaux d'entrée** :
- STC croise au-dessus de 25 → **BUY**
- STC croise en-dessous de 75 → **SELL**
- Prix au-dessus du nuage Ichimoku → Confirmation BUY
- Prix en-dessous du nuage Ichimoku → Confirmation SELL

**Filtrage HTF** :
- Calcul tendance sur M15, M30, H1, H4
- Score de confiance = % de timeframes alignés
- Entrée seulement si confiance > 60% (configurable)

### 2. Stratégie Sweep Progressive

**Principe** : Martingale additive sur retracements Elliott Wave

```
Position 1 : 1× base (0.01 lot) → Retracement détecté
Position 2 : 2× base (0.02 lot) → Continuation baisse
Position 3 : 3× base (0.03 lot) → Encore baisse
Position 4 : 4× base (0.04 lot) → Dernier retracement
═══════════════════════════════════════════════════════
Prix rebondit → Toutes positions en profit → Sortie échelonnée
```

**Activation** :
- Circuit Breaker **DÉSACTIVÉ** (backtest uniquement)
- OU mode `unrestricted_mode=True` dans code

**Avantages** :
- ✅ Maximise profits sur tendances fortes
- ✅ Moyenne le prix d'entrée
- ✅ Sortie échelonnée (30%, 30%, 20%, 20%)

**Risques** :
- ⚠️ Besoin de capital suffisant (marge)
- ⚠️ Perte amplifiée si tendance ne retourne pas
- ⚠️ Utiliser UNIQUEMENT en backtest ou avec expertise

📚 **Voir aussi**: 
- [STRATEGIE_SWEEP_HFT.md](STRATEGIE_SWEEP_HFT.md)
- [GUIDE_TICK_PRIORITY_HTF_CONFIDENCE.md](GUIDE_TICK_PRIORITY_HTF_CONFIDENCE.md)
- [REFONTE_ICHIMOKU_STC.md](REFONTE_ICHIMOKU_STC.md)
- [SYSTEME_PROFIT_REACTIF.md](SYSTEME_PROFIT_REACTIF.md)

---

## 🛡️ Gestion des Risques

### Circuit Breaker - 6 Protections

Le **Circuit Breaker** est un système de sécurité multi-niveaux qui **arrête automatiquement** le trading si des limites sont atteintes.

#### 1. Protection Perte Journalière
```
❌ Perte du jour > \$500 → ARRÊT TRADING
```

#### 2. Protection Overtrading
```
❌ Nombre trades > 50/jour → ARRÊT TRADING
```

#### 3. Protection Pertes Consécutives
```
❌ 5 pertes d'affilée → COOLDOWN 30 minutes
```

#### 4. Protection Drawdown
```
❌ Drawdown > 10% du capital → ARRÊT TRADING
```

#### 5. Protection Corrélation
```
❌ > 3 positions BUY simultanées → REFUS NOUVELLE POSITION BUY
```

#### 6. Protection Risque Portefeuille
```
❌ Risque total positions > 20% capital → REFUS NOUVELLE POSITION
```

### Trailing Stop 2 Phases

**Phase 1 : Sécurisation**
```
Profit > \$10 → Trailing à \$5 du prix actuel
```

**Phase 2 : Extension**
```
Profit > \$20 → Trailing à \$8 du prix actuel (plus agressif)
```

📚 **Voir aussi**: 
- [CIRCUIT_BREAKER_ACTIVABLE.md](CIRCUIT_BREAKER_ACTIVABLE.md)
- [CIRCUIT_BREAKER_CONFIG.md](CIRCUIT_BREAKER_CONFIG.md)
- [AMELIORATIONS_V2.md](AMELIORATIONS_V2.md)

---

## 🤖 Machine Learning

### Entraînement

```powershell
# Lancer le wizard ML
.\train_ml.bat
```

**Étapes** :
1. Vérification données (min 100 trades)
2. Choix modèles (RF, LSTM, Q-Learning)
3. Split train/test (80/20 par défaut)
4. Entraînement avec validation croisée
5. Évaluation métriques
6. Sauvegarde modèles (`ml/models/`)

📚 **Voir aussi**: 
- [ml/ARCHITECTURE_ML_AVANCEE.md](ml/ARCHITECTURE_ML_AVANCEE.md)

---

## ⚡ Optimisation et Performances

### Accélération Rust

| Opération | Python | Rust | Gain |
|-----------|--------|------|------|
| **STC (1000 bars)** | 45ms | 2ms | **22x** |
| **Ichimoku (1000 bars)** | 80ms | 3ms | **26x** |
| **TickBuffer append** | 5µs | 200ns | **25x** |

**Compilation** :
```powershell
cd hft_rust_core
pip install maturin
maturin develop --release
```

📚 **Voir aussi**: 
- [GUIDE_RUST_INTEGRATION.md](GUIDE_RUST_INTEGRATION.md)
- [RUST_ACTIVATED.md](RUST_ACTIVATED.md)
- [OPTIMISATION_MEMOIRE_RAPPORT.md](OPTIMISATION_MEMOIRE_RAPPORT.md)
- [README_OPTIMISATION.md](README_OPTIMISATION.md)

---

## 📚 Documentation Technique

### Architecture
- [ARCHITECTURE_MODULAIRE.md](ARCHITECTURE_MODULAIRE.md)
- [README_ARCHITECTURE.md](README_ARCHITECTURE.md)
- [REFACTORISATION_RESUME.md](REFACTORISATION_RESUME.md)

### Corrections
- [CORRECTIONS_GUI_TEMPS_REEL.md](CORRECTIONS_GUI_TEMPS_REEL.md)
- [CORRECTION_FEED_TICKS.md](CORRECTION_FEED_TICKS.md)
- [CORRECTION_FILLING_MODE.md](CORRECTION_FILLING_MODE.md)
- [CORRECTION_ORDRES_NON_PLACES.md](CORRECTION_ORDRES_NON_PLACES.md)
- [CORRECTION_TP_SL_SPREAD.md](CORRECTION_TP_SL_SPREAD.md)

### Diagnostics
- [DIAGNOSTIC_AVANCE.md](DIAGNOSTIC_AVANCE.md)
- [DIAGNOSTIC_NO_ORDERS.md](DIAGNOSTIC_NO_ORDERS.md)
- [DIAGNOSTIC_SEUILS_MEMOIRE.md](DIAGNOSTIC_SEUILS_MEMOIRE.md)

### Tests
- [TEST_INSTRUCTIONS.md](TEST_INSTRUCTIONS.md)
- [TEST_REUSSI_BOT_OPERATIONNEL.md](TEST_REUSSI_BOT_OPERATIONNEL.md)

---

## 🔧 Dépannage

### Le bot ne place aucun ordre

**Solutions** :
1. Vérifier Circuit Breaker
2. Diminuer `htf_confidence_min`
3. Augmenter `spread_max`
4. Vérifier connexion MT5

📚 **Voir**: [DIAGNOSTIC_NO_ORDERS.md](DIAGNOSTIC_NO_ORDERS.md)

---

## ⚠️ AVERTISSEMENT

Le trading comporte des risques de perte en capital. Utilisez ce bot **uniquement en compte démo** avant tout passage en réel.

---

<div align="center">
  <img src="technology-tech.gif" alt="GOLD_HFT Technology" />
</div>

---

*Version 2.0.0 - 22 octobre 2025*
