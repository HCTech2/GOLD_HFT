# 🚨 DIAGNOSTIC: ANCIENS SEUILS STC EN MÉMOIRE

**Date:** 21 octobre 2025 09:27  
**Problème:** GUI montre Signal LONG + STC=0 (SURVENTE) mais aucun ordre placé sur MT5

---

## 🔍 ANALYSE DES LOGS

### Seuils STC détectés dans les logs:
```
2025-10-21 09:27:22.002 | [📊 CONDITION STC] M1:100.0 M5:0.0 | Seuils: Buy<10.9 Sell>97.4
```

### Comparaison avec fichier de configuration:

**Fichier `config/trading_config.py` (ligne 55-56):**
```python
stc_threshold_buy: float = 25.0   # STC < 25 = signal BUY (survente)
stc_threshold_sell: float = 75.0  # STC > 75 = signal SELL (surachat)
```

**❌ INCOHÉRENCE DÉTECTÉE:**
- Logs montrent: `Buy<10.9 Sell>97.4`
- Fichier montre: `Buy<25.0 Sell>75.0`

---

## 🧩 EXPLICATION DU PROBLÈME

### Cycle de vie de la configuration:

```
┌──────────────────────────────────────────────────────────────────┐
│ 1. LANCEMENT DU BOT                                              │
│    ├─ Lecture de config/trading_config.py                        │
│    ├─ config.stc_threshold_buy = 25.0 (après correction)         │
│    ├─ config.stc_threshold_sell = 75.0 (après correction)        │
│    └─ Création de la GUI avec ces valeurs                        │
├──────────────────────────────────────────────────────────────────┤
│ 2. INITIALISATION GUI (main_window.py ligne 58-59)              │
│    ├─ self.stc_buy_var = DoubleVar(value=config.stc_threshold_buy)│
│    ├─ self.stc_sell_var = DoubleVar(value=config.stc_threshold_sell)│
│    └─ Sliders STC créés avec valeurs initiales                   │
├──────────────────────────────────────────────────────────────────┤
│ 3. SESSION PRÉCÉDENTE (HYPOTHÈSE)                               │
│    ⚠️  Quelqu'un a modifié les sliders STC dans la GUI:          │
│    ├─ STC Buy: 25.0 → 10.9 (via slider)                         │
│    ├─ STC Sell: 75.0 → 97.4 (via slider)                        │
│    └─ Valeurs stockées dans self.stc_buy_var / self.stc_sell_var│
├──────────────────────────────────────────────────────────────────┤
│ 4. APPLICATION DES PARAMÈTRES (ligne 1116-1117)                 │
│    ├─ self.config.stc_threshold_buy = self.stc_buy_var.get()    │
│    ├─ self.config.stc_threshold_sell = self.stc_sell_var.get()  │
│    └─ ✅ Valeurs GUI écrasent les valeurs fichier                │
├──────────────────────────────────────────────────────────────────┤
│ 5. UTILISATION PAR LE STRATEGY (strategy.py ligne 420)          │
│    ├─ if stc_m1 < self.config.stc_threshold_buy (10.9)          │
│    ├─ STC M1 = 100.0 → 100.0 < 10.9 = FALSE                     │
│    └─ ❌ Signal REJETÉ même si STC=0 (survente extrême)          │
└──────────────────────────────────────────────────────────────────┘
```

### Pourquoi les seuils 10.9/97.4 ?

**Théorie 1:** Session précédente avec sliders modifiés manuellement
- Quelqu'un a testé différents seuils dans la GUI
- Les valeurs sont restées en mémoire du processus Python
- Même sans `user_settings.json`, les variables GUI gardent leurs valeurs

**Théorie 2:** Ancien code avec seuils par défaut différents
- Le bot a été lancé AVANT la correction des seuils (1.0/99.0)
- Une version intermédiaire avec 10.9/97.4 a existé
- Le processus n'a jamais été redémarré depuis

**Théorie 3:** Conflit avec un autre fichier de config
- ❌ `granular_strategy_config.json` → N'existe pas
- ❌ `user_settings.json` → N'existe pas (vérifié)
- ❌ Preset Circuit Breaker → Ne touche pas aux seuils STC

---

## 🎯 CONSÉQUENCES

### Avec seuils incorrects (10.9/97.4):

**Exemple de signal rejeté:**
```
STC M1: 0.0 (survente extrême, devrait être BUY)
Condition: stc_m1 < 10.9 ?
Résultat: 0.0 < 10.9 = TRUE → Signal BUY détecté
```

Attendez... Ça devrait FONCTIONNER ! 🤔

Vérifions les logs plus en détail...

---

## 🔎 ANALYSE APPROFONDIE DES LOGS

### Logs observés:
```
[📊 CONDITION STC] M1:100.0 M5:0.0 | Seuils: Buy<10.9 Sell>97.4
```

**⚠️ PROBLÈME RÉEL DÉTECTÉ:**
- STC M1 = **100.0** (SURACHAT EXTRÊME, devrait être SELL)
- STC M5 = **0.0** (SURVENTE EXTRÊME, devrait être BUY)
- **Contradiction entre M1 et M5 !**

### Analyse de la condition (strategy.py ligne 423):
```python
if stc_m1 < self.config.stc_threshold_buy or (stc_m1 < 50 and stc_m5 < 50):
    # Signal HAUSSIER
```

**Évaluation:**
- `stc_m1 < 10.9` → `100.0 < 10.9` = **FALSE**
- `(stc_m1 < 50 and stc_m5 < 50)` → `(100.0 < 50 and 0.0 < 50)` = **FALSE**
- **Résultat: Signal HAUSSIER REJETÉ** ✅ (correct car M1=100 = surachat)

### Analyse condition baissière (ligne 433):
```python
elif stc_m1 > self.config.stc_threshold_sell or (stc_m1 > 50 and stc_m5 > 50):
    # Signal BAISSIER
```

**Évaluation:**
- `stc_m1 > 97.4` → `100.0 > 97.4` = **TRUE**
- **Résultat: Signal BAISSIER ACCEPTÉ** ✅

Donc le bot devrait chercher un signal BAISSIER (SELL) !

### Mais la GUI montre:
- Signal: **LONG (Achat)** ← Incohérence !
- STC: **0.00 / 100** ← Différent des logs (M1:100.0, M5:0.0)

---

## 🚨 DOUBLE PROBLÈME IDENTIFIÉ

### Problème #1: Anciens seuils (10.9/97.4)
- ✅ Corrigé dans `config/trading_config.py` (25.0/75.0)
- ❌ Pas chargé car bot pas redémarré
- **Impact:** Seuils trop stricts, rejettent des signaux valides

### Problème #2: Incohérence STC entre logs et GUI
- **Logs strategy.py:** M1=100.0 (surachat)
- **GUI affiche:** 0.00 (survente)
- **Cause possible:**
  - GUI lit depuis `IndicatorWorker` (thread séparé)
  - Strategy lit depuis calcul Rust direct
  - Désynchronisation entre les deux sources

---

## ✅ SOLUTIONS

### Solution Immédiate: Redémarrer le bot

**Étape 1:** Arrêter complètement
```
1. Dans la GUI: Cliquer [🔴 Arrêter]
2. Fermer la fenêtre GUI (X)
3. Vérifier processus terminés: Get-Process python*
```

**Étape 2:** Relancer avec nouveaux paramètres
```powershell
.\start_bot.ps1
```

**Résultat attendu:**
- Chargement des seuils 25.0/75.0 depuis `trading_config.py`
- Synchronisation STC entre GUI et Strategy
- Ordres placés sur MT5 dès signaux valides

### Solution Long Terme: Résoudre désynchronisation GUI

**Fichier à modifier:** `gui/indicator_worker.py`

**Problème:**
- `IndicatorWorker` calcule STC indépendamment
- Utilise potentiellement des données différentes
- Pas de synchronisation avec calcul Rust de `strategy.py`

**Solution:**
- Faire lire les valeurs STC directement depuis `strategy.indicators`
- Au lieu de recalculer dans `IndicatorWorker`
- Garantir une source unique de vérité

**Code à ajouter (indicator_worker.py):**
```python
# Au lieu de calculer STC localement:
stc_m1 = self.indicators.calculate_stc('M1')

# Lire depuis la strategy:
if self.strategy and self.strategy.indicators:
    stc_m1 = self.strategy.indicators.last_stc_m1  # Cache
else:
    stc_m1 = self.indicators.calculate_stc('M1')  # Fallback
```

---

## 📊 VÉRIFICATIONS POST-REDÉMARRAGE

### 1. Vérifier seuils STC chargés:
```powershell
.\watch_orders.ps1
```

Devrait afficher:
```
1️⃣  SEUILS STC APPLIQUÉS:
   ✅ Seuils corrigés détectés (25/75)
   [📊 CONDITION STC] M1:X M5:Y | Seuils: Buy<25.0 Sell>75.0
```

### 2. Vérifier synchronisation STC:
```powershell
$log = (Get-ChildItem "d:\Prototype\Production\hft_bot_*.log" | Sort-Object LastWriteTime -Descending | Select-Object -First 1).FullName
Get-Content $log | Select-String "STC.*M1.*M5" | Select-Object -Last 5
```

Comparer avec les valeurs affichées dans la GUI.

### 3. Surveiller ordres placés:
```powershell
Get-Content $log | Select-String "ORDRE.*Ouverture|Position ouverte" | Select-Object -Last 10
```

Si toujours aucun ordre après 10 minutes → Problème plus profond.

---

## 🔧 DÉPANNAGE AVANCÉ

### Si toujours aucun ordre après redémarrage:

**Vérifier HTF confirmations:**
```powershell
Get-Content $log | Select-String "TENDANCE HTF.*✅"
```

**Vérifier rejets HTF:**
```powershell
Get-Content $log | Select-String "REJET|NEUTRE"
```

**Vérifier Circuit Breaker:**
```powershell
Get-Content $log | Select-String "CIRCUIT BREAKER|PROTECTION.*bloqué"
```

**Vérifier Ichimoku:**
```powershell
Get-Content $log | Select-String "ICHIMOKU|CROISEMENT"
```

---

## 📝 CHECKLIST

- [ ] Bot arrêté complètement (GUI fermée + processus tués)
- [ ] Relancement avec `.\start_bot.ps1`
- [ ] Seuils STC = 25.0/75.0 dans logs (vérifier avec watch_orders.ps1)
- [ ] Synchronisation STC entre logs et GUI
- [ ] Confirmations HTF apparaissent dans logs
- [ ] Ordres placés sur MT5 (vérifier GUI + MT5 Terminal)
- [ ] Balance MT5 change (confirmation exécution)

---

## 🎯 RÉSUMÉ EXÉCUTIF

**Problème principal:** Bot utilise anciens seuils STC (10.9/97.4) stockés en mémoire.

**Cause:** Processus Python pas redémarré après correction dans `trading_config.py`.

**Solution:** Arrêter bot → Relancer → Vérifier nouveaux seuils (25.0/75.0).

**Problème secondaire:** Désynchronisation STC entre GUI (0.00) et logs (100.0).

**Solution:** Après redémarrage, si problème persiste → Modifier `indicator_worker.py` pour lire depuis source unique.

**Résultat attendu:** Ordres placés sur MT5 dès signaux Ichimoku + STC + HTF alignés.

**Temps estimé:** 2 minutes (redémarrage) + 5-10 minutes (observation).
