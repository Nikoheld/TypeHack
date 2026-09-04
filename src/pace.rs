//! Anschläge / 10 Minuten → wall-clock keystroke schedule (2000 → exactly 0.3s).

use std::time::Duration;

pub const STROKES_MIN: i32 = 200;
pub const STROKES_MAX: i32 = 8000;
pub const STROKES_DEFAULT: i32 = 2000;
/// MAX Speed must beat this (100000 Anschläge / 10 min ≈ 6 ms/Taste).
pub const MAX_SPEED_MIN_STROKES: i32 = 100_000;
const WINDOW_SECONDS: f64 = 600.0;

pub fn clamp_strokes(n: impl Into<f64>) -> i32 {
    let value = n.into();
    if !value.is_finite() {
        return STROKES_DEFAULT;
    }
    (value as i32).clamp(STROKES_MIN, STROKES_MAX)
}

/// Seconds between keystrokes from Anschläge / 10 minutes. 2000 → 0.3s exactly.
pub fn interval_seconds(strokes_per_10min: impl Into<f64>) -> f64 {
    let n = clamp_strokes(strokes_per_10min);
    WINDOW_SECONDS / f64::from(n)
}

/// Zero when MAX Speed is on so keys fire as fast as the lesson accepts them.
pub fn interval_duration(strokes_per_10min: i32, max_speed: bool) -> Duration {
    if max_speed {
        Duration::ZERO
    } else {
        Duration::from_secs_f64(interval_seconds(strokes_per_10min))
    }
}

/// When the Nth key (0-based) is due relative to session start.
/// Key 0 at t=0, key 1 at 1×interval, … so 2000 keys land in 599.7s ≈ 2000/10min.
pub fn due_after(sent: u64, interval: Duration) -> Duration {
    interval.saturating_mul(sent as u32)
}

pub fn expected_strokes_per_10min(interval: Duration) -> f64 {
    if interval.is_zero() {
        return f64::INFINITY;
    }
    WINDOW_SECONDS / interval.as_secs_f64()
}

#[derive(Debug, Clone, Copy, PartialEq, Eq)]
pub enum TypingMode {
    Paced { strokes: i32 },
    MaxSpeed,
}

impl TypingMode {
    pub fn from_ui(strokes: i32, max_speed: bool) -> Self {
        if max_speed {
            TypingMode::MaxSpeed
        } else {
            TypingMode::Paced {
                strokes: clamp_strokes(strokes),
            }
        }
    }

    pub fn is_max(self) -> bool {
        matches!(self, TypingMode::MaxSpeed)
    }

    pub fn interval(self) -> Duration {
        match self {
            TypingMode::MaxSpeed => Duration::ZERO,
            TypingMode::Paced { strokes } => interval_duration(strokes, false),
        }
    }
}

/// Editing Anschläge always leaves MAX Speed. 2000 → paced 0.3s, never a burst.
pub fn after_strokes_edited(strokes: i32) -> (i32, bool) {
    (clamp_strokes(strokes), false)
}
