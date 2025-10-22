//! Détecteur de signaux HFT
//! Analyse rapide des conditions de marché

use pyo3::prelude::*;

#[pyclass]
#[derive(Clone, Debug)]
pub enum SignalType {
    Long,
    Short,
    Neutral,
}

#[pyclass]
pub struct SignalDetector {
    min_confidence: f64,
}

#[pymethods]
impl SignalDetector {
    #[new]
    fn new(min_confidence: f64) -> Self {
        SignalDetector { min_confidence }
    }
    
    /// Détecte un signal Ichimoku
    fn detect_ichimoku_signal(
        &self,
        price: f64,
        tenkan: f64,
        kijun: f64,
        senkou_a: f64,
        senkou_b: f64,
    ) -> (String, f64) {
        
        let cloud_top = senkou_a.max(senkou_b);
        let cloud_bottom = senkou_a.min(senkou_b);
        
        let mut score = 0.0;
        let mut signal = "NEUTRAL".to_string();
        
        // Prix au-dessus du nuage
        if price > cloud_top {
            score += 30.0;
            
            // TK Cross haussier
            if tenkan > kijun {
                score += 40.0;
                
                // Confirmation forte
                if tenkan > cloud_top && kijun > cloud_top {
                    score += 30.0;
                    signal = "LONG".to_string();
                }
            }
        }
        // Prix en-dessous du nuage
        else if price < cloud_bottom {
            score += 30.0;
            
            // TK Cross baissier
            if tenkan < kijun {
                score += 40.0;
                
                // Confirmation forte
                if tenkan < cloud_bottom && kijun < cloud_bottom {
                    score += 30.0;
                    signal = "SHORT".to_string();
                }
            }
        }
        
        (signal, score)
    }
    
    /// Détecte un signal STC
    fn detect_stc_signal(&self, stc: f64, prev_stc: f64) -> (String, f64) {
        let mut signal = "NEUTRAL".to_string();
        let mut confidence = 0.0;
        
        // Survente → Achat
        if prev_stc < 25.0 && stc > 25.0 {
            signal = "LONG".to_string();
            confidence = 70.0;
        }
        // Surachat → Vente
        else if prev_stc > 75.0 && stc < 75.0 {
            signal = "SHORT".to_string();
            confidence = 70.0;
        }
        
        (signal, confidence)
    }
    
    /// Combine plusieurs signaux
    fn combine_signals(
        &self,
        ichimoku_signal: String,
        ichimoku_conf: f64,
        stc_signal: String,
        stc_conf: f64,
    ) -> (String, f64) {
        
        // Accord parfait
        if ichimoku_signal == stc_signal && ichimoku_signal != "NEUTRAL" {
            let combined_conf = (ichimoku_conf + stc_conf) / 2.0;
            return (ichimoku_signal, combined_conf);
        }
        
        // Désaccord ou neutralité
        ("NEUTRAL".to_string(), 0.0)
    }
}
