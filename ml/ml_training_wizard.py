#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Assistant d'entraînement ML - Interface        # Utiliser le chemin de la base de données depuis la config ou le chemin par défaut
        from ml.trade_database import DB_PATH
        
        # Déterminer le chemin de la base de données (utiliser DB_PATH par défaut)
        db_path = DB_PATH
        if hasattr(self.config, 'trade_database_path'):
            # Convertir le chemin relatif en chemin absolu si nécessaire
            if not os.path.isabs(self.config.trade_database_path):
                base_dir = Path(__file__).parent.parent
                db_path = base_dir / self.config.trade_database_path
            else:
                db_path = Path(self.config.trade_database_path)
        
        self.trade_db = TradeDatabase(db_path=db_path)
        
        # Utiliser la méthode get_trade_count
        trade_count = self.trade_db.get_trade_count()
        
        print(f"✅ Base de données trouvée: {db_path}")
        print(f"📈 Nombre de trades: {trade_count}")ée et claire
Permet d'entraîner les modèles ML avec guidance étape par étape
"""

import sys
import os
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, List, Union

# Ajouter le chemin du projet
sys.path.insert(0, str(Path(__file__).parent.parent))

from config.trading_config import TradingConfig
from ml.trainer import MLTrainer
from ml.trade_database import TradeDatabase


class MLTrainingWizard:
    """Assistant d'entraînement ML interactif"""
    
    def __init__(self):
        self.config = TradingConfig()
        self.trainer = None
        self.trade_db = None
        
        # Valeurs par défaut pour ML si non définies dans TradingConfig
        if not hasattr(self.config, 'ml_train_test_split'):
            self.config.ml_train_test_split = 0.8  # 80% training, 20% test
    
    def run(self):
        """Lance l'assistant"""
        self.print_header()
        
        # Menu principal
        while True:
            choice = self.show_main_menu()
            
            if choice == '1':
                self.train_new_model()
            elif choice == '2':
                self.retrain_existing()
            elif choice == '3':
                self.check_data_quality()
            elif choice == '4':
                self.view_model_performance()
            elif choice == '5':
                self.configure_training()
            elif choice == '6':
                self.export_model()
            elif choice == '0':
                print("\n👋 À bientôt!")
                break
            else:
                print("\n❌ Choix invalide")
    
    def print_header(self):
        """Affiche l'en-tête"""
        print("\n" + "=" * 80)
        print("🤖 ASSISTANT D'ENTRAÎNEMENT ML - HFT BOT v2.0")
        print("=" * 80)
        print()
        print("Cet assistant vous guide pour entraîner vos modèles de machine learning")
        print("sur les données historiques de trading collectées par le bot.")
        print()
        print("=" * 80)
    
    def show_main_menu(self) -> str:
        """Affiche le menu principal"""
        print("\n" + "─" * 80)
        print("📋 MENU PRINCIPAL")
        print("─" * 80)
        print()
        print("  [1] 🎯 Nouvel entraînement (recommandé)")
        print("  [2] 🔄 Ré-entraîner modèle existant")
        print("  [3] 📊 Vérifier qualité des données")
        print("  [4] 📈 Voir performances des modèles")
        print("  [5] ⚙️  Configurer paramètres d'entraînement")
        print("  [6] 💾 Exporter modèle pour production")
        print("  [0] 🚪 Quitter")
        print()
        
        return input("Votre choix [0-6]: ").strip()
    
    def train_new_model(self):
        """Lance un nouvel entraînement"""
        print("\n" + "=" * 80)
        print("🎯 NOUVEL ENTRAÎNEMENT ML")
        print("=" * 80)
        
        # Étape 1: Vérifier les données
        print("\n📊 Étape 1/5 : Vérification des données")
        print("─" * 80)
        
        # Utiliser le chemin par défaut de la base de données défini dans trade_database.py
        from ml.trade_database import DB_PATH
        self.trade_db = TradeDatabase(db_path=DB_PATH)
        
        # Utiliser la méthode get_trade_count
        trade_count = self.trade_db.get_trade_count()
        
        print(f"✅ Base de données trouvée: {DB_PATH}")
        print(f"📈 Nombre de trades: {trade_count}")
        
        if trade_count < 100:
            print(f"\n⚠️ AVERTISSEMENT: Seulement {trade_count} trades disponibles")
            print("   Minimum recommandé: 1000 trades")
            print("   Optimal: 5000+ trades")
            print()
            print("💡 Conseil: Laissez le bot trader en démo pendant quelques semaines")
            print("   pour collecter plus de données avant d'entraîner le ML.")
            
            confirm = input("\nContinuer quand même? (o/n) [défaut: n]: ").lower().strip()
            if confirm not in ['o', 'oui', 'y', 'yes']:
                print("❌ Entraînement annulé")
                return
        elif trade_count < 1000:
            print(f"\n🟡 {trade_count} trades disponibles (acceptable)")
            print("   Modèles entraînés mais performance limitée")
        else:
            print(f"\n✅ {trade_count} trades disponibles (excellent!)")
            print("   Données suffisantes pour un bon entraînement")
        
        # Étape 2: Choisir les modèles
        print("\n🤖 Étape 2/5 : Sélection des modèles")
        print("─" * 80)
        print()
        print("Modèles disponibles:")
        print("  [1] ✅ Random Forest (rapide, robuste) - RECOMMANDÉ")
        print("  [2] 🧠 LSTM Temporal (séquences, plus lent)")
        print("  [3] 🎮 Q-Learning Agent (apprentissage par renforcement)")
        print("  [4] 🌟 TOUS LES MODÈLES (complet)")
        print()
        
        model_choice = input("Choisir modèle [1-4] [défaut: 1]: ").strip() or '1'
        
        models_to_train = []
        if model_choice == '1':
            models_to_train = ['random_forest']
            print("✅ Random Forest sélectionné")
        elif model_choice == '2':
            models_to_train = ['lstm']
            print("✅ LSTM Temporal sélectionné")
        elif model_choice == '3':
            models_to_train = ['qlearning']
            print("✅ Q-Learning Agent sélectionné")
        else:
            models_to_train = ['random_forest', 'lstm', 'qlearning']
            print("✅ Tous les modèles sélectionnés")
        
        # Étape 3: Configuration split
        print("\n📊 Étape 3/5 : Split des données")
        print("─" * 80)
        print()
        print("Répartition train/test:")
        # S'assurer que ml_train_test_split a une valeur
        train_split = getattr(self.config, 'ml_train_test_split', 0.8)
        print(f"  Train: {train_split * 100:.0f}%")
        print(f"  Test:  {(1 - train_split) * 100:.0f}%")
        print()
        
        modify = input("Modifier la répartition? (o/n) [défaut: n]: ").lower().strip()
        if modify in ['o', 'oui', 'y', 'yes']:
            try:
                new_split = input("Nouveau pourcentage train (ex: 70): ").strip()
                if new_split:
                    # S'assurer que self.config a l'attribut ml_train_test_split
                    if not hasattr(self.config, 'ml_train_test_split'):
                        self.config.ml_train_test_split = 0.8
                    
                    self.config.ml_train_test_split = float(new_split) / 100
                    print(f"✅ Nouveau split: {self.config.ml_train_test_split * 100:.0f}% / {(1 - self.config.ml_train_test_split) * 100:.0f}%")
            except ValueError:
                print("❌ Valeur invalide, split par défaut conservé")
        
        # Étape 4: Dossier de sortie
        print("\n💾 Étape 4/5 : Dossier de sortie")
        print("─" * 80)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        default_output = f"ml_output/training_{timestamp}"
        
        print(f"Dossier par défaut: {default_output}")
        custom_output = input("Personnaliser? (Entrée = défaut): ").strip()
        
        output_dir = custom_output if custom_output else default_output
        print(f"✅ Dossier: {output_dir}")
        
        # Étape 5: Confirmation
        print("\n✅ Étape 5/5 : Confirmation")
        print("=" * 80)
        print()
        print("RÉSUMÉ DE L'ENTRAÎNEMENT:")
        print(f"  📈 Trades: {trade_count}")
        print(f"  🤖 Modèles: {', '.join(models_to_train)}")
        
        # S'assurer que ml_train_test_split a une valeur
        train_split = getattr(self.config, 'ml_train_test_split', 0.8)
        print(f"  📊 Split: {train_split * 100:.0f}% / {(1 - train_split) * 100:.0f}%")
        
        print(f"  💾 Output: {output_dir}")
        print()
        
        # Estimer durée
        estimated_time = self._estimate_training_time(trade_count, len(models_to_train))
        print(f"⏱️  Durée estimée: {estimated_time}")
        print()
        
        confirm = input("🚀 Lancer l'entraînement? (o/n) [défaut: o]: ").lower().strip()
        if confirm in ['', 'o', 'oui', 'y', 'yes']:
            self._execute_training(models_to_train, output_dir)
        else:
            print("❌ Entraînement annulé")
    
    def _estimate_training_time(self, trade_count: int, model_count: int) -> str:
        """Estime la durée d'entraînement"""
        # Estimation grossière
        if trade_count < 500:
            base_time = 1
        elif trade_count < 2000:
            base_time = 3
        elif trade_count < 5000:
            base_time = 5
        else:
            base_time = 10
        
        total_minutes = base_time * model_count
        
        if total_minutes < 5:
            return f"{total_minutes} minute(s)"
        elif total_minutes < 60:
            return f"{total_minutes} minutes"
        else:
            hours = total_minutes // 60
            mins = total_minutes % 60
            return f"{hours}h {mins}min"
    
    def _execute_training(self, models: List[str], output_dir: str):
        """Exécute l'entraînement"""
        print("\n" + "=" * 80)
        print("🚀 ENTRAÎNEMENT EN COURS...")
        print("=" * 80)
        print()
        
        try:
            # Créer le trainer
            from ml.trainer import MLTrainerConfig
            
            # Créer une config spécifique pour le trainer avec le bon output_dir
            train_split = getattr(self.config, 'ml_train_test_split', 0.8)
            trainer_config = MLTrainerConfig(
                output_dir=Path(output_dir),
                test_size=(1 - train_split)
            )
            
            self.trainer = MLTrainer(config=trainer_config)
            
            print("📊 Chargement des données...")
            
            # Lancer l'entraînement
            print("🤖 Entraînement des modèles...")
            print("   (Cela peut prendre plusieurs minutes)")
            print()
            
            results = self.trainer.run()
            
            # Afficher résultats
            print("\n" + "=" * 80)
            print("✅ ENTRAÎNEMENT TERMINÉ!")
            print("=" * 80)
            print()
            
            if results and 'metrics' in results:
                print("📊 RÉSULTATS:")
                print()
                
                for model_name, metrics in results['metrics'].items():
                    print(f"  🤖 {model_name}:")
                    print(f"      Accuracy:  {metrics.get('accuracy', 0) * 100:.2f}%")
                    print(f"      Precision: {metrics.get('precision', 0) * 100:.2f}%")
                    print(f"      Recall:    {metrics.get('recall', 0) * 100:.2f}%")
                    print(f"      F1-Score:  {metrics.get('f1', 0) * 100:.2f}%")
                    print()
                
                print(f"💾 Modèles sauvegardés dans: {output_dir}")
                print(f"📈 Rapport complet: {output_dir}/training_report.json")
            
            print()
            print("💡 Prochaines étapes:")
            print("   1. Vérifier les métriques ci-dessus")
            print("   2. Si accuracy > 60%, le modèle est bon")
            print("   3. Activer 'ML Auto' dans l'interface pour utiliser le modèle")
            print("   4. Surveiller les performances en live")
            print()
            
        except Exception as e:
            print(f"\n❌ ERREUR pendant l'entraînement: {e}")
            print()
            print("💡 Suggestions:")
            print("   - Vérifier que la base de données existe")
            print("   - S'assurer d'avoir assez de trades (>100)")
            print("   - Consulter les logs pour plus de détails")
            print()
    
    def retrain_existing(self):
        """Ré-entraîne un modèle existant"""
        print("\n🔄 Ré-entraînement en construction...")
        print("   Cette fonctionnalité permet de ré-entraîner un modèle")
        print("   avec de nouvelles données pour améliorer ses performances.")
        input("\nAppuyez sur Entrée pour continuer...")
    
    def check_data_quality(self):
        """Vérifie la qualité des données"""
        print("\n" + "=" * 80)
        print("📊 VÉRIFICATION QUALITÉ DES DONNÉES")
        print("=" * 80)
        
        try:
            # Utiliser le chemin par défaut de la base de données
            from ml.trade_database import DB_PATH
            self.trade_db = TradeDatabase(db_path=DB_PATH)
            
            print("\n📈 Statistiques générales:")
            print("─" * 80)
            
            trade_count = self.trade_db.get_trade_count()
            print(f"  Total trades: {trade_count}")
            
            if trade_count > 0:
                # Récupérer tous les trades
                trades = self.trade_db.get_all_trades()
                
                # Calculer stats
                wins = sum(1 for t in trades if t.get('profit_loss', 0) > 0)
                losses = sum(1 for t in trades if t.get('profit_loss', 0) < 0)
                breakeven = trade_count - wins - losses
                
                winrate = (wins / trade_count * 100) if trade_count > 0 else 0
                
                print(f"  Wins: {wins} ({wins/trade_count*100:.1f}%)")
                print(f"  Losses: {losses} ({losses/trade_count*100:.1f}%)")
                print(f"  Breakeven: {breakeven}")
                print(f"  Winrate: {winrate:.2f}%")
                print()
                
                # Recommandations
                print("💡 Recommandations:")
                print("─" * 80)
                
                if trade_count < 100:
                    print("  ⚠️  Pas assez de données (< 100 trades)")
                    print("      → Laissez le bot collecter plus de trades")
                elif trade_count < 1000:
                    print("  🟡 Données limitées (< 1000 trades)")
                    print("      → ML fonctionnel mais performances limitées")
                else:
                    print("  ✅ Excellent volume de données (>= 1000 trades)")
                    print("      → Prêt pour un bon entraînement ML")
                
                print()
                
                if winrate < 40:
                    print("  ⚠️  Winrate faible (< 40%)")
                    print("      → Vérifier la stratégie de base")
                    print("      → ML ne peut pas corriger une stratégie cassée")
                elif winrate > 70:
                    print("  ✅ Excellent winrate (> 70%)")
                    print("      → ML peut encore améliorer")
                else:
                    print("  ✅ Winrate acceptable (40-70%)")
                    print("      → Bon candidat pour amélioration ML")
            
            print()
            
        except Exception as e:
            print(f"\n❌ Erreur: {e}")
            print("   Base de données introuvable ou corrompue")
        
        input("\nAppuyez sur Entrée pour continuer...")
    
    def view_model_performance(self):
        """Affiche les performances des modèles"""
        print("\n📈 Performances des modèles en construction...")
        input("\nAppuyez sur Entrée pour continuer...")
    
    def configure_training(self):
        """Configure les paramètres d'entraînement"""
        print("\n⚙️  Configuration des paramètres en construction...")
        input("\nAppuyez sur Entrée pour continuer...")
    
    def export_model(self):
        """Exporte un modèle pour production"""
        print("\n💾 Export de modèle en construction...")
        input("\nAppuyez sur Entrée pour continuer...")


def main():
    """Point d'entrée principal"""
    wizard = MLTrainingWizard()
    try:
        wizard.run()
    except KeyboardInterrupt:
        print("\n\n⚠️ Interruption utilisateur (Ctrl+C)")
        print("👋 À bientôt!")
    except Exception as e:
        print(f"\n❌ Erreur fatale: {e}")
        import traceback
        traceback.print_exc()


if __name__ == "__main__":
    main()
