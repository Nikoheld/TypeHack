//! Anschläge / 10 Minuten → delay between keystrokes (same clamp as TypeHack 2.x).

pub const STROKES_MIN: i32 = 200;
pub const STROKES_MAX: i32 = 8000;
pub const STROKES_DEFAULT: i32 = 2000;
const WINDOW_SECONDS: f64 = 600.0;

pub fn clamp_strokes(n: impl Into<f64>) -> i32 {
    let value = n.into();
    if !value.is_finite() {
        return STROKES_DEFAULT;
    }
    (value as i32).clamp(STROKES_MIN, STROKES_MAX)
}

/// Seconds between keystrokes from Anschläge / 10 minutes. 2000 → 0.3s.
pub fn interval_seconds(strokes_per_10min: impl Into<f64>) -> f64 {
    let n = clamp_strokes(strokes_per_10min);
    (WINDOW_SECONDS / f64::from(n)).max(0.02)
}

pub fn interval_seconds_cfg(strokes_per_10min: i32, jitter_pct: f64) -> f64 {
    let base = interval_seconds(strokes_per_10min);
    let jitter = jitter_pct.clamp(0.0, 100.0) / 100.0;
    if jitter <= 0.0 {
        return base;
    }
    let factor = 1.0 + (hash_jitter() * 2.0 - 1.0) * jitter;
    (base * factor).max(0.02)
}

fn hash_jitter() -> f64 {
    use std::time::{SystemTime, UNIX_EPOCH};
    let t = SystemTime::now()
        .duration_since(UNIX_EPOCH)
        .map(|d| d.subsec_nanos())
        .unwrap_or(1);
    (t as f64) / 1_000_000_000.0
}
