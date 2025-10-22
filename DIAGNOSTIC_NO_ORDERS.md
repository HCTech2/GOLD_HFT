# 🔍 DIAGNOSTIC - Pas de placement d'ordres MT5

## 📊 SYMPTÔMES

Le bot détecte des signaux HTF valides :
```
2025-10-21 07:01:46 | INFO | [TENDANCE HTF] ✅ HAUSSIÈRE CONFIRMÉE - M1:0.0, M5:100.0 | HTF BUY:4/4
```

Mais **AUCUN ordre** n'est placé sur MT5.

---

## 🔎 CAUSES IDENTIFIÉES

### 1. **Ichimoku retourne None**

**Ligne 461** de `trading/strategy.py` :
```python
tenkan_m1, kijun_m1, senkou_a_m1, senkou_b_m1 = self.indicators.calculate_ichimoku('M1')

if None in [tenkan_m1, kijun_m1]:
    return  # ← RETOUR SILENCIEUX ICI
```

Le bot :
1. ✅ Détecte tendance HTF (BUY 4/4 confirmée)
2. ✅ Passe `check_can_trade()` du Risk Manager
3. ❌ **Ichimoku M1 retourne None** → return sans log
4. ❌ Aucun ordre placé

---

## 🛠️ CORRECTIONS APPLIQUÉES

### Ajout de logs de diagnostic

**1. Log si données insuffisantes (ligne 340)**
```python
if len(m1_candles) < 60 or len(m5_candles) < 60:
    logger.debug(f"[DONNÉES] Bougies insuffisantes - M1:{len(m1_candles)}/60, M5:{len(m5_candles)}/60")
    return
```

**2. Log après mise à jour indicateurs (ligne 348)**
```python
self.indicators.update_from_m1_candles(m1_candles)
self.indicators.update_from_m5_candles(m5_candles)
logger.debug(f"[INDICATEURS] Historique mis à jour - M1:{len(self.indicators.price_history_m1)} bougies, M5:{len(self.indicators.price_history_m5)} bougies")
```

**3. Log explicite si Ichimoku échoue (ligne 461)**
```python
if None in [tenkan_m1, kijun_m1]:
    m1_history_len = len(self.indicators.price_history_m1)
    required_len = self.config.ichimoku_senkou_span_b
    logger.warning(
        f"[ICHIMOKU] Données insuffisantes - Historique M1: {m1_history_len}/{required_len} bougies "
        f"(Tenkan:{tenkan_m1}, Kijun:{kijun_m1})"
    )
    return
```

---

## 🧪 TESTS À EFFECTUER

### 1. Relancer le bot et observer les nouveaux logs

```powershell
cd D:\Prototype\Production
python run_hft_bot.py
```

**Logs attendus :**
```
[DONNÉES] Bougies insuffisantes - M1:45/60, M5:38/60  ← Si pas assez de bougies
[INDICATEURS] Historique mis à jour - M1:100 bougies, M5:100 bougies  ← Si OK
[ICHIMOKU] Données insuffisantes - Historique M1: 0/52 bougies  ← Si update_from_m1_candles échoue
```

### 2. Vérifier `update_from_m1_candles()`

**Fichier** : `indicators/hft_indicators.py` ligne 55-62

Problème potentiel :
```python
def update_from_m1_candles(self, candles: List[OHLC]) -> None:
    if not candles:
        return
    
    self.price_history_m1.clear()  # ← Vide tout l'historique
    for candle in candles:
        self.price_history_m1.append(candle.close)
```

**Si clear() est appelé trop souvent**, l'historique ne se construit jamais !

---

## 🎯 SOLUTIONS POSSIBLES

### Solution A : Ne pas clear() l'historique à chaque update

**Avant** :
```python
def update_from_m1_candles(self, candles: List[OHLC]) -> None:
    if not candles:
        return
    
    self.price_history_m1.clear()  # ← Problème
    for candle in candles:
        self.price_history_m1.append(candle.close)
```

**Après** :
```python
def update_from_m1_candles(self, candles: List[OHLC]) -> None:
    if not candles:
        return
    
    # Remplacer complètement l'historique par les nouvelles données
    # (utile si candles contient TOUTES les bougies nécessaires)
    self.price_history_m1.clear()
    for candle in candles[-self.config.ichimoku_senkou_span_b * 2:]:  # Garder 2x la période nécessaire
        self.price_history_m1.append(candle.close)
```

### Solution B : Ajouter un log dans update_from_m1_candles

```python
def update_from_m1_candles(self, candles: List[OHLC]) -> None:
    if not candles:
        return
    
    self.price_history_m1.clear()
    for candle in candles:
        self.price_history_m1.append(candle.close)
    
    logger.debug(f"[HFT_INDICATORS] update_from_m1_candles: {len(candles)} bougies reçues, historique={len(self.price_history_m1)}")
    self.last_update = datetime.now()
```

---

## 📝 PROCHAINES ÉTAPES

1. ✅ **Logs ajoutés** - Relancer le bot pour voir où ça bloque
2. ⏳ **Analyser les logs** - Identifier si c'est un problème de :
   - Récupération de bougies (`get_m1_candles()`)
   - Mise à jour historique (`update_from_m1_candles()`)
   - Calcul Ichimoku (`calculate_ichimoku()`)
3. ⏳ **Appliquer le fix approprié** selon les résultats

---

## 💡 AUTRES CAUSES POSSIBLES

### Circuit Breaker désactivé (confirmé dans log)

```
2025-10-21 06:32:20.302 | WARNING | ⚠️ CIRCUIT BREAKER DÉSACTIVÉ - Aucune protection active
```

**Solution** : Activer avec le menu interactif au démarrage :
```powershell
python run_hft_bot.py
# Répondre 'o' à la question de configuration
# Choisir preset [3] Équilibrée
```

### Cooldown entre trades

Si `last_trade_time` est trop récent :
```python
self.min_trade_interval = timedelta(seconds=config.min_seconds_between_trades)  # 30 secondes par défaut
```

**Vérification** : Chercher dans les logs `"[COOLDOWN]"` ou `"min_trade_interval"`.

---

## ✅ RÉSUMÉ

**Problème principal** : Ichimoku M1 retourne `None` → aucun croisement détecté → aucun ordre

**Cause probable** : 
- `update_from_m1_candles()` appelle `clear()` trop souvent
- OU `get_m1_candles()` ne retourne pas assez de bougies
- OU délai d'accumulation des bougies M1 trop long après démarrage

**Prochaine action** : Observer les nouveaux logs pour confirmation ! 🚀
