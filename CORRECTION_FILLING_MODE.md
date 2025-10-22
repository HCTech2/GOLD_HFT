# 🔧 Correction du Filling Mode pour XAUUSD-m

## 📋 Problème identifié

**Erreur:** `RetCode=10030 - Unsupported filling mode`

Le bot utilisait un mauvais ordre de vérification des bits pour le filling mode, ce qui empêchait l'utilisation du mode FOK (Fill or Kill) requis par XAUUSD-m.

## 🔍 Diagnostic

Script `check_filling_mode.py` a révélé :
- **XAUUSD-m supporte UNIQUEMENT le mode FOK**
- `filling_mode = 1` (binaire: `0b1`)
- Seul le bit 0 est activé → FOK uniquement

## ✅ Corrections apportées

### 1. Dans `open_position()` (ligne ~795)

**AVANT (incorrect):**
```python
if symbol_info.filling_mode & 2:  # Vérifiait IOC d'abord
    filling_type = mt5.ORDER_FILLING_FOK  # Commentaire faux
elif symbol_info.filling_mode & 1:
    filling_type = mt5.ORDER_FILLING_IOC  # Commentaire faux
```

**APRÈS (correct):**
```python
if symbol_info.filling_mode & 1:  # FOK (Fill or Kill) - Bit 0
    filling_type = mt5.ORDER_FILLING_FOK
    filling_name = "FOK"
elif symbol_info.filling_mode & 2:  # IOC (Immediate or Cancel) - Bit 1
    filling_type = mt5.ORDER_FILLING_IOC
    filling_name = "IOC"
else:  # RETURN (Return) - Bit 2
    filling_type = mt5.ORDER_FILLING_RETURN
    filling_name = "RETURN"

logger.info(f"[FILLING MODE] {filling_name} sélectionné")
```

### 2. Dans `close_position()` (ligne ~923)

Même correction appliquée.

## 🎯 Résultat attendu

- ✅ Le bot détecte automatiquement FOK pour XAUUSD-m
- ✅ Les ordres d'achat/vente passent sans erreur 10030
- ✅ Log de confirmation du filling mode utilisé
- ✅ Compatible avec tous les symboles (auto-détection)

## 📊 Valeurs des constantes MT5

- `ORDER_FILLING_FOK = 0` (Fill or Kill - tout ou rien)
- `ORDER_FILLING_IOC = 1` (Immediate or Cancel - partiel OK)
- `ORDER_FILLING_RETURN = 2` (Market execution - ordre au marché)

## 🔢 Correspondance Bits

| Bit | Masque | Mode | Constante MT5 |
|-----|--------|------|---------------|
| 0   | & 1    | FOK  | 0             |
| 1   | & 2    | IOC  | 1             |
| 2   | & 4    | RETURN | 2           |

## 🚀 Prochaines étapes

1. **Redémarrer le bot**
2. Vérifier le log : `[FILLING MODE] FOK sélectionné`
3. Attendre un signal confirmé
4. L'ordre devrait passer avec succès

## 📝 Notes

- **FOK** = L'ordre est exécuté entièrement ou annulé
- Parfait pour le HFT où on veut une exécution complète immédiate
- Évite les exécutions partielles qui compliquent la gestion

Date: 19 octobre 2025
Fichier: XAU_USD_HFT_Bot.py
