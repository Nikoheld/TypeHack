//! Single source of truth for the shipped TypeHack version.

pub const VERSION: &str = "3.1.0";
pub const APP_NAME: &str = "TypeHack";
pub const WINDOW_TITLE: &str = "TypeHack 3.1.0";
pub const REPO: &str = "Nikoheld/TypeHack";

/// `v3.1.0` / `3.1.0-beta` → `[3, 1, 0]`.
pub fn parse_version(tag: &str) -> Vec<u32> {
    let raw = tag.trim().trim_start_matches(['v', 'V']);
    let mut parts = Vec::new();
    for bit in raw.split(|c: char| matches!(c, '.' | '+' | '-')) {
        if bit.is_empty() {
            continue;
        }
        if bit.chars().all(|c| c.is_ascii_digit()) {
            if let Ok(n) = bit.parse::<u32>() {
                parts.push(n);
            }
        } else {
            break;
        }
    }
    if parts.is_empty() {
        parts.push(0);
    }
    parts
}

pub fn is_newer(remote: &str, local: &str) -> bool {
    let mut a = parse_version(remote);
    let mut b = parse_version(local);
    let n = a.len().max(b.len());
    a.resize(n, 0);
    b.resize(n, 0);
    a > b
}
