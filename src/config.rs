use serde::{Deserialize, Serialize};
use std::path::{Path, PathBuf};

use crate::pace::{clamp_strokes, STROKES_DEFAULT};

#[derive(Debug, Clone, Serialize, Deserialize)]
pub struct Config {
    pub base_url: String,
    pub url_preset: String,
    pub browser: String,
    pub remember_login: bool,
    pub always_on_top: bool,
    pub strokes_per_10min: i32,
    pub jitter_pct: f64,
}

impl Default for Config {
    fn default() -> Self {
        Self {
            base_url: "https://at4.typewriter.at".into(),
            url_preset: "Österreich (at4)".into(),
            browser: "Auto".into(),
            remember_login: true,
            always_on_top: true,
            strokes_per_10min: STROKES_DEFAULT,
            jitter_pct: 0.0,
        }
    }
}

pub const PRESET_URLS: &[(&str, &str)] = &[
    ("Österreich (at4)", "https://at4.typewriter.at"),
    ("Deutschland (de4)", "https://de4.typewriter.at"),
    ("Schweiz (ch4)", "https://ch4.typewriter.at"),
    ("Benutzerdefiniert", ""),
];

pub fn preset_url(name: &str) -> Option<&'static str> {
    PRESET_URLS.iter().find(|(n, _)| *n == name).map(|(_, u)| *u)
}

pub fn app_dir() -> PathBuf {
    std::env::current_exe()
        .ok()
        .and_then(|p| p.parent().map(|d| d.to_path_buf()))
        .unwrap_or_else(|| std::env::current_dir().unwrap_or_else(|_| PathBuf::from(".")))
}

pub fn config_path() -> PathBuf {
    app_dir().join("config.json")
}

pub fn credentials_path() -> PathBuf {
    app_dir().join("credentials.json")
}

pub fn merge_config(raw: Option<&serde_json::Value>) -> Config {
    let mut cfg = Config::default();
    let Some(serde_json::Value::Object(map)) = raw else {
        return cfg;
    };
    if let Some(v) = map.get("base_url").and_then(|v| v.as_str()) {
        cfg.base_url = v.to_string();
    }
    if let Some(v) = map.get("url_preset").and_then(|v| v.as_str()) {
        cfg.url_preset = v.to_string();
    }
    if let Some(v) = map.get("browser").and_then(|v| v.as_str()) {
        cfg.browser = v.to_string();
    }
    if let Some(v) = map.get("remember_login").and_then(|v| v.as_bool()) {
        cfg.remember_login = v;
    }
    if let Some(v) = map.get("always_on_top").and_then(|v| v.as_bool()) {
        cfg.always_on_top = v;
    }
    if let Some(v) = map.get("strokes_per_10min") {
        let n = v.as_f64().or_else(|| v.as_i64().map(|i| i as f64)).unwrap_or(STROKES_DEFAULT as f64);
        cfg.strokes_per_10min = clamp_strokes(n);
    }
    if let Some(v) = map.get("jitter_pct").and_then(|v| v.as_f64()) {
        cfg.jitter_pct = v;
    }
    cfg
}

pub fn load_config(path: &Path) -> Config {
    match std::fs::read_to_string(path) {
        Ok(text) => merge_config(serde_json::from_str(&text).ok().as_ref()),
        Err(_) => Config::default(),
    }
}

pub fn save_config(cfg: &Config, path: &Path) -> std::io::Result<()> {
    let mut out = cfg.clone();
    out.strokes_per_10min = clamp_strokes(out.strokes_per_10min);
    std::fs::write(path, serde_json::to_string_pretty(&out).unwrap_or_else(|_| "{}".into()))
}

pub fn load_credentials(path: &Path) -> (Option<String>, Option<String>) {
    let Ok(text) = std::fs::read_to_string(path) else {
        return (None, None);
    };
    let Ok(v) = serde_json::from_str::<serde_json::Value>(&text) else {
        return (None, None);
    };
    let email = v
        .get("email")
        .and_then(|x| x.as_str())
        .map(str::trim)
        .filter(|s| !s.is_empty())
        .map(ToOwned::to_owned);
    let password = v
        .get("password")
        .and_then(|x| x.as_str())
        .filter(|s| !s.is_empty())
        .map(ToOwned::to_owned);
    (email, password)
}

pub fn save_credentials(email: &str, password: &str, path: &Path) -> std::io::Result<()> {
    let v = serde_json::json!({ "email": email, "password": password });
    std::fs::write(path, serde_json::to_string_pretty(&v).unwrap())
}
