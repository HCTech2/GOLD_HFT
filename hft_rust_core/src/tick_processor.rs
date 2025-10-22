//! Buffer circulaire haute performance pour ticks
//! Utilise parking_lot pour thread-safety optimale

use pyo3::prelude::*;
use parking_lot::RwLock;
use std::sync::Arc;
use chrono::{DateTime, Utc};

/// Tick de marché
#[pyclass]
#[derive(Clone, Debug)]
pub struct Tick {
    #[pyo3(get)]
    pub symbol: String,
    #[pyo3(get)]
    pub bid: f64,
    #[pyo3(get)]
    pub ask: f64,
    #[pyo3(get)]
    pub timestamp: i64, // Unix timestamp en microsecondes
    #[pyo3(get)]
    pub volume: i64,
}

#[pymethods]
impl Tick {
    #[new]
    fn new(symbol: String, bid: f64, ask: f64, timestamp: i64, volume: i64) -> Self {
        Tick { symbol, bid, ask, timestamp, volume }
    }
    
    #[getter]
    fn mid_price(&self) -> f64 {
        (self.bid + self.ask) / 2.0
    }
    
    #[getter]
    fn spread(&self) -> f64 {
        self.ask - self.bid
    }
}

/// OHLC Bar
#[pyclass]
#[derive(Clone, Debug)]
pub struct OHLC {
    #[pyo3(get)]
    pub timestamp: i64,
    #[pyo3(get)]
    pub open: f64,
    #[pyo3(get)]
    pub high: f64,
    #[pyo3(get)]
    pub low: f64,
    #[pyo3(get)]
    pub close: f64,
    #[pyo3(get)]
    pub volume: i64,
}

/// Buffer circulaire thread-safe pour ticks
#[pyclass]
pub struct TickBuffer {
    ticks: Arc<RwLock<Vec<Tick>>>,
    m1_candles: Arc<RwLock<Vec<OHLC>>>,
    m5_candles: Arc<RwLock<Vec<OHLC>>>,
    capacity: usize,
    symbol: String,
}

#[pymethods]
impl TickBuffer {
    #[new]
    fn new(capacity: usize, symbol: String) -> Self {
        TickBuffer {
            ticks: Arc::new(RwLock::new(Vec::with_capacity(capacity))),
            m1_candles: Arc::new(RwLock::new(Vec::with_capacity(60))),
            m5_candles: Arc::new(RwLock::new(Vec::with_capacity(60))),
            capacity,
            symbol,
        }
    }
    
    /// Ajoute un tick au buffer (thread-safe)
    fn add_tick(&self, tick: Tick) {
        let mut ticks = self.ticks.write();
        
        // Buffer circulaire : supprimer le plus ancien si plein
        if ticks.len() >= self.capacity {
            ticks.remove(0);
        }
        
        ticks.push(tick);
    }
    
    /// Récupère les N derniers ticks
    fn get_recent_ticks(&self, n: usize) -> Vec<Tick> {
        let ticks = self.ticks.read();
        let start = if ticks.len() > n { ticks.len() - n } else { 0 };
        ticks[start..].to_vec()
    }
    
    /// Construit une bougie OHLC à partir des ticks
    fn build_ohlc_from_ticks(&self, ticks: Vec<Tick>) -> Option<OHLC> {
        if ticks.is_empty() {
            return None;
        }
        
        let mut high = f64::MIN;
        let mut low = f64::MAX;
        let mut total_volume = 0i64;
        
        for tick in &ticks {
            let mid = tick.mid_price();
            if mid > high { high = mid; }
            if mid < low { low = mid; }
            total_volume += tick.volume;
        }
        
        Some(OHLC {
            timestamp: ticks[0].timestamp,
            open: ticks[0].mid_price(),
            high,
            low,
            close: ticks[ticks.len() - 1].mid_price(),
            volume: total_volume,
        })
    }
    
    /// Récupère les bougies M1
    fn get_m1_candles(&self, n: usize) -> Vec<OHLC> {
        let candles = self.m1_candles.read();
        let start = if candles.len() > n { candles.len() - n } else { 0 };
        candles[start..].to_vec()
    }
    
    /// Récupère les bougies M5
    fn get_m5_candles(&self, n: usize) -> Vec<OHLC> {
        let candles = self.m5_candles.read();
        let start = if candles.len() > n { candles.len() - n } else { 0 };
        candles[start..].to_vec()
    }
    
    /// Nombre de ticks dans le buffer
    fn tick_count(&self) -> usize {
        self.ticks.read().len()
    }
}
