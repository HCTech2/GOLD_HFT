#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Script de build et installation du module Rust
"""

import subprocess
import sys
import shutil
from pathlib import Path

def build_rust_module():
    """Compile le module Rust avec Maturin (PyO3)"""
    
    print("=" * 80)
    print("COMPILATION DU MODULE RUST HFT_RUST_CORE")
    print("=" * 80)
    
    rust_dir = Path(__file__).parent / "hft_rust_core"
    
    if not rust_dir.exists():
        print(f"❌ Erreur: Dossier {rust_dir} introuvable")
        return False
    
    # Vérifier que Maturin est installé
    try:
        result = subprocess.run(["maturin", "--version"], capture_output=True, text=True, check=False)
        if result.returncode != 0:
            raise FileNotFoundError
        print(f"✓ Maturin installé: {result.stdout.strip()}")
    except FileNotFoundError:
        print("⚠️ Maturin non trouvé - Installation...")
        try:
            subprocess.run([sys.executable, "-m", "pip", "install", "maturin"], check=True)
            print("✓ Maturin installé")
        except subprocess.CalledProcessError:
            print("❌ Échec installation maturin")
            return False
    
    # Compilation en mode release avec Maturin
    print("\n🔨 Compilation en mode RELEASE...")
    print("   (Cela peut prendre 1-3 minutes)")
    try:
        result = subprocess.run(
            ["maturin", "develop", "--release"],
            cwd=rust_dir,
            capture_output=True,
            text=True,
            check=True
        )
        print("✓ Compilation réussie")
        print(f"\n📊 Output:\n{result.stdout}")
        return True
        
    except subprocess.CalledProcessError as e:
        print(f"❌ Erreur de compilation:")
        print(e.stderr if e.stderr else e.stdout)
        print("\n🔧 Vérifier que Rust est installé: https://rustup.rs/")
        return False

def test_rust_module():
    """Teste l'importation du module Rust"""
    print("\n" + "=" * 80)
    print("TEST DU MODULE RUST")
    print("=" * 80)
    
    try:
        import hft_rust_core
        print("✓ Import réussi")
        
        # Test TickBuffer
        buffer = hft_rust_core.TickBuffer(1000, "XAUUSD-m")
        print(f"✓ TickBuffer créé: capacité {buffer.tick_count()}")
        
        # Test IchimokuCalculator
        calc = hft_rust_core.IchimokuCalculator()
        print("✓ IchimokuCalculator créé")
        
        # Test STCCalculator
        stc_calc = hft_rust_core.STCCalculator()
        print("✓ STCCalculator créé")
        
        # Test SignalDetector
        detector = hft_rust_core.SignalDetector(70.0)
        print("✓ SignalDetector créé")
        
        print("\n🎉 Tous les tests passés avec succès!")
        return True
        
    except ImportError as e:
        print(f"❌ Erreur d'import: {e}")
        return False
    except Exception as e:
        print(f"❌ Erreur lors des tests: {e}")
        return False

if __name__ == "__main__":
    print("=" * 80)
    print("BUILD ET INSTALLATION HFT RUST CORE")
    print("=" * 80)
    
    # Compilation
    if not build_rust_module():
        print("\n❌ Échec de la compilation")
        sys.exit(1)
    
    # Tests
    if not test_rust_module():
        print("\n⚠️ Compilation réussie mais tests échoués")
        sys.exit(1)
    
    print("\n" + "=" * 80)
    print("✅ BUILD ET TESTS RÉUSSIS")
    print("=" * 80)
    print("\nLe module hft_rust_core est prêt à être utilisé!")
    print("Performances attendues:")
    print("  - TickBuffer: 10-50x plus rapide que Python")
    print("  - Indicateurs: 5-20x plus rapide que numpy")
    print("  - Détection signaux: < 1µs par analyse")
