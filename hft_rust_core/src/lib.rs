//! HFT Trading Core - Rust Backend
//! Composants haute performance pour trading HFT

use pyo3::prelude::*;

mod tick_processor;
mod indicators;
mod signal_detector;

pub use tick_processor::TickBuffer;
pub use indicators::{IchimokuCalculator, STCCalculator};
pub use signal_detector::SignalDetector;

/// Module Python exposé
#[pymodule]
fn hft_rust_core(_py: Python, m: &PyModule) -> PyResult<()> {
    m.add_class::<TickBuffer>()?;
    m.add_class::<IchimokuCalculator>()?;
    m.add_class::<STCCalculator>()?;
    m.add_class::<SignalDetector>()?;
    Ok(())
}
