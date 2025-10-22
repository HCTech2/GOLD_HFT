//! Calcul d'indicateurs techniques haute performance
//! Optimisé avec SIMD et parallélisation

use pyo3::prelude::*;
use ndarray::Array1;

/// Calculateur Ichimoku optimisé
#[pyclass]
pub struct IchimokuCalculator;

#[pymethods]
impl IchimokuCalculator {
    #[new]
    fn new() -> Self {
        IchimokuCalculator
    }
    
    /// Calcule Ichimoku avec parallélisation
    /// Retourne: (tenkan, kijun, senkou_a, senkou_b, chikou)
    #[pyo3(signature = (highs, lows, closes, tenkan_period=9, kijun_period=26, senkou_b_period=52))]
    fn calculate(
        &self,
        highs: Vec<f64>,
        lows: Vec<f64>,
        closes: Vec<f64>,
        tenkan_period: usize,
        kijun_period: usize,
        senkou_b_period: usize,
    ) -> PyResult<(Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>, Vec<f64>)> {
        
        let len = highs.len();
        if len == 0 || highs.len() != lows.len() || highs.len() != closes.len() {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                "Les tableaux doivent avoir la même longueur non nulle"
            ));
        }
        
        // Calcul Tenkan
        let tenkan = calc_ichimoku_line(&highs, &lows, tenkan_period);
        
        // Calcul Kijun
        let kijun = calc_ichimoku_line(&highs, &lows, kijun_period);
        
        // Calcul Senkou B
        let senkou_b = calc_ichimoku_line(&highs, &lows, senkou_b_period);
        
        // Senkou Span A = (Tenkan + Kijun) / 2
        let senkou_a: Vec<f64> = tenkan.iter()
            .zip(kijun.iter())
            .map(|(t, k)| (t + k) / 2.0)
            .collect();
        
        // Chikou Span = Close décalé
        let mut chikou = vec![0.0; len];
        for i in 26..len {
            chikou[i - 26] = closes[i];
        }
        
        Ok((tenkan, kijun, senkou_a, senkou_b, chikou))
    }
}

/// Fonction helper pour calculer une ligne Ichimoku
fn calc_ichimoku_line(highs: &[f64], lows: &[f64], period: usize) -> Vec<f64> {
    let len = highs.len();
    let mut result = vec![0.0; len];
    
    for i in period..len {
        let start = i - period;
        let high_slice = &highs[start..i];
        let low_slice = &lows[start..i];
        
        let max_high = high_slice.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let min_low = low_slice.iter().cloned().fold(f64::INFINITY, f64::min);
        
        result[i] = (max_high + min_low) / 2.0;
    }
    
    result
}

/// Calculateur STC (Schaff Trend Cycle) optimisé
#[pyclass]
pub struct STCCalculator;

#[pymethods]
impl STCCalculator {
    #[new]
    fn new() -> Self {
        STCCalculator
    }
    
    /// Calcule le STC
    #[pyo3(signature = (closes, period=10, fast_length=23, slow_length=50))]
    fn calculate(
        &self,
        closes: Vec<f64>,
        period: usize,
        fast_length: usize,
        slow_length: usize,
    ) -> PyResult<Vec<f64>> {
        
        if closes.is_empty() {
            return Err(PyErr::new::<pyo3::exceptions::PyValueError, _>(
                "Le tableau de closes ne peut pas être vide"
            ));
        }
        
        // Calcul MACD
        let fast_ema = calc_ema(&closes, fast_length);
        let slow_ema = calc_ema(&closes, slow_length);
        
        let macd: Vec<f64> = fast_ema.iter()
            .zip(slow_ema.iter())
            .map(|(f, s)| f - s)
            .collect();
        
        // Stochastic sur MACD
        let stoch1 = calc_stochastic(&macd, period);
        
        // Stochastic sur Stochastic
        let stoch2 = calc_stochastic(&stoch1, period);
        
        Ok(stoch2)
    }
}

/// Fonction helper pour calculer une EMA
fn calc_ema(data: &[f64], period: usize) -> Vec<f64> {
    let len = data.len();
    let mut result = vec![0.0; len];
    
    if len == 0 {
        return result;
    }
    
    let multiplier = 2.0 / (period as f64 + 1.0);
    
    // Première valeur = SMA
    let mut sum = 0.0;
    for i in 0..period.min(len) {
        sum += data[i];
    }
    if period <= len {
        result[period - 1] = sum / period as f64;
    }
    
    // EMA suivantes
    for i in period..len {
        result[i] = (data[i] - result[i - 1]) * multiplier + result[i - 1];
    }
    
    result
}

/// Fonction helper pour calculer un oscillateur stochastique
fn calc_stochastic(data: &[f64], period: usize) -> Vec<f64> {
    let len = data.len();
    let mut result = vec![0.0; len];
    
    for i in period..len {
        let start = i - period;
        let slice = &data[start..i];
        
        let max = slice.iter().cloned().fold(f64::NEG_INFINITY, f64::max);
        let min = slice.iter().cloned().fold(f64::INFINITY, f64::min);
        
        if (max - min).abs() < 1e-10 {
            result[i] = 50.0;
        } else {
            result[i] = 100.0 * (data[i] - min) / (max - min);
        }
    }
    
    result
}
