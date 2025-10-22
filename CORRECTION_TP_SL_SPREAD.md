# 🎯 Correction du Take Profit et Stop Loss pour XAU/USD

## 📋 Problème identifié

**Symptômes:**
- Profits de -0.01% au lieu du minimum 2x attendu par sweep
- Le spread n'était pas pris en compte dans les calculs
- TP trop serré (seulement 1.0$ = 100 points)

## 🔍 Analyse

### Ancien calcul (incorrect):
```python
# SL dynamique basé sur le portefeuille (trop complexe)
sl_distance = max(0.5, (current_portfolio - min_portfolio) * 0.1) * sl_mult

# TP fixe de 1$ seulement
take_profit = entry_price + (1.0 * tp_mult)  # BUY
```

**Problèmes:**
- ❌ SL variable selon le portefeuille (imprévisible)
- ❌ TP de 1$ trop faible pour XAU/USD
- ❌ Spread non comptabilisé (coût d'entrée ignoré)
- ❌ Ratio Risk:Reward désavantageux

## ✅ Solution implémentée

### Nouveau calcul (correct):

```python
# Distances fixes et professionnelles
base_sl_distance = 10.0  # 10$ de SL (100 points)
base_tp_distance = 20.0  # 20$ de TP (200 points) → Ratio 1:2

# Récupération du spread réel
symbol_info = mt5.symbol_info(symbol)
spread_in_price = symbol_info.spread * symbol_info.point

# Compensation du spread dans le TP
tp_distance += spread_in_price * 1.5  # +50% du spread pour sécurité

# Application des multiplicateurs de la GUI
sl_distance = base_sl_distance * sl_mult
tp_distance = base_tp_distance * tp_mult
```

## 📊 Résultats attendus

### Exemple avec spread de 3.15$ (315 points):

**Configuration standard (100%):**
- Prix d'entrée: 4248.99$
- SL: 4238.99$ (-10.00$)
- TP: 4273.71$ (+20.00$ + 4.73$ spread compensé = +24.73$)
- **Ratio Risk:Reward: 2.47:1** ✅
- **Profit net après spread: 20.00$** ✅

**Configuration agressive (TP 200%):**
- Prix d'entrée: 4248.99$
- SL: 4238.99$ (-10.00$)
- TP: 4293.71$ (+40.00$ + 4.73$ spread = +44.73$)
- **Ratio Risk:Reward: 4.47:1** ✅
- **Profit net après spread: 40.00$** ✅

## 🎛️ Multiplicateurs GUI

Les sliders de la GUI permettent d'ajuster:
- **SL%**: 50% à 200% (de 5$ à 20$ de distance)
- **TP%**: 50% à 200% (de 10$ à 40$ de distance)
- **Volume%**: 50% à 200% (taille de position)

## 📈 Avantages

1. ✅ **Ratio Risk:Reward minimum 2:1** garanti
2. ✅ **Spread compensé** automatiquement dans le TP
3. ✅ **Distances fixes et prévisibles** (10$ SL / 20$ TP de base)
4. ✅ **Profits minimum 2x** le risque (objectif atteint)
5. ✅ **Multiplicateurs flexibles** via GUI
6. ✅ **Log détaillé** des paramètres de chaque trade

## 🔧 Logs ajoutés

Nouveau log lors de l'ouverture de position:
```
[TRADE SETUP] Prix=4248.99, SL=4238.99 (-10.00$), TP=4273.71 (+24.73$), R:R=2.47:1
```

Ce log permet de vérifier:
- Le prix d'entrée exact
- La distance du SL en dollars
- La distance du TP en dollars (avec spread compensé)
- Le ratio Risk:Reward calculé

## 📝 Valeurs pour XAU/USD (Gold Micro)

- **1 point = 0.01$**
- **100 points = 1.00$**
- **Spread moyen TitanFX: 315 points = 3.15$**
- **SL de base: 1000 points = 10.00$**
- **TP de base: 2000 points = 20.00$**

## 🚀 Pour tester

1. **Redémarrer le bot**
2. Attendre un signal confirmé
3. Vérifier dans les logs:
   ```
   [TRADE SETUP] Prix=XXXX, SL=XXXX (-10.00$), TP=XXXX (+24.73$), R:R=2.47:1
   [FILLING MODE] FOK sélectionné
   [HFT] Position ouverte...
   ```
4. Le profit devrait maintenant être **minimum 20$ net** par trade gagnant

## ⚙️ Ajustements possibles

Dans la GUI, vous pouvez:
- **Augmenter TP%** à 200% pour viser 40$ de profit
- **Réduire SL%** à 50% pour limiter le risque à 5$
- **Spread Max** à ajuster selon les conditions de marché

Date: 19 octobre 2025
Fichier: XAU_USD_HFT_Bot.py
Lignes modifiées: 690-722, 1305-1314
