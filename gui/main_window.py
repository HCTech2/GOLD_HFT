#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
Interface graphique principale du bot HFT
"""

import os
import tkinter as tk
from tkinter import ttk, scrolledtext, messagebox, filedialog
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path
from typing import Optional
import logging
import json
from dataclasses import asdict

from config.trading_config import TradingConfig
from config.settings_manager import SettingsManager, extract_saveable_config
from trading.strategy import HFTStrategy
from gui.indicator_worker import IndicatorWorker
from utils.mt5_helper import get_account_summary, get_positions_summary, format_duration
from ml.trainer import MLTrainer, MLTrainerConfig

logger = logging.getLogger(__name__)


class HFTBotGUI:
    """Interface graphique Tkinter pour le bot HFT"""
    
    def __init__(self, config: TradingConfig):
        self.config = config
        self.strategy: Optional[HFTStrategy] = None
        self.indicator_worker: Optional[IndicatorWorker] = None
        
        # 🆕 Gestionnaire de sauvegarde des paramètres
        self.settings_manager = SettingsManager()
        
        # État
        self.is_bot_running = False
        self.start_time = None
        
        # Fenêtre principale (DOIT ÊTRE CRÉÉE EN PREMIER pour Tkinter)
        self.root = tk.Tk()
        self.root.title(f"HFT Bot - {config.symbol}")
        self.root.geometry("1200x800")
        self.root.protocol("WM_DELETE_WINDOW", self.on_closing)
        
        # Variables de paramètres ajustables (APRÈS la création de root)
        self.sl_multiplier = tk.IntVar(value=100)  # 100 = 1.0x
        self.tp_multiplier = tk.IntVar(value=100)  # 100 = 1.0x
        self.volume_multiplier = tk.IntVar(value=100)  # 100 = 1.0x
        self.spread_max = tk.DoubleVar(value=config.spread_threshold)
        
        # Paramètres Ichimoku
        self.tenkan_var = tk.IntVar(value=config.ichimoku_tenkan_sen)
        self.kijun_var = tk.IntVar(value=config.ichimoku_kijun_sen)
        self.senkou_var = tk.IntVar(value=config.ichimoku_senkou_span_b)
        
        # Paramètres STC
        self.stc_period_var = tk.IntVar(value=config.stc_period)
        self.stc_buy_var = tk.DoubleVar(value=config.stc_threshold_buy)
        self.stc_sell_var = tk.DoubleVar(value=config.stc_threshold_sell)
        
        # Contrôles
        self.enable_kill_zone_var = tk.BooleanVar(value=config.kill_zone_enabled)
        self.ignore_stc_var = tk.BooleanVar(value=config.ignore_stc)
        self.max_orders_var = tk.IntVar(value=config.max_simultaneous_orders)
        self.strategy_timeframe_var = tk.StringVar(value=config.strategy_timeframe)
        
        # Profit Réactif (nouveau)
        self.reactive_profit_enabled_var = tk.BooleanVar(value=config.reactive_profit_enabled)
        self.profit_threshold_per_position_var = tk.DoubleVar(value=config.profit_threshold_per_position)
        self.profit_threshold_cumulative_var = tk.DoubleVar(value=config.profit_threshold_cumulative)
        
        # 🌊 Sweep - Mise de départ (nouveau)
        self.sweep_base_volume_var = tk.DoubleVar(value=getattr(config, 'sweep_base_volume', 0.01))

        # 🧠 ML Trainer - paramètres interactifs
        self.ml_dataset_limit_var = tk.StringVar(value="")
        self.ml_test_size_var = tk.DoubleVar(value=0.2)
        self.ml_random_state_var = tk.IntVar(value=42)
        self.ml_output_dir_var = tk.StringVar(value="ml/models/active")
        self.ml_persist_var = tk.BooleanVar(value=True)
        self.ml_train_rf_var = tk.BooleanVar(value=True)
        self.ml_train_lstm_var = tk.BooleanVar(value=True)
        self.ml_train_rl_var = tk.BooleanVar(value=True)
        self.ml_sequence_device_var = tk.StringVar(value="")

        self.ml_status_var = tk.StringVar(value="Prêt à entraîner")
        self.ml_last_report_var = tk.StringVar(value="Aucun entraînement réalisé")
        self.ml_auto_enabled_var = tk.BooleanVar(value=False)
        self.ml_auto_interval_var = tk.IntVar(value=180)  # minutes
        self.ml_auto_status_var = tk.StringVar(value="Auto: désactivé")
        self.ml_auto_next_run_var = tk.StringVar(value="Prochaine exécution: --")
        
        # Couleurs
        self.bg_color = "#1e1e1e"
        self.fg_color = "#ffffff"
        self.accent_color = "#007acc"
        self.success_color = "#28a745"
        self.danger_color = "#dc3545"
        self.warning_color = "#ffc107"
        
        self.root.configure(bg=self.bg_color)
        
        # Créer l'interface
        self._create_widgets()
        
        # Event pour arrêter les mises à jour
        self.update_stop_event = threading.Event()

        # État ML Trainer
        self.ml_training_thread = None
        self.ml_training_lock = threading.Lock()
        self.ml_last_report_path = None
        self.ml_history_paths: list[Path] = []
        self.ml_auto_after_id = None
        
        logger.info("GUI initialisée")
    
    def _create_widgets(self) -> None:
        """Crée tous les widgets de l'interface"""
        
        # Frame principal
        main_frame = tk.Frame(self.root, bg=self.bg_color)
        main_frame.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Titre
        title_frame = tk.Frame(main_frame, bg=self.bg_color)
        title_frame.pack(fill=tk.X, pady=(0, 10))
        
        title_label = tk.Label(
            title_frame,
            text=f"🤖 HFT Trading Bot - {self.config.symbol}",
            font=("Arial", 18, "bold"),
            bg=self.bg_color,
            fg=self.accent_color
        )
        title_label.pack(side=tk.LEFT)
        
        # Boutons de contrôle
        control_frame = tk.Frame(main_frame, bg=self.bg_color)
        control_frame.pack(fill=tk.X, pady=(0, 10))

        
        self.start_button = tk.Button(
            control_frame,
            text="▶ Démarrer",
            command=self.start_bot,
            font=("Arial", 12, "bold"),
            bg=self.success_color,
            fg=self.fg_color,
            width=15,
            height=2
        )
        self.start_button.pack(side=tk.LEFT, padx=5)
        
        self.stop_button = tk.Button(
            control_frame,
            text="■ Arrêter",
            command=self.stop_bot,
            font=("Arial", 12, "bold"),
            bg=self.danger_color,
            fg=self.fg_color,
            width=15,
            height=2,
            state=tk.DISABLED
        )
        self.stop_button.pack(side=tk.LEFT, padx=5)
        
        self.status_label = tk.Label(
            control_frame,
            text="● Status: Arrêté",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.danger_color
        )
        self.status_label.pack(side=tk.LEFT, padx=20)
        
        # Notebook (onglets)
        notebook = ttk.Notebook(main_frame)
        notebook.pack(fill=tk.BOTH, expand=True)
        
        # Style pour notebook
        style = ttk.Style()
        style.theme_use('default')
        style.configure('TNotebook', background=self.bg_color, borderwidth=0)
        style.configure('TNotebook.Tab', padding=[20, 10], font=('Arial', 10, 'bold'))
        
        # Onglet Dashboard
        self.dashboard_frame = tk.Frame(notebook, bg=self.bg_color)
        notebook.add(self.dashboard_frame, text="📊 Dashboard")
        self._create_dashboard()
        
        # Onglet Positions
        self.positions_frame = tk.Frame(notebook, bg=self.bg_color)
        notebook.add(self.positions_frame, text="💼 Positions")
        self._create_positions_tab()
        
        # Onglet Indicateurs
        self.indicators_frame = tk.Frame(notebook, bg=self.bg_color)
        notebook.add(self.indicators_frame, text="📈 Indicateurs")
        self._create_indicators_tab()
        
        # Onglet Paramètres
        self.params_frame = tk.Frame(notebook, bg=self.bg_color)
        notebook.add(self.params_frame, text="⚙️ Paramètres")
        self._create_params_tab()
        
        # Onglet Logs
        self.logs_frame = tk.Frame(notebook, bg=self.bg_color)
        notebook.add(self.logs_frame, text="📝 Logs")
        self._create_logs_tab()

        # Onglet ML Trainer
        self.ml_frame = tk.Frame(notebook, bg=self.bg_color)
        notebook.add(self.ml_frame, text="🧠 ML Trainer")
        self._create_ml_tab()
    
    def _create_dashboard(self) -> None:
        """Crée l'onglet dashboard"""
        
        # Frame compte
        account_frame = tk.LabelFrame(
            self.dashboard_frame,
            text="💰 Compte",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=10,
            pady=10
        )
        account_frame.grid(row=0, column=0, sticky="nsew", padx=5, pady=5)
        
        self.balance_label = tk.Label(account_frame, text="Balance: --", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.balance_label.pack(anchor=tk.W)
        
        self.equity_label = tk.Label(account_frame, text="Equity: --", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.equity_label.pack(anchor=tk.W)
        
        self.margin_label = tk.Label(account_frame, text="Marge Libre: --", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.margin_label.pack(anchor=tk.W)
        
        self.profit_label = tk.Label(account_frame, text="Profit: --", font=("Arial", 11), bg=self.bg_color, fg=self.success_color)
        self.profit_label.pack(anchor=tk.W)
        
        # Frame stratégie
        strategy_frame = tk.LabelFrame(
            self.dashboard_frame,
            text="🎯 Stratégie",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=10,
            pady=10
        )
        strategy_frame.grid(row=0, column=1, sticky="nsew", padx=5, pady=5)
        
        self.signals_label = tk.Label(strategy_frame, text="Signaux générés: 0", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.signals_label.pack(anchor=tk.W)
        
        self.orders_label = tk.Label(strategy_frame, text="Ordres envoyés: 0", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.orders_label.pack(anchor=tk.W)
        
        self.rejected_label = tk.Label(strategy_frame, text="Ordres rejetés: 0", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.rejected_label.pack(anchor=tk.W)
        
        self.uptime_label = tk.Label(strategy_frame, text="Uptime: --", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.uptime_label.pack(anchor=tk.W)
        
        # Frame ticks
        ticks_frame = tk.LabelFrame(
            self.dashboard_frame,
            text="⚡ Flux de Données",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=10,
            pady=10
        )
        ticks_frame.grid(row=1, column=0, sticky="nsew", padx=5, pady=5)
        
        self.ticks_label = tk.Label(ticks_frame, text="Ticks reçus: 0", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.ticks_label.pack(anchor=tk.W)
        
        self.last_tick_label = tk.Label(ticks_frame, text="Dernier tick: --", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.last_tick_label.pack(anchor=tk.W)
        
        self.analysis_time_label = tk.Label(ticks_frame, text="Temps analyse: --", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.analysis_time_label.pack(anchor=tk.W)
        
        # Frame positions
        positions_summary_frame = tk.LabelFrame(
            self.dashboard_frame,
            text="💼 Positions",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=10,
            pady=10
        )
        positions_summary_frame.grid(row=1, column=1, sticky="nsew", padx=5, pady=5)
        
        self.positions_count_label = tk.Label(positions_summary_frame, text="Positions ouvertes: 0", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.positions_count_label.pack(anchor=tk.W)
        
        self.total_trades_label = tk.Label(positions_summary_frame, text="Trades totaux: 0", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.total_trades_label.pack(anchor=tk.W)
        
        self.positions_profit_label = tk.Label(positions_summary_frame, text="Profit positions: --", font=("Arial", 11), bg=self.bg_color, fg=self.fg_color)
        self.positions_profit_label.pack(anchor=tk.W)
        
        # Frame Sweep (nouvelle fonctionnalité)
        sweep_frame = tk.LabelFrame(
            self.dashboard_frame,
            text="🌊 Sweep Status",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=10,
            pady=10
        )
        sweep_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=5, pady=5)
        
        self.sweep_status_label = tk.Label(sweep_frame, text="Sweep: INACTIF", font=("Arial", 11, "bold"), bg=self.bg_color, fg=self.fg_color)
        self.sweep_status_label.pack(anchor=tk.W)
        
        self.sweep_direction_label = tk.Label(sweep_frame, text="Direction: --", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color)
        self.sweep_direction_label.pack(anchor=tk.W)
        
        self.sweep_progress_label = tk.Label(sweep_frame, text="Progression: 0/0 ordres (0.0%)", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color)
        self.sweep_progress_label.pack(anchor=tk.W)
        
        self.sweep_phase_label = tk.Label(sweep_frame, text="Phase: --", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color)
        self.sweep_phase_label.pack(anchor=tk.W)
        
        # Configuration grille
        self.dashboard_frame.grid_columnconfigure(0, weight=1)
        self.dashboard_frame.grid_columnconfigure(1, weight=1)
        self.dashboard_frame.grid_rowconfigure(0, weight=1)
        self.dashboard_frame.grid_rowconfigure(1, weight=1)
        self.dashboard_frame.grid_rowconfigure(2, weight=1)
    
    def _create_positions_tab(self) -> None:
        """Crée l'onglet positions"""
        
        # Tableau des positions
        columns = ("Ticket", "Type", "Volume", "Prix Entrée", "SL", "TP", "Profit", "Durée")
        
        self.positions_tree = ttk.Treeview(self.positions_frame, columns=columns, show='headings', height=15)
        
        for col in columns:
            self.positions_tree.heading(col, text=col)
            self.positions_tree.column(col, width=120, anchor=tk.CENTER)
        
        self.positions_tree.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Scrollbar
        scrollbar = ttk.Scrollbar(self.positions_tree, orient=tk.VERTICAL, command=self.positions_tree.yview)
        self.positions_tree.configure(yscroll=scrollbar.set)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _create_indicators_tab(self) -> None:
        """Crée l'onglet indicateurs"""
        
        # Frame Ichimoku (timeframe dynamique)
        self.ichimoku_frame = tk.LabelFrame(
            self.indicators_frame,
            text=f"📊 Ichimoku {self.config.strategy_timeframe}",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=10,
            pady=10
        )
        self.ichimoku_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.tenkan_m1_label = tk.Label(self.ichimoku_frame, text="Tenkan-sen (ligne rapide): Calcul en cours...", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color)
        self.tenkan_m1_label.pack(anchor=tk.W)
        
        self.kijun_m1_label = tk.Label(self.ichimoku_frame, text="Kijun-sen (ligne lente): Calcul en cours...", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color)
        self.kijun_m1_label.pack(anchor=tk.W)
        
        self.signal_m1_label = tk.Label(self.ichimoku_frame, text="Signal: ⚪ En attente de données", font=("Arial", 11, "bold"), bg=self.bg_color, fg=self.warning_color)
        self.signal_m1_label.pack(anchor=tk.W)
        
        # Frame STC (timeframe dynamique)
        self.stc_frame = tk.LabelFrame(
            self.indicators_frame,
            text=f"📈 STC {self.config.strategy_timeframe} (Schaff Trend Cycle)",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=10,
            pady=10
        )
        self.stc_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.stc_m1_value_label = tk.Label(self.stc_frame, text="Valeur STC: 0 / 100", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color)
        self.stc_m1_value_label.pack(anchor=tk.W)
        
        self.stc_m1_zone_label = tk.Label(self.stc_frame, text="Zone: ⚪ En attente de données", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color)
        self.stc_m1_zone_label.pack(anchor=tk.W)
        
        # Informations supplémentaires
        info_frame = tk.LabelFrame(
            self.indicators_frame,
            text="ℹ️ Informations",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=10,
            pady=10
        )
        info_frame.pack(fill=tk.X, padx=10, pady=5)
        
        self.last_update_label = tk.Label(info_frame, text="Dernière mise à jour: --", font=("Arial", 9), bg=self.bg_color, fg=self.fg_color)
        self.last_update_label.pack(anchor=tk.W)
        
        self.computation_time_label = tk.Label(info_frame, text="Temps de calcul: --", font=("Arial", 9), bg=self.bg_color, fg=self.fg_color)
        self.computation_time_label.pack(anchor=tk.W)
        
        tk.Label(
            info_frame,
            text="🔄 Rafraîchissement: Automatique toutes les secondes",
            font=("Arial", 9, "italic"),
            bg=self.bg_color,
            fg=self.accent_color
        ).pack(anchor=tk.W, pady=(5, 0))
    
    def _create_params_tab(self) -> None:
        """Crée l'onglet paramètres avec tous les contrôles ajustables"""
        
        # Conteneur scrollable
        canvas = tk.Canvas(self.params_frame, bg=self.bg_color)
        scrollbar = tk.Scrollbar(self.params_frame, orient=tk.VERTICAL, command=canvas.yview)
        scrollable_frame = tk.Frame(canvas, bg=self.bg_color)
        
        scrollable_frame.bind(
            "<Configure>",
            lambda e: canvas.configure(scrollregion=canvas.bbox("all"))
        )
        
        canvas.create_window((0, 0), window=scrollable_frame, anchor=tk.NW)
        canvas.configure(yscrollcommand=scrollbar.set)
        
        # ===== MULTIPLICATEURS =====
        multipliers_frame = tk.LabelFrame(
            scrollable_frame,
            text="📊 Multiplicateurs (SL/TP/Volume)",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.accent_color,
            padx=15,
            pady=10
        )
        multipliers_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Stop Loss Multiplier
        tk.Label(multipliers_frame, text="Stop Loss %:", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        sl_scale = tk.Scale(
            multipliers_frame,
            from_=50,
            to=200,
            orient=tk.HORIZONTAL,
            variable=self.sl_multiplier,
            length=300,
            bg=self.bg_color,
            fg=self.fg_color,
            highlightthickness=0
        )
        sl_scale.grid(row=0, column=1, padx=5, pady=5)
        self.sl_value_label = tk.Label(multipliers_frame, text="100%", font=("Arial", 10, "bold"), bg=self.bg_color, fg=self.success_color)
        self.sl_value_label.grid(row=0, column=2, padx=5, pady=5)
        sl_scale.config(command=lambda v: self.sl_value_label.config(text=f"{int(float(v))}%"))
        
        # Take Profit Multiplier
        tk.Label(multipliers_frame, text="Take Profit %:", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color).grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        tp_scale = tk.Scale(
            multipliers_frame,
            from_=50,
            to=200,
            orient=tk.HORIZONTAL,
            variable=self.tp_multiplier,
            length=300,
            bg=self.bg_color,
            fg=self.fg_color,
            highlightthickness=0
        )
        tp_scale.grid(row=1, column=1, padx=5, pady=5)
        self.tp_value_label = tk.Label(multipliers_frame, text="100%", font=("Arial", 10, "bold"), bg=self.bg_color, fg=self.success_color)
        self.tp_value_label.grid(row=1, column=2, padx=5, pady=5)
        tp_scale.config(command=lambda v: self.tp_value_label.config(text=f"{int(float(v))}%"))
        
        # Volume Multiplier
        tk.Label(multipliers_frame, text="Volume %:", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color).grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        vol_scale = tk.Scale(
            multipliers_frame,
            from_=50,
            to=200,
            orient=tk.HORIZONTAL,
            variable=self.volume_multiplier,
            length=300,
            bg=self.bg_color,
            fg=self.fg_color,
            highlightthickness=0
        )
        vol_scale.grid(row=2, column=1, padx=5, pady=5)
        self.vol_value_label = tk.Label(multipliers_frame, text="100%", font=("Arial", 10, "bold"), bg=self.bg_color, fg=self.success_color)
        self.vol_value_label.grid(row=2, column=2, padx=5, pady=5)
        vol_scale.config(command=lambda v: self.vol_value_label.config(text=f"{int(float(v))}%"))
        
        # Spread Max
        tk.Label(multipliers_frame, text="Spread Max ($):", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color).grid(row=3, column=0, sticky=tk.W, padx=5, pady=5)
        spread_scale = tk.Scale(
            multipliers_frame,
            from_=0.01,
            to=20.0,
            resolution=0.01,
            orient=tk.HORIZONTAL,
            variable=self.spread_max,
            length=300,
            bg=self.bg_color,
            fg=self.fg_color,
            highlightthickness=0
        )
        spread_scale.grid(row=3, column=1, padx=5, pady=5)
        self.spread_value_label = tk.Label(multipliers_frame, text=f"{self.spread_max.get():.2f}$", font=("Arial", 10, "bold"), bg=self.bg_color, fg=self.success_color)
        self.spread_value_label.grid(row=3, column=2, padx=5, pady=5)
        spread_scale.config(command=lambda v: self.spread_value_label.config(text=f"{float(v):.2f}$"))
        
        # ===== ICHIMOKU =====
        ichimoku_frame = tk.LabelFrame(
            scrollable_frame,
            text="📈 Paramètres Ichimoku",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.accent_color,
            padx=15,
            pady=10
        )
        ichimoku_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Tenkan-sen
        tk.Label(ichimoku_frame, text="Tenkan-sen (Périodes):", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        tenkan_spin = tk.Spinbox(ichimoku_frame, from_=5, to=30, textvariable=self.tenkan_var, width=10, font=("Arial", 10))
        tenkan_spin.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Kijun-sen
        tk.Label(ichimoku_frame, text="Kijun-sen (Périodes):", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color).grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        kijun_spin = tk.Spinbox(ichimoku_frame, from_=10, to=60, textvariable=self.kijun_var, width=10, font=("Arial", 10))
        kijun_spin.grid(row=1, column=1, sticky=tk.W, padx=5, pady=5)
        
        # Senkou Span B
        tk.Label(ichimoku_frame, text="Senkou Span B (Périodes):", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color).grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        senkou_spin = tk.Spinbox(ichimoku_frame, from_=20, to=100, textvariable=self.senkou_var, width=10, font=("Arial", 10))
        senkou_spin.grid(row=2, column=1, sticky=tk.W, padx=5, pady=5)
        
        # ===== STC =====
        stc_frame = tk.LabelFrame(
            scrollable_frame,
            text="📉 Paramètres STC (Schaff Trend Cycle)",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.accent_color,
            padx=15,
            pady=10
        )
        stc_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # STC Period
        tk.Label(stc_frame, text="Période STC:", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color).grid(row=0, column=0, sticky=tk.W, padx=5, pady=5)
        stc_period_spin = tk.Spinbox(stc_frame, from_=5, to=20, textvariable=self.stc_period_var, width=10, font=("Arial", 10))
        stc_period_spin.grid(row=0, column=1, sticky=tk.W, padx=5, pady=5)
        
        # STC Buy Threshold
        tk.Label(stc_frame, text="Seuil Achat:", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color).grid(row=1, column=0, sticky=tk.W, padx=5, pady=5)
        stc_buy_scale = tk.Scale(
            stc_frame,
            from_=1,
            to=50,
            resolution=0.1,
            orient=tk.HORIZONTAL,
            variable=self.stc_buy_var,
            length=300,
            bg=self.bg_color,
            fg=self.fg_color,
            highlightthickness=0
        )
        stc_buy_scale.grid(row=1, column=1, padx=5, pady=5)
        self.stc_buy_label = tk.Label(stc_frame, text=f"{self.stc_buy_var.get():.1f}", font=("Arial", 10, "bold"), bg=self.bg_color, fg=self.success_color)
        self.stc_buy_label.grid(row=1, column=2, padx=5, pady=5)
        stc_buy_scale.config(command=lambda v: self.stc_buy_label.config(text=f"{float(v):.1f}"))
        
        # STC Sell Threshold
        tk.Label(stc_frame, text="Seuil Vente:", font=("Arial", 10), bg=self.bg_color, fg=self.fg_color).grid(row=2, column=0, sticky=tk.W, padx=5, pady=5)
        stc_sell_scale = tk.Scale(
            stc_frame,
            from_=50,
            to=99,
            resolution=0.1,
            orient=tk.HORIZONTAL,
            variable=self.stc_sell_var,
            length=300,
            bg=self.bg_color,
            fg=self.fg_color,
            highlightthickness=0
        )
        stc_sell_scale.grid(row=2, column=1, padx=5, pady=5)
        self.stc_sell_label = tk.Label(stc_frame, text=f"{self.stc_sell_var.get():.1f}", font=("Arial", 10, "bold"), bg=self.bg_color, fg=self.danger_color)
        self.stc_sell_label.grid(row=2, column=2, padx=5, pady=5)
        stc_sell_scale.config(command=lambda v: self.stc_sell_label.config(text=f"{float(v):.1f}"))
        
        # ===== TIMEFRAME =====
        timeframe_frame = tk.LabelFrame(
            scrollable_frame,
            text="⏱️ Timeframe de Stratégie",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.accent_color,
            padx=15,
            pady=10
        )
        timeframe_frame.pack(fill=tk.X, padx=10, pady=10)
        
        tk.Radiobutton(
            timeframe_frame,
            text="TICK (Ultra-réactif)",
            variable=self.strategy_timeframe_var,
            value="TICK",
            font=("Arial", 10),
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.accent_color
        ).pack(anchor=tk.W, padx=5, pady=3)
        
        tk.Radiobutton(
            timeframe_frame,
            text="M1 (1 minute)",
            variable=self.strategy_timeframe_var,
            value="M1",
            font=("Arial", 10),
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.accent_color
        ).pack(anchor=tk.W, padx=5, pady=3)
        
        tk.Radiobutton(
            timeframe_frame,
            text="M5 (5 minutes)",
            variable=self.strategy_timeframe_var,
            value="M5",
            font=("Arial", 10),
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.accent_color
        ).pack(anchor=tk.W, padx=5, pady=3)
        
        # ===== CONTRÔLES =====
        controls_frame = tk.LabelFrame(
            scrollable_frame,
            text="🎛️ Contrôles Avancés",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.accent_color,
            padx=15,
            pady=10
        )
        controls_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Kill Zone
        kill_zone_check = tk.Checkbutton(
            controls_frame,
            text="Activer Kill Zone (Londres/NY uniquement)",
            variable=self.enable_kill_zone_var,
            command=self.update_kill_zone,
            font=("Arial", 10),
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.accent_color
        )
        kill_zone_check.pack(anchor=tk.W, padx=5, pady=5)
        
        # Ignorer STC
        ignore_stc_check = tk.Checkbutton(
            controls_frame,
            text="Ignorer STC (utiliser Ichimoku uniquement)",
            variable=self.ignore_stc_var,
            command=self.update_ignore_stc,
            font=("Arial", 10),
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.accent_color
        )
        ignore_stc_check.pack(anchor=tk.W, padx=5, pady=5)
        
        # Max ordres
        max_orders_container = tk.Frame(controls_frame, bg=self.bg_color)
        max_orders_container.pack(anchor=tk.W, padx=5, pady=5)
        
        tk.Label(
            max_orders_container,
            text="Ordres simultanés maximum:",
            font=("Arial", 10),
            bg=self.bg_color,
            fg=self.fg_color
        ).pack(side=tk.LEFT, padx=5)
        
        max_orders_spin = tk.Spinbox(
            max_orders_container,
            from_=1,
            to=10,
            textvariable=self.max_orders_var,
            width=5,
            font=("Arial", 10),
            command=self.update_max_orders
        )
        max_orders_spin.pack(side=tk.LEFT, padx=5)
        max_orders_spin.bind('<Return>', lambda e: self.update_max_orders())
        max_orders_spin.bind('<FocusOut>', lambda e: self.update_max_orders())
        
        # ===== PROFIT RÉACTIF (NOUVEAU) =====
        profit_frame = tk.LabelFrame(
            scrollable_frame,
            text="💰 Profit Réactif (Clôture automatique en profit)",
            font=("Arial", 11, "bold"),
            bg=self.bg_color,
            fg=self.success_color,
            padx=10,
            pady=10
        )
        profit_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Activer profit réactif
        profit_enabled_check = tk.Checkbutton(
            profit_frame,
            text="✅ Activer le profit réactif (100% profitable)",
            variable=self.reactive_profit_enabled_var,
            command=self.update_reactive_profit,
            font=("Arial", 10, "bold"),
            bg=self.bg_color,
            fg=self.success_color,
            selectcolor=self.accent_color
        )
        profit_enabled_check.pack(anchor=tk.W, padx=5, pady=5)
        
        # Seuil par position
        profit_per_pos_container = tk.Frame(profit_frame, bg=self.bg_color)
        profit_per_pos_container.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(
            profit_per_pos_container,
            text="Seuil par position (fermer si profit ≥):",
            font=("Arial", 10),
            bg=self.bg_color,
            fg=self.fg_color
        ).pack(side=tk.LEFT, padx=5)
        
        self.profit_per_pos_scale = tk.Scale(
            profit_per_pos_container,
            from_=1.0,
            to=50.0,
            resolution=0.5,
            orient=tk.HORIZONTAL,
            variable=self.profit_threshold_per_position_var,
            length=300,
            bg=self.bg_color,
            fg=self.fg_color,
            troughcolor=self.accent_color,
            highlightthickness=0
        )
        self.profit_per_pos_scale.pack(side=tk.LEFT, padx=5)
        
        self.profit_per_pos_value = tk.Label(
            profit_per_pos_container,
            text=f"{self.profit_threshold_per_position_var.get():.1f}$",
            font=("Arial", 10, "bold"),
            bg=self.bg_color,
            fg=self.success_color,
            width=8
        )
        self.profit_per_pos_value.pack(side=tk.LEFT, padx=5)
        self.profit_per_pos_scale.config(
            command=lambda v: self.profit_per_pos_value.config(text=f"{float(v):.1f}$")
        )
        
        # Seuil cumulatif
        profit_cumulative_container = tk.Frame(profit_frame, bg=self.bg_color)
        profit_cumulative_container.pack(fill=tk.X, padx=5, pady=5)
        
        tk.Label(
            profit_cumulative_container,
            text="Seuil cumulatif (fermer toutes si total ≥):",
            font=("Arial", 10),
            bg=self.bg_color,
            fg=self.fg_color
        ).pack(side=tk.LEFT, padx=5)
        
        self.profit_cumulative_scale = tk.Scale(
            profit_cumulative_container,
            from_=5.0,
            to=100.0,
            resolution=1.0,
            orient=tk.HORIZONTAL,
            variable=self.profit_threshold_cumulative_var,
            length=300,
            bg=self.bg_color,
            fg=self.fg_color,
            troughcolor=self.success_color,
            highlightthickness=0
        )
        self.profit_cumulative_scale.pack(side=tk.LEFT, padx=5)
        
        self.profit_cumulative_value = tk.Label(
            profit_cumulative_container,
            text=f"{self.profit_threshold_cumulative_var.get():.0f}$",
            font=("Arial", 10, "bold"),
            bg=self.bg_color,
            fg=self.success_color,
            width=8
        )
        self.profit_cumulative_value.pack(side=tk.LEFT, padx=5)
        self.profit_cumulative_scale.config(
            command=lambda v: self.profit_cumulative_value.config(text=f"{float(v):.0f}$")
        )
        
        # ===== 🌊 SWEEP - MISE DE DÉPART =====
        sweep_frame = tk.LabelFrame(
            scrollable_frame,
            text="🌊 Sweep - Mise de Départ (Martingale Additive)",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.accent_color,
            padx=15,
            pady=10
        )
        sweep_frame.pack(fill=tk.X, padx=10, pady=10)
        
        # Explication
        sweep_info = tk.Label(
            sweep_frame,
            text="Volume de base pour la première position du sweep.\nLes positions suivantes augmentent de manière additive:\nPos 1: 1×base, Pos 2: 2×base, Pos 3: 3×base, etc.",
            font=("Arial", 9),
            bg=self.bg_color,
            fg=self.warning_color,
            justify=tk.LEFT
        )
        sweep_info.pack(anchor=tk.W, pady=(0, 10))
        
        # Conteneur horizontal
        sweep_container = tk.Frame(sweep_frame, bg=self.bg_color)
        sweep_container.pack(fill=tk.X)
        
        tk.Label(
            sweep_container,
            text="Mise de base (lots):",
            font=("Arial", 10),
            bg=self.bg_color,
            fg=self.fg_color
        ).pack(side=tk.LEFT, padx=5)
        
        # Scale pour mise de base (0.01 à 100.00)
        self.sweep_base_volume_scale = tk.Scale(
            sweep_container,
            from_=0.01,
            to=100.0,
            resolution=0.01,
            orient=tk.HORIZONTAL,
            variable=self.sweep_base_volume_var,
            length=300,
            bg=self.bg_color,
            fg=self.fg_color,
            highlightthickness=0
        )
        self.sweep_base_volume_scale.pack(side=tk.LEFT, padx=5)
        
        # Valeur affichée
        self.sweep_base_volume_value = tk.Label(
            sweep_container,
            text=f"{self.sweep_base_volume_var.get():.2f}",
            font=("Arial", 10, "bold"),
            bg=self.bg_color,
            fg=self.success_color,
            width=8
        )
        self.sweep_base_volume_value.pack(side=tk.LEFT, padx=5)
        self.sweep_base_volume_scale.config(
            command=lambda v: self.sweep_base_volume_value.config(text=f"{float(v):.2f}")
        )
        
        # Exemple de progression
        sweep_example = tk.Label(
            sweep_frame,
            text=f"Exemple avec {self.sweep_base_volume_var.get():.2f} lots:\nPos 1: {self.sweep_base_volume_var.get():.2f} | Pos 2: {self.sweep_base_volume_var.get()*2:.2f} | Pos 3: {self.sweep_base_volume_var.get()*3:.2f} | Pos 4: {self.sweep_base_volume_var.get()*4:.2f}",
            font=("Arial", 9, "italic"),
            bg=self.bg_color,
            fg="#888888",
            justify=tk.LEFT
        )
        sweep_example.pack(anchor=tk.W, pady=(10, 0))
        
        # Mettre à jour l'exemple quand la valeur change
        def update_sweep_example(v):
            val = float(v)
            sweep_example.config(
                text=f"Exemple avec {val:.2f} lots:\nPos 1: {val:.2f} | Pos 2: {val*2:.2f} | Pos 3: {val*3:.2f} | Pos 4: {val*4:.2f}"
            )
        
        self.sweep_base_volume_scale.config(
            command=lambda v: [
                self.sweep_base_volume_value.config(text=f"{float(v):.2f}"),
                update_sweep_example(v)
            ]
        )
        
        # ===== BOUTON APPLIQUER =====
        apply_button = tk.Button(
            scrollable_frame,
            text="✅ Appliquer tous les paramètres",
            command=self.apply_parameters,
            font=("Arial", 12, "bold"),
            bg=self.success_color,
            fg=self.fg_color,
            width=30,
            height=2
        )
        apply_button.pack(pady=20)
        
        # Pack canvas et scrollbar
        canvas.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
    
    def _create_ml_tab(self) -> None:
        """Construit l'onglet dédié à l'entraînement ML."""

        container = tk.Frame(self.ml_frame, bg=self.bg_color)
        container.pack(fill=tk.BOTH, expand=True, padx=12, pady=12)

        # Paramètres généraux
        params_frame = tk.LabelFrame(
            container,
            text="⚙️ Paramètres d'entraînement",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=12,
            pady=10,
        )
        params_frame.grid(row=0, column=0, sticky="nsew", padx=6, pady=6)

        tk.Label(params_frame, text="Limite dataset", bg=self.bg_color, fg=self.fg_color, font=("Arial", 10)).grid(row=0, column=0, sticky=tk.W, pady=3)
        tk.Entry(params_frame, textvariable=self.ml_dataset_limit_var, width=12).grid(row=0, column=1, sticky=tk.W, padx=5, pady=3)

        tk.Label(params_frame, text="Test size", bg=self.bg_color, fg=self.fg_color, font=("Arial", 10)).grid(row=1, column=0, sticky=tk.W, pady=3)
        tk.Spinbox(params_frame, from_=0.05, to=0.5, increment=0.05, textvariable=self.ml_test_size_var, width=10, format="%.2f").grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)

        tk.Label(params_frame, text="Seed", bg=self.bg_color, fg=self.fg_color, font=("Arial", 10)).grid(row=2, column=0, sticky=tk.W, pady=3)
        tk.Spinbox(params_frame, from_=0, to=9999, textvariable=self.ml_random_state_var, width=10).grid(row=2, column=1, sticky=tk.W, padx=5, pady=3)

        tk.Label(params_frame, text="Device LSTM", bg=self.bg_color, fg=self.fg_color, font=("Arial", 10)).grid(row=3, column=0, sticky=tk.W, pady=3)
        tk.Entry(params_frame, textvariable=self.ml_sequence_device_var, width=16).grid(row=3, column=1, sticky=tk.W, padx=5, pady=3)

        tk.Label(params_frame, text="Répertoire modèles", bg=self.bg_color, fg=self.fg_color, font=("Arial", 10)).grid(row=4, column=0, sticky=tk.W, pady=3)
        output_entry = tk.Entry(params_frame, textvariable=self.ml_output_dir_var, width=30)
        output_entry.grid(row=4, column=1, sticky=tk.W, padx=5, pady=3)
        tk.Button(params_frame, text="📁", command=self._browse_ml_output_dir, width=3, bg=self.accent_color, fg=self.fg_color).grid(row=4, column=2, sticky=tk.W, padx=(4, 0))

        tk.Checkbutton(
            params_frame,
            text="Sauvegarder modèles",
            variable=self.ml_persist_var,
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.bg_color,
        ).grid(row=5, column=0, columnspan=2, sticky=tk.W, pady=(6, 0))

        # Modèles à entraîner
        models_frame = tk.LabelFrame(
            container,
            text="🧠 Modèles à entraîner",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=12,
            pady=10,
        )
        models_frame.grid(row=0, column=1, sticky="nsew", padx=6, pady=6)

        tk.Checkbutton(models_frame, text="RandomForest", variable=self.ml_train_rf_var, bg=self.bg_color, fg=self.fg_color, selectcolor=self.bg_color).pack(anchor=tk.W, pady=3)
        tk.Checkbutton(models_frame, text="LSTM Temporel", variable=self.ml_train_lstm_var, bg=self.bg_color, fg=self.fg_color, selectcolor=self.bg_color).pack(anchor=tk.W, pady=3)
        tk.Checkbutton(models_frame, text="Agent Q-Learning", variable=self.ml_train_rl_var, bg=self.bg_color, fg=self.fg_color, selectcolor=self.bg_color).pack(anchor=tk.W, pady=3)

        # Actions
        actions_frame = tk.Frame(container, bg=self.bg_color)
        actions_frame.grid(row=1, column=0, columnspan=2, sticky="ew", padx=6, pady=(10, 6))

        self.ml_run_button = tk.Button(
            actions_frame,
            text="🚀 Lancer l'entraînement",
            font=("Arial", 12, "bold"),
            command=lambda: self.launch_ml_training(triggered_auto=False),
            bg=self.success_color,
            fg=self.fg_color,
            width=24,
            height=2,
        )
        self.ml_run_button.pack(side=tk.LEFT, padx=5)

        tk.Button(
            actions_frame,
            text="📂 Ouvrir dossier",
            command=self._open_ml_output_dir,
            bg=self.accent_color,
            fg=self.fg_color,
            width=18,
        ).pack(side=tk.LEFT, padx=5)

        tk.Button(
            actions_frame,
            text="📝 Dernier rapport",
            command=self._open_last_ml_report,
            bg=self.accent_color,
            fg=self.fg_color,
            width=18,
        ).pack(side=tk.LEFT, padx=5)

        # Statut
        status_frame = tk.LabelFrame(
            container,
            text="📈 Statut & Résultats",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=12,
            pady=10,
        )
        status_frame.grid(row=2, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)

        tk.Label(status_frame, textvariable=self.ml_status_var, bg=self.bg_color, fg=self.accent_color, font=("Arial", 11, "bold")).pack(anchor=tk.W, pady=3)
        tk.Label(status_frame, textvariable=self.ml_last_report_var, bg=self.bg_color, fg=self.fg_color, font=("Arial", 10), wraplength=900, justify=tk.LEFT).pack(anchor=tk.W, pady=3)

        # Mode auto
        auto_frame = tk.LabelFrame(
            container,
            text="🤖 Mode Auto",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=12,
            pady=10,
        )
        auto_frame.grid(row=3, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)

        tk.Checkbutton(
            auto_frame,
            text="Activer entraînement automatique",
            variable=self.ml_auto_enabled_var,
            command=self.toggle_ml_auto,
            bg=self.bg_color,
            fg=self.fg_color,
            selectcolor=self.bg_color,
        ).grid(row=0, column=0, columnspan=2, sticky=tk.W)

        tk.Label(auto_frame, text="Intervalle (minutes)", bg=self.bg_color, fg=self.fg_color, font=("Arial", 10)).grid(row=1, column=0, sticky=tk.W, pady=3)
        tk.Spinbox(auto_frame, from_=30, to=1440, increment=30, textvariable=self.ml_auto_interval_var, width=8).grid(row=1, column=1, sticky=tk.W, padx=5, pady=3)

        tk.Label(auto_frame, textvariable=self.ml_auto_status_var, bg=self.bg_color, fg=self.accent_color, font=("Arial", 10, "bold")).grid(row=2, column=0, columnspan=2, sticky=tk.W, pady=3)
        tk.Label(auto_frame, textvariable=self.ml_auto_next_run_var, bg=self.bg_color, fg=self.fg_color, font=("Arial", 10)).grid(row=3, column=0, columnspan=2, sticky=tk.W, pady=3)

        # Historique
        history_frame = tk.LabelFrame(
            container,
            text="📚 Historique des rapports",
            font=("Arial", 12, "bold"),
            bg=self.bg_color,
            fg=self.fg_color,
            padx=12,
            pady=10,
        )
        history_frame.grid(row=4, column=0, columnspan=2, sticky="nsew", padx=6, pady=6)

        history_content = tk.Frame(history_frame, bg=self.bg_color)
        history_content.pack(fill=tk.BOTH, expand=True)

        self.ml_history_list = tk.Listbox(
            history_content,
            height=6,
            bg="#141414",
            fg=self.fg_color,
            selectbackground=self.accent_color,
            selectforeground=self.fg_color,
        )
        self.ml_history_list.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        self.ml_history_list.bind("<Double-Button-1>", lambda _: self._open_selected_ml_report())

        scrollbar = tk.Scrollbar(history_content, command=self.ml_history_list.yview)
        scrollbar.pack(side=tk.RIGHT, fill=tk.Y)
        self.ml_history_list.configure(yscrollcommand=scrollbar.set)

        history_buttons = tk.Frame(history_frame, bg=self.bg_color)
        history_buttons.pack(fill=tk.X, pady=(8, 0))

        tk.Button(history_buttons, text="🔄 Rafraîchir", command=self._refresh_ml_history, bg=self.accent_color, fg=self.fg_color).pack(side=tk.LEFT, padx=4)
        tk.Button(history_buttons, text="🗑️ Nettoyer", command=self._clear_ml_history, bg=self.danger_color, fg=self.fg_color).pack(side=tk.LEFT, padx=4)

        # Grille responsive
        container.grid_columnconfigure(0, weight=1)
        container.grid_columnconfigure(1, weight=1)
        container.grid_rowconfigure(4, weight=1)

        self._refresh_ml_history()
    
    def _create_logs_tab(self) -> None:
        """Crée l'onglet logs"""
        
        self.log_text = scrolledtext.ScrolledText(
            self.logs_frame,
            width=100,
            height=30,
            font=("Consolas", 9),
            bg="#2d2d2d",
            fg="#d4d4d4",
            insertbackground=self.fg_color
        )
        self.log_text.pack(fill=tk.BOTH, expand=True, padx=10, pady=10)
        
        # Bouton clear logs
        clear_button = tk.Button(
            self.logs_frame,
            text="🗑️ Effacer logs",
            command=self.clear_logs,
            font=("Arial", 10),
            bg=self.danger_color,
            fg=self.fg_color
        )
        clear_button.pack(pady=5)
    
    def _browse_ml_output_dir(self) -> None:
        """Ouvre un dialogue pour sélectionner le répertoire de sortie ML"""
        directory = filedialog.askdirectory(
            title="Sélectionner le répertoire de sortie des modèles ML",
            initialdir=self.ml_output_dir_var.get() or "."
        )
        if directory:
            self.ml_output_dir_var.set(directory)
            self.log_message(f"📁 Répertoire ML défini: {directory}")
    
    def _open_ml_output_dir(self) -> None:
        """Ouvre le dossier de sortie ML dans l'explorateur de fichiers"""
        output_dir = self.ml_output_dir_var.get() or "ml_models"
        path = Path(output_dir)
        
        if not path.exists():
            messagebox.showwarning("Dossier introuvable", f"Le dossier '{output_dir}' n'existe pas encore.")
            return
        
        try:
            if os.name == 'nt':  # Windows
                os.startfile(path)
            elif os.name == 'posix':  # macOS/Linux
                import subprocess
                if os.uname().sysname == 'Darwin':  # macOS
                    subprocess.run(['open', path])
                else:  # Linux
                    subprocess.run(['xdg-open', path])
            self.log_message(f"📂 Dossier ML ouvert: {output_dir}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir le dossier: {e}")
            logger.error(f"Erreur ouverture dossier ML: {e}")
    
    def _open_last_ml_report(self) -> None:
        """Ouvre le dernier rapport ML généré"""
        output_dir = Path(self.ml_output_dir_var.get() or "ml_models")
        
        if not output_dir.exists():
            messagebox.showwarning("Aucun rapport", "Aucun rapport ML n'a été généré.")
            return
        
        # Rechercher le dernier fichier de rapport (JSON ou texte)
        reports = list(output_dir.glob("training_report_*.json"))
        if not reports:
            reports = list(output_dir.glob("training_report_*.txt"))
        
        if not reports:
            messagebox.showwarning("Aucun rapport", "Aucun rapport ML trouvé dans le dossier.")
            return
        
        # Trier par date de modification (le plus récent en premier)
        latest_report = max(reports, key=lambda p: p.stat().st_mtime)
        
        try:
            if os.name == 'nt':  # Windows
                os.startfile(latest_report)
            else:
                import subprocess
                subprocess.run(['open' if os.uname().sysname == 'Darwin' else 'xdg-open', latest_report])
            self.log_message(f"📝 Rapport ouvert: {latest_report.name}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir le rapport: {e}")
            logger.error(f"Erreur ouverture rapport ML: {e}")
    
    def _open_selected_ml_report(self) -> None:
        """Ouvre le rapport sélectionné dans l'historique"""
        selection = self.ml_history_list.curselection()
        if not selection:
            return
        
        selected_text = self.ml_history_list.get(selection[0])
        # Extraire le nom du fichier du texte affiché
        # Format: "2025-10-22 10:00:00 - training_report_20251022_100000.json"
        parts = selected_text.split(" - ")
        if len(parts) < 2:
            return
        
        filename = parts[1].strip()
        output_dir = Path(self.ml_output_dir_var.get() or "ml_models")
        report_path = output_dir / filename
        
        if not report_path.exists():
            messagebox.showwarning("Fichier introuvable", f"Le rapport '{filename}' n'existe plus.")
            self._refresh_ml_history()  # Rafraîchir la liste
            return
        
        try:
            if os.name == 'nt':  # Windows
                os.startfile(report_path)
            else:
                import subprocess
                subprocess.run(['open' if os.uname().sysname == 'Darwin' else 'xdg-open', report_path])
            self.log_message(f"📝 Rapport ouvert: {filename}")
        except Exception as e:
            messagebox.showerror("Erreur", f"Impossible d'ouvrir le rapport: {e}")
            logger.error(f"Erreur ouverture rapport ML: {e}")
    
    def _refresh_ml_history(self) -> None:
        """Rafraîchit la liste des rapports ML dans l'historique"""
        self.ml_history_list.delete(0, tk.END)
        
        output_dir = Path(self.ml_output_dir_var.get() or "ml_models")
        if not output_dir.exists():
            return
        
        # Chercher tous les rapports
        reports = list(output_dir.glob("training_report_*.json"))
        reports.extend(output_dir.glob("training_report_*.txt"))
        
        if not reports:
            self.ml_history_list.insert(tk.END, "Aucun rapport disponible")
            return
        
        # Trier par date de modification (le plus récent en premier)
        reports.sort(key=lambda p: p.stat().st_mtime, reverse=True)
        
        # Ajouter à la liste (limiter aux 50 plus récents)
        for report in reports[:50]:
            mtime = datetime.fromtimestamp(report.stat().st_mtime)
            display_text = f"{mtime.strftime('%Y-%m-%d %H:%M:%S')} - {report.name}"
            self.ml_history_list.insert(tk.END, display_text)
    
    def _clear_ml_history(self) -> None:
        """Supprime les anciens rapports ML"""
        output_dir = Path(self.ml_output_dir_var.get() or "ml_models")
        if not output_dir.exists():
            messagebox.showinfo("Info", "Aucun dossier de rapports à nettoyer.")
            return
        
        # Confirmer la suppression
        confirm = messagebox.askyesno(
            "Confirmation",
            "Voulez-vous vraiment supprimer tous les anciens rapports ML?\n\n"
            "Cette action est irréversible."
        )
        
        if not confirm:
            return
        
        # Supprimer les rapports
        deleted_count = 0
        try:
            for report in output_dir.glob("training_report_*"):
                if report.is_file():
                    report.unlink()
                    deleted_count += 1
            
            self._refresh_ml_history()
            messagebox.showinfo("Nettoyage terminé", f"{deleted_count} rapport(s) supprimé(s).")
            self.log_message(f"🗑️ {deleted_count} rapport(s) ML supprimé(s)")
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du nettoyage: {e}")
            logger.error(f"Erreur nettoyage rapports ML: {e}")
    
    def toggle_ml_auto(self) -> None:
        """Active/désactive le mode d'entraînement automatique ML"""
        is_enabled = self.ml_auto_enabled_var.get()
        
        if is_enabled:
            self.ml_auto_status_var.set("🟢 Mode auto: ACTIVÉ")
            interval_minutes = self.ml_auto_interval_var.get()
            self.log_message(f"🤖 Entraînement ML automatique activé (intervalle: {interval_minutes} min)")
            
            # Calculer la prochaine exécution
            next_run = datetime.now() + timedelta(minutes=interval_minutes)
            self.ml_auto_next_run_var.set(f"Prochaine exécution: {next_run.strftime('%H:%M:%S')}")
            
            # TODO: Démarrer le timer d'entraînement automatique
            # self._schedule_ml_training()
        else:
            self.ml_auto_status_var.set("⚫ Mode auto: DÉSACTIVÉ")
            self.ml_auto_next_run_var.set("Prochaine exécution: --")
            self.log_message("🤖 Entraînement ML automatique désactivé")
            
            # TODO: Annuler le timer d'entraînement automatique
            # self._cancel_ml_training()
    
    def launch_ml_training(self, triggered_auto: bool = False) -> None:
        """Lance l'entraînement des modèles ML"""
        if not self.strategy:
            messagebox.showwarning("Bot non démarré", "Veuillez d'abord démarrer le bot pour entraîner les modèles ML.")
            return
        
        # Récupérer les paramètres de l'interface
        try:
            dataset_limit = int(self.ml_dataset_limit_var.get())
        except ValueError:
            dataset_limit = None
        
        test_size = self.ml_test_size_var.get()
        random_state = self.ml_random_state_var.get()
        device = self.ml_sequence_device_var.get()
        output_dir = self.ml_output_dir_var.get() or "ml_models"
        persist = self.ml_persist_var.get()
        
        # Modèles à entraîner
        train_rf = self.ml_train_rf_var.get()
        train_lstm = self.ml_train_lstm_var.get()
        train_qlearning = self.ml_train_qlearning_var.get()
        
        if not any([train_rf, train_lstm, train_qlearning]):
            messagebox.showwarning("Aucun modèle", "Veuillez sélectionner au moins un modèle à entraîner.")
            return
        
        # Créer la configuration ML
        ml_config = MLTrainerConfig(
            dataset_limit=dataset_limit,
            test_size=test_size,
            random_state=random_state,
            sequence_device=device,
            output_dir=output_dir,
            persist=persist,
            train_rf=train_rf,
            train_lstm=train_lstm,
            train_qlearning=train_qlearning
        )
        
        # Lancer l'entraînement dans un thread séparé
        def training_thread():
            try:
                self.ml_status_var.set("🔄 Entraînement en cours...")
                self.ml_run_button.config(state=tk.DISABLED)
                
                source = "automatique" if triggered_auto else "manuel"
                self.log_message(f"🚀 Lancement entraînement ML ({source})...")
                
                # Créer le trainer et lancer l'entraînement
                trainer = MLTrainer(ml_config)
                
                # TODO: Extraire les features depuis la stratégie
                # Pour l'instant, utiliser des données de test
                import numpy as np
                X_dummy = np.random.rand(100, 10)
                y_dummy = np.random.randint(0, 2, 100)
                
                results = trainer.train_all(X_dummy, y_dummy)
                
                # Afficher les résultats
                report_lines = ["✅ Entraînement terminé!"]
                for model_name, metrics in results.items():
                    if metrics:
                        report_lines.append(f"\n🧠 {model_name}:")
                        for metric, value in metrics.items():
                            report_lines.append(f"  • {metric}: {value:.4f}")
                
                report_text = "\n".join(report_lines)
                self.ml_last_report_var.set(report_text)
                self.ml_status_var.set("✅ Entraînement terminé")
                self.log_message("✅ Entraînement ML terminé avec succès")
                
                # Rafraîchir l'historique
                self._refresh_ml_history()
                
            except Exception as e:
                error_msg = f"❌ Erreur: {str(e)}"
                self.ml_status_var.set(error_msg)
                self.ml_last_report_var.set(error_msg)
                self.log_message(f"❌ Erreur entraînement ML: {e}")
                logger.error(f"Erreur entraînement ML: {e}", exc_info=True)
                messagebox.showerror("Erreur ML", f"Erreur lors de l'entraînement:\n{e}")
            finally:
                self.ml_run_button.config(state=tk.NORMAL)
        
        # Démarrer le thread d'entraînement
        threading.Thread(target=training_thread, daemon=True).start()
    
    def start_bot(self) -> None:
        """Démarre le bot"""
        if self.is_bot_running:
            return
        
        try:
            self.log_message("Démarrage du bot...")
            
            # Créer la stratégie avec référence à la GUI pour les paramètres
            self.strategy = HFTStrategy(self.config, gui=self)
            
            # Créer l'indicator worker
            self.indicator_worker = IndicatorWorker(self.strategy.indicators, self.config)
            self.indicator_worker.start()
            
            # Démarrer la stratégie
            if not self.strategy.start():
                messagebox.showerror("Erreur", "Échec du démarrage de la stratégie")
                return
            
            self.is_bot_running = True
            self.start_time = datetime.now()
            
            # Mettre à jour l'interface
            self.start_button.config(state=tk.DISABLED)
            self.stop_button.config(state=tk.NORMAL)
            self.status_label.config(text="● Status: En cours", fg=self.success_color)
            
            # Démarrer les mises à jour GUI (utilise after() au lieu de thread)
            self.update_stop_event.clear()
            self._schedule_update()
            
            self.log_message("✅ Bot démarré avec succès!")
            self.log_message(f"📊 Multiplicateurs actifs: SL={self.get_sl_multiplier():.2f}x, TP={self.get_tp_multiplier():.2f}x, Vol={self.get_volume_multiplier():.2f}x")
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors du démarrage: {e}")
            logger.error(f"Erreur démarrage bot: {e}", exc_info=True)
    
    def stop_bot(self) -> None:
        """Arrête le bot"""
        if not self.is_bot_running:
            return
        
        try:
            self.log_message("Arrêt du bot...")
            
            # Arrêter le thread de mise à jour
            self.update_stop_event.set()
            
            # Arrêter la stratégie
            if self.strategy:
                self.strategy.stop()
            
            # Arrêter l'indicator worker
            if self.indicator_worker:
                self.indicator_worker.stop()
            
            self.is_bot_running = False
            
            # Mettre à jour l'interface
            self.start_button.config(state=tk.NORMAL)
            self.stop_button.config(state=tk.DISABLED)
            self.status_label.config(text="● Status: Arrêté", fg=self.danger_color)
            
            self.log_message("✅ Bot arrêté")
            
        except Exception as e:
            messagebox.showerror("Erreur", f"Erreur lors de l'arrêt: {e}")
            logger.error(f"Erreur arrêt bot: {e}", exc_info=True)
    
    def _schedule_update(self) -> None:
        """Planifie la prochaine mise à jour GUI (appelée depuis le thread principal Tkinter)"""
        if self.update_stop_event.is_set():
            return
        
        try:
            self.update_dashboard()
            self.update_positions()
            self.update_indicators()  # NOUVEAU: Mise à jour des indicateurs en temps réel
        except Exception as e:
            logger.error(f"Erreur mise à jour GUI: {e}")
        
        # Replanifier la prochaine mise à jour (1000ms = 1 seconde)
        self.root.after(1000, self._schedule_update)
    
    def update_dashboard(self) -> None:
        """Met à jour le dashboard"""
        if not self.strategy:
            return
        
        # Compte
        account = get_account_summary()
        if account:
            self.balance_label.config(text=f"Balance: {account['balance']:.2f}")
            self.equity_label.config(text=f"Equity: {account['equity']:.2f}")
            self.margin_label.config(text=f"Marge Libre: {account['margin_free']:.2f}")
            
            profit = account['profit']
            profit_color = self.success_color if profit >= 0 else self.danger_color
            self.profit_label.config(text=f"Profit: {profit:.2f}", fg=profit_color)
        
        # Statistiques stratégie
        stats = self.strategy.get_statistics()
        self.signals_label.config(text=f"Signaux générés: {stats['signals_generated']}")
        self.orders_label.config(text=f"Ordres envoyés: {stats['orders_sent']}")
        self.rejected_label.config(text=f"Ordres rejetés: {stats['orders_rejected']}")
        
        # Uptime
        if self.start_time:
            uptime = (datetime.now() - self.start_time).total_seconds()
            self.uptime_label.config(text=f"Uptime: {format_duration(uptime)}")
        
        # Ticks
        self.ticks_label.config(text=f"Ticks reçus: {stats['ticks_received']}")
        if stats['last_tick_time']:
            self.last_tick_label.config(text=f"Dernier tick: {stats['last_tick_time'].strftime('%H:%M:%S')}")
        
        analysis_ms = stats['last_analysis_duration_ms']
        self.analysis_time_label.config(text=f"Temps analyse: {analysis_ms:.2f}ms")
        
        # Positions
        self.positions_count_label.config(text=f"Positions ouvertes: {stats['open_positions']}")
        self.total_trades_label.config(text=f"Trades totaux: {stats['total_trades']}")
        
        pos_summary = get_positions_summary(self.config.symbol)
        if pos_summary:
            pos_profit = pos_summary['total_profit']
            pos_profit_color = self.success_color if pos_profit >= 0 else self.danger_color
            self.positions_profit_label.config(text=f"Profit positions: {pos_profit:.2f}", fg=pos_profit_color)
        
        # 🌊 Sweep Status
        if hasattr(self.strategy, 'sweep_manager'):
            sweep_status = self.strategy.sweep_manager.get_status()
            
            if sweep_status['active']:
                self.sweep_status_label.config(
                    text=f"Sweep: 🌊 ACTIF ({sweep_status['direction']})",
                    fg=self.success_color
                )
                self.sweep_direction_label.config(text=f"Direction: {sweep_status['direction']}")
                self.sweep_progress_label.config(
                    text=f"Progression: {sweep_status['orders_placed']}/{sweep_status['levels_total']} ordres ({sweep_status['progress']:.1f}%)"
                )
                self.sweep_phase_label.config(text=f"Phase: {sweep_status['phase']}")
            else:
                self.sweep_status_label.config(text="Sweep: INACTIF", fg=self.fg_color)
                self.sweep_direction_label.config(text="Direction: --")
                self.sweep_progress_label.config(text="Progression: 0/0 ordres (0.0%)")
                self.sweep_phase_label.config(text="Phase: --")
    
    def update_positions(self) -> None:
        """Met à jour le tableau des positions"""
        if not self.strategy:
            return
        
        # Effacer l'ancien contenu
        for item in self.positions_tree.get_children():
            self.positions_tree.delete(item)
        
        # Ajouter les positions actuelles
        positions = self.strategy.position_manager.get_all_positions()
        for pos in positions:
            duration = (datetime.now() - pos.entry_time).total_seconds()
            duration_str = format_duration(duration)
            
            profit = pos.profit if pos.profit else 0.0
            
            self.positions_tree.insert('', tk.END, values=(
                pos.ticket,
                pos.order_type.name,
                pos.volume,
                f"{pos.entry_price:.2f}",
                f"{pos.stop_loss:.2f}",
                f"{pos.take_profit:.2f}",
                f"{profit:.2f}",
                duration_str
            ))
    
    def update_indicators(self) -> None:
        """Met à jour l'onglet Indicateurs en temps réel"""
        # Si le bot n'est pas démarré, afficher un message
        if not self.is_bot_running:
            self.tenkan_m1_label.config(text="Tenkan-sen: ⏸️ Bot arrêté")
            self.kijun_m1_label.config(text="Kijun-sen: ⏸️ Bot arrêté")
            self.signal_m1_label.config(text="Signal: ⏸️ Démarrez le bot", fg=self.warning_color)
            self.stc_m1_value_label.config(text="Valeur: ⏸️ Bot arrêté")
            self.stc_m1_zone_label.config(text="Zone: ⏸️ Démarrez le bot", fg=self.warning_color)
            self.last_update_label.config(text="Dernière mise à jour: --")
            self.computation_time_label.config(text="Temps de calcul: --")
            return
        
        if not self.indicator_worker or not self.strategy:
            return
        
        try:
            # Récupérer le tick_buffer depuis la stratégie
            tick_buffer = self.strategy.tick_feed.get_tick_buffer()
            if not tick_buffer:
                return
            
            # Demander le calcul des indicateurs avec les données actuelles
            m1_candles = tick_buffer.get_m1_candles()
            m5_candles = tick_buffer.get_m5_candles()
            
            if len(m1_candles) >= 60 and len(m5_candles) >= 60:
                self.indicator_worker.request_computation('compute_all', {
                    'm1_candles': m1_candles,
                    'm5_candles': m5_candles
                })
            
            # Récupérer les indicateurs en cache depuis le worker
            indicators = self.indicator_worker.get_cached_indicators()
            
            # Mettre à jour les infos de calcul
            last_update = indicators.get('last_update')
            computation_time = indicators.get('computation_time_ms', 0)
            
            if last_update:
                self.last_update_label.config(text=f"Dernière mise à jour: {last_update.strftime('%H:%M:%S')}")
            
            if computation_time > 0:
                self.computation_time_label.config(text=f"Temps de calcul: {computation_time:.2f}ms")
            
            # Ichimoku M1
            ichimoku_m1 = indicators.get('ichimoku_m1')
            if ichimoku_m1 and isinstance(ichimoku_m1, dict):
                tenkan = ichimoku_m1.get('tenkan_sen', 0)
                kijun = ichimoku_m1.get('kijun_sen', 0)
                signal = ichimoku_m1.get('signal', 'NEUTRAL')
                
                self.tenkan_m1_label.config(text=f"Tenkan-sen (ligne rapide): {tenkan:.2f}")
                self.kijun_m1_label.config(text=f"Kijun-sen (ligne lente): {kijun:.2f}")
                
                # Couleur selon signal
                if signal == 'LONG':
                    signal_color = self.success_color
                    signal_text = "Signal: 🟢 LONG (Achat) - Tenkan > Kijun"
                elif signal == 'SHORT':
                    signal_color = self.danger_color
                    signal_text = "Signal: 🔴 SHORT (Vente) - Tenkan < Kijun"
                else:
                    signal_color = self.warning_color
                    signal_text = "Signal: ⚪ NEUTRAL - Tenkan = Kijun"
                
                self.signal_m1_label.config(text=signal_text, fg=signal_color)
            else:
                self.tenkan_m1_label.config(text="Tenkan-sen: ⏳ Calcul en cours...")
                self.kijun_m1_label.config(text="Kijun-sen: ⏳ Calcul en cours...")
                self.signal_m1_label.config(text="Signal: ⏳ En attente de données (60+ bougies)", fg=self.warning_color)
            
            # STC M1
            stc_m1 = indicators.get('stc_m1')
            if stc_m1 and isinstance(stc_m1, dict):
                stc_value = stc_m1.get('value', 0)
                stc_signal = stc_m1.get('signal', 'NEUTRAL')
                
                self.stc_m1_value_label.config(text=f"Valeur STC: {stc_value:.2f} / 100")
                
                # Zone selon valeur avec émojis et couleurs
                if stc_value < self.config.stc_threshold_buy:
                    zone_text = f"Zone: 🟢 SURVENTE (<{self.config.stc_threshold_buy:.0f}) - Signal ACHAT"
                    zone_color = self.success_color
                elif stc_value > self.config.stc_threshold_sell:
                    zone_text = f"Zone: 🔴 SURACHAT (>{self.config.stc_threshold_sell:.0f}) - Signal VENTE"
                    zone_color = self.danger_color
                else:
                    zone_text = f"Zone: ⚪ NEUTRE ({self.config.stc_threshold_buy:.0f}-{self.config.stc_threshold_sell:.0f}) - Pas de signal"
                    zone_color = self.warning_color
                
                self.stc_m1_zone_label.config(text=zone_text, fg=zone_color)
            else:
                self.stc_m1_value_label.config(text="Valeur: ⏳ Calcul en cours...")
                self.stc_m1_zone_label.config(text="Zone: ⏳ En attente de données (60+ bougies)", fg=self.warning_color)
        
        except Exception as e:
            logger.error(f"Erreur mise à jour indicateurs: {e}", exc_info=True)
    
    def log_message(self, message: str) -> None:
        """Ajoute un message aux logs"""
        timestamp = datetime.now().strftime("%H:%M:%S")
        log_line = f"[{timestamp}] {message}\n"
        
        self.log_text.insert(tk.END, log_line)
        self.log_text.see(tk.END)  # Auto-scroll
    
    def clear_logs(self) -> None:
        """Efface les logs"""
        self.log_text.delete(1.0, tk.END)
    
    def update_kill_zone(self) -> None:
        """Met à jour l'activation de la Kill Zone en temps réel"""
        self.config.kill_zone_enabled = self.enable_kill_zone_var.get()
        status = "ACTIVÉE" if self.config.kill_zone_enabled else "DÉSACTIVÉE"
        color = self.success_color if self.config.kill_zone_enabled else self.danger_color
        self.log_message(f"✅ Kill Zone {status}")
        logger.info(f"Kill Zone {status}")
    
    def update_ignore_stc(self) -> None:
        """Met à jour l'option d'ignorer le STC en temps réel"""
        self.config.ignore_stc = self.ignore_stc_var.get()
        status = "IGNORÉ" if self.config.ignore_stc else "PRIS EN COMPTE"
        color = self.warning_color if self.config.ignore_stc else self.success_color
        self.log_message(f"⚙️ STC {status}")
        logger.info(f"STC {status}")
    
    def update_max_orders(self) -> None:
        """Met à jour le nombre maximum d'ordres simultanés en temps réel"""
        self.config.max_simultaneous_orders = self.max_orders_var.get()
        self.log_message(f"📊 Max ordres simultanés: {self.config.max_simultaneous_orders}")
        logger.info(f"Max ordres simultanés configuré à {self.config.max_simultaneous_orders}")
    
    def update_reactive_profit(self) -> None:
        """Met à jour l'activation du profit réactif en temps réel"""
        self.config.reactive_profit_enabled = self.reactive_profit_enabled_var.get()
        status = "ACTIVÉ" if self.config.reactive_profit_enabled else "DÉSACTIVÉ"
        color = self.success_color if self.config.reactive_profit_enabled else self.warning_color
        self.log_message(f"💰 Profit Réactif {status}")
        logger.info(f"Profit Réactif {status}")
    
    def apply_parameters(self) -> None:
        """Applique tous les paramètres ajustés à la stratégie"""
        try:
            # Mettre à jour la configuration
            self.config.spread_threshold = self.spread_max.get()
            self.config.ichimoku_tenkan_sen = self.tenkan_var.get()
            self.config.ichimoku_kijun_sen = self.kijun_var.get()
            self.config.ichimoku_senkou_span_b = self.senkou_var.get()
            self.config.stc_period = self.stc_period_var.get()
            self.config.stc_threshold_buy = self.stc_buy_var.get()
            self.config.stc_threshold_sell = self.stc_sell_var.get()
            self.config.strategy_timeframe = self.strategy_timeframe_var.get()
            
            # Mettre à jour les titres des frames d'indicateurs
            new_tf = self.strategy_timeframe_var.get()
            self.ichimoku_frame.config(text=f"📊 Ichimoku {new_tf}")
            self.stc_frame.config(text=f"📈 STC {new_tf} (Schaff Trend Cycle)")
            
            # Profit réactif (nouveau)
            self.config.reactive_profit_enabled = self.reactive_profit_enabled_var.get()
            self.config.profit_threshold_per_position = self.profit_threshold_per_position_var.get()
            self.config.profit_threshold_cumulative = self.profit_threshold_cumulative_var.get()
            
            # 🌊 Sweep - Mise de départ (nouveau)
            self.config.sweep_base_volume = self.sweep_base_volume_var.get()
            
            self.log_message("=" * 60)
            self.log_message("✅ PARAMÈTRES APPLIQUÉS:")
            self.log_message(f"   💰 Stop Loss: {self.sl_multiplier.get()}%")
            self.log_message(f"   💰 Take Profit: {self.tp_multiplier.get()}%")
            self.log_message(f"   📊 Volume: {self.volume_multiplier.get()}%")
            self.log_message(f"   📈 Spread Max: ${self.config.spread_threshold:.2f}")
            self.log_message(f"   📉 Ichimoku: T={self.config.ichimoku_tenkan_sen}, K={self.config.ichimoku_kijun_sen}, S={self.config.ichimoku_senkou_span_b}")
            self.log_message(f"   📊 STC: Période={self.config.stc_period}, Achat={self.config.stc_threshold_buy:.1f}, Vente={self.config.stc_threshold_sell:.1f}")
            self.log_message(f"   ⏱️ Timeframe: {self.config.strategy_timeframe}")
            self.log_message(f"   💰 Profit Réactif: {'ACTIVÉ' if self.config.reactive_profit_enabled else 'DÉSACTIVÉ'}")
            if self.config.reactive_profit_enabled:
                self.log_message(f"      → Seuil/Position: ${self.config.profit_threshold_per_position:.1f}")
                self.log_message(f"      → Seuil Cumulatif: ${self.config.profit_threshold_cumulative:.0f}")
            self.log_message(f"   🌊 Sweep - Mise de base: {self.config.sweep_base_volume:.2f} lots")
            self.log_message(f"      → Progression: 1×{self.config.sweep_base_volume:.2f} | 2×{self.config.sweep_base_volume*2:.2f} | 3×{self.config.sweep_base_volume*3:.2f} | 4×{self.config.sweep_base_volume*4:.2f}")
            self.log_message("=" * 60)
            
            logger.info("Paramètres de stratégie appliqués avec succès")
            
            messagebox.showinfo(
                "Succès",
                "Tous les paramètres ont été appliqués avec succès!\n\n"
                "Note: Les nouveaux paramètres Ichimoku et STC seront\n"
                "utilisés pour les prochaines analyses."
            )
            
        except Exception as e:
            error_msg = f"Erreur lors de l'application des paramètres: {e}"
            self.log_message(f"❌ {error_msg}")
            logger.error(error_msg, exc_info=True)
            messagebox.showerror("Erreur", error_msg)
    
    def get_sl_multiplier(self) -> float:
        """Retourne le multiplicateur SL (100 = 1.0x)"""
        return self.sl_multiplier.get() / 100.0
    
    def get_tp_multiplier(self) -> float:
        """Retourne le multiplicateur TP (100 = 1.0x)"""
        return self.tp_multiplier.get() / 100.0
    
    def get_volume_multiplier(self) -> float:
        """Retourne le multiplicateur de volume (100 = 1.0x)"""
        return self.volume_multiplier.get() / 100.0
    
    def on_closing(self) -> None:
        """Gestion de la fermeture de la fenêtre"""
        if self.is_bot_running:
            if messagebox.askokcancel("Quitter", "Le bot est en cours d'exécution. Voulez-vous vraiment quitter?"):
                self.stop_bot()
                
                # 🆕 Sauvegarder les paramètres avant de quitter
                try:
                    current_settings = extract_saveable_config(self.config)
                    self.settings_manager.save_settings(current_settings)
                    logger.info(f"💾 {len(current_settings)} paramètres sauvegardés")
                except Exception as e:
                    logger.error(f"Erreur sauvegarde paramètres: {e}")
                
                self.root.destroy()
        else:
            # 🆕 Sauvegarder même si le bot n'est pas en cours
            try:
                current_settings = extract_saveable_config(self.config)
                self.settings_manager.save_settings(current_settings)
                logger.info(f"💾 {len(current_settings)} paramètres sauvegardés")
            except Exception as e:
                logger.error(f"Erreur sauvegarde paramètres: {e}")
            
            self.root.destroy()
    
    def run(self) -> None:
        """Lance la boucle principale de l'interface"""
        self.root.mainloop()
