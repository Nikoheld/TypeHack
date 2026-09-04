//! TypeHack 3.0.0 desktop UI — native Rust, not the 2.x Tk window.

#![cfg_attr(not(debug_assertions), windows_subsystem = "windows")]

use std::sync::atomic::{AtomicBool, Ordering};
use std::sync::{Arc, Mutex};
use std::thread;
use std::time::Duration;

use eframe::egui::{self, Color32, CornerRadius, FontId, Frame, Margin, RichText, Stroke, Ui, Vec2};
use typehack::config::{self, Config, PRESET_URLS};
use typehack::pace::{clamp_strokes, due_after, interval_duration, interval_seconds, STROKES_MAX, STROKES_MIN};
use typehack::ui_labels;
use typehack::{VERSION, WINDOW_TITLE};

mod browser;

#[derive(Clone)]
struct Live {
    status: String,
    remaining: String,
    connected: bool,
    typing: bool,
    badge: String,
}

impl Default for Live {
    fn default() -> Self {
        Self {
            status: "Bereit.".into(),
            remaining: "Verbinden → Level wählen → Start Typing.".into(),
            connected: false,
            typing: false,
            badge: "getrennt".into(),
        }
    }
}

struct App {
    email: String,
    password: String,
    preset: String,
    custom_url: String,
    strokes: i32,
    max_speed: bool,
    always_on_top: bool,
    live: Arc<Mutex<Live>>,
    stop: Arc<AtomicBool>,
    connecting: bool,
}

impl App {
    fn new(cc: &eframe::CreationContext<'_>) -> Self {
        apply_theme(&cc.egui_ctx);
        let cfg = config::load_config(&config::config_path());
        let (email, password) = config::load_credentials(&config::credentials_path());
        if cfg.always_on_top {
            cc.egui_ctx
                .send_viewport_cmd(egui::ViewportCommand::WindowLevel(egui::WindowLevel::AlwaysOnTop));
        }
        let custom_url = if cfg.url_preset == "Benutzerdefiniert" {
            cfg.base_url.clone()
        } else {
            String::new()
        };
        Self {
            email: email.unwrap_or_default(),
            password: password.unwrap_or_default(),
            preset: cfg.url_preset,
            custom_url,
            strokes: clamp_strokes(cfg.strokes_per_10min),
            max_speed: cfg.max_speed,
            always_on_top: cfg.always_on_top,
            live: Arc::new(Mutex::new(Live::default())),
            stop: Arc::new(AtomicBool::new(false)),
            connecting: false,
        }
    }

    fn base_url(&self) -> String {
        if self.preset == "Benutzerdefiniert" {
            let u = self.custom_url.trim();
            if u.is_empty() {
                "https://at4.typewriter.at".into()
            } else {
                u.trim_end_matches('/').into()
            }
        } else {
            config::preset_url(&self.preset)
                .filter(|s| !s.is_empty())
                .unwrap_or("https://at4.typewriter.at")
                .into()
        }
    }

    fn persist(&self) {
        let cfg = Config {
            base_url: self.base_url(),
            url_preset: self.preset.clone(),
            browser: "Auto".into(),
            remember_login: true,
            always_on_top: self.always_on_top,
            strokes_per_10min: clamp_strokes(self.strokes),
            jitter_pct: 0.0,
            max_speed: self.max_speed,
        };
        let _ = config::save_config(&cfg, &config::config_path());
        if !self.email.trim().is_empty() && !self.password.is_empty() {
            let _ = config::save_credentials(self.email.trim(), &self.password, &config::credentials_path());
        }
    }

    fn set_live(&self, f: impl FnOnce(&mut Live)) {
        if let Ok(mut g) = self.live.lock() {
            f(&mut g);
        }
    }
}

impl eframe::App for App {
    fn update(&mut self, ctx: &egui::Context, _frame: &mut eframe::Frame) {
        ctx.request_repaint_after(Duration::from_millis(80));
        let live = self.live.lock().map(|g| g.clone()).unwrap_or_default();
        if live.connected || live.status.contains("fehl") || live.status.starts_with("Browser:") {
            self.connecting = false;
        }

        egui::CentralPanel::default()
            .frame(Frame::new().fill(COL_BG).inner_margin(Margin::same(0)))
            .show(ctx, |ui| {
                header(ui, &live);
                egui::ScrollArea::vertical().show(ui, |ui| {
                    ui.add_space(8.0);
                    ui.allocate_ui_with_layout(
                        Vec2::new(ui.available_width(), ui.available_height()),
                        egui::Layout::top_down(egui::Align::Center),
                        |ui| {
                            ui.set_max_width(420.0);
                            card(ui, |ui| {
                                field(ui, ui_labels::EMAIL, &mut self.email, false);
                                field(ui, ui_labels::PASSWORD, &mut self.password, true);
                                ui.add_space(6.0);
                                ui.label(RichText::new(ui_labels::SERVER).color(COL_MUTED).size(12.0));
                                let presets: Vec<&str> = PRESET_URLS.iter().map(|(n, _)| *n).collect();
                                egui::ComboBox::from_id_salt("server")
                                    .selected_text(&self.preset)
                                    .width(ui.available_width())
                                    .show_ui(ui, |ui| {
                                        for p in presets {
                                            ui.selectable_value(&mut self.preset, p.to_string(), p);
                                        }
                                    });
                                if self.preset == "Benutzerdefiniert" {
                                    ui.add_space(4.0);
                                    ui.add(
                                        egui::TextEdit::singleline(&mut self.custom_url)
                                            .desired_width(f32::INFINITY)
                                            .hint_text("https://…"),
                                    );
                                }
                                ui.add_space(12.0);
                                ui.label(RichText::new(ui_labels::RATE).color(COL_MUTED).size(12.0));
                                ui.horizontal(|ui| {
                                    ui.add_enabled(
                                        !self.max_speed,
                                        egui::DragValue::new(&mut self.strokes)
                                            .range(STROKES_MIN..=STROKES_MAX)
                                            .speed(10),
                                    );
                                    ui.add_enabled(
                                        !self.max_speed,
                                        egui::Slider::new(&mut self.strokes, STROKES_MIN..=STROKES_MAX)
                                            .show_value(false),
                                    );
                                });
                                let n = clamp_strokes(self.strokes);
                                if ui.checkbox(&mut self.max_speed, ui_labels::MAX_SPEED).changed() {
                                    self.persist();
                                }
                                let pace_txt = if self.max_speed {
                                    "MAX Speed — so schnell wie die Lektion mitkommt.".to_string()
                                } else {
                                    let ms = (interval_seconds(n) * 1000.0).round() as i32;
                                    format!("exakt {n} / 10 min  ·  {:.2} Anschläge/s  ·  {ms} ms", n as f64 / 600.0)
                                };
                                ui.label(RichText::new(pace_txt).color(COL_MUTED).size(11.0));
                            });
                            ui.add_space(10.0);
                            Frame::new()
                                .fill(COL_PANEL)
                                .stroke(Stroke::new(1.0_f32, COL_LINE))
                                .corner_radius(CornerRadius::same(14))
                                .inner_margin(Margin::same(14))
                                .show(ui, |ui| {
                                    ui.label(RichText::new(ui_labels::REMAINING).color(COL_ACCENT).size(11.0).strong());
                                    ui.add_space(4.0);
                                    ui.label(
                                        RichText::new(&live.remaining)
                                            .color(COL_TEXT)
                                            .size(15.0)
                                            .family(egui::FontFamily::Monospace),
                                    );
                                });
                            ui.add_space(8.0);
                            ui.label(RichText::new(&live.status).color(COL_MUTED).size(12.0));
                            ui.add_space(10.0);
                            ui.horizontal(|ui| {
                                let connect_enabled = !self.connecting && !live.connected;
                                if accent_button(ui, ui_labels::CONNECT, connect_enabled).clicked() {
                                    self.connect();
                                }
                                if accent_button(ui, ui_labels::START, live.connected && !live.typing).clicked() {
                                    self.start_typing();
                                }
                                if ghost_button(ui, ui_labels::STOP).clicked() {
                                    self.stop.store(true, Ordering::SeqCst);
                                    self.set_live(|l| {
                                        l.typing = false;
                                        l.status = "Gestoppt.".into();
                                        l.badge = if l.connected { "verbunden".into() } else { "getrennt".into() };
                                    });
                                }
                            });
                            ui.add_space(8.0);
                            ui.horizontal(|ui| {
                                if ui.checkbox(&mut self.always_on_top, "Immer im Vordergrund").changed() {
                                    let level = if self.always_on_top {
                                        egui::WindowLevel::AlwaysOnTop
                                    } else {
                                        egui::WindowLevel::Normal
                                    };
                                    ctx.send_viewport_cmd(egui::ViewportCommand::WindowLevel(level));
                                    self.persist();
                                }
                                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                                    ui.label(RichText::new(format!("v{VERSION}")).color(COL_MUTED).size(11.0));
                                });
                            });
                            ui.add_space(16.0);
                        },
                    );
                });
            });
    }
}

impl App {
    fn connect(&mut self) {
        if self.email.trim().is_empty() || self.password.is_empty() {
            self.set_live(|l| l.status = "E-Mail und Passwort eintragen.".into());
            return;
        }
        self.persist();
        self.connecting = true;
        self.set_live(|l| {
            l.status = "Starte Browser… Captcha? Seite wird neu geladen.".into();
            l.badge = "verbindet".into();
        });
        let email = self.email.trim().to_string();
        let password = self.password.clone();
        let base = self.base_url();
        let live = self.live.clone();
        thread::spawn(move || {
            let rt = tokio::runtime::Runtime::new().expect("tokio");
            rt.block_on(async move {
                match browser::BrowserSession::launch("Auto").await {
                    Ok(session) => {
                        if let Err(e) = session.login(&email, &password, &base).await {
                            if let Ok(mut g) = live.lock() {
                                g.status = format!("Verbindung fehlgeschlagen: {e}");
                                g.badge = "getrennt".into();
                            }
                            session.quit().await;
                            return;
                        }
                        if let Ok(mut g) = live.lock() {
                            g.connected = true;
                            g.badge = "verbunden".into();
                            g.status = "Verbunden. Level wählen, dann Start Typing.".into();
                        }
                        // Keep session by leaking into a parked thread via channel is heavy;
                        // store in OnceLock-like static for Start Typing.
                        SESSION.lock().unwrap().replace(session);
                    }
                    Err(e) => {
                        if let Ok(mut g) = live.lock() {
                            g.status = format!("Browser: {e}");
                            g.badge = "getrennt".into();
                        }
                    }
                }
            });
        });
    }

    fn start_typing(&mut self) {
        self.stop.store(false, Ordering::SeqCst);
        self.set_live(|l| {
            l.typing = true;
            l.badge = "tippt".into();
            l.status = "Schreibmodus an — Browser kommt in den Vordergrund.".into();
        });
        if self.always_on_top {
            // drop always-on-top while typing so OS keys hit Edge
        }
        let live = self.live.clone();
        let stop = self.stop.clone();
        let base = self.base_url();
        let strokes = clamp_strokes(self.strokes);
        let max_speed = self.max_speed;
        thread::spawn(move || {
            let rt = tokio::runtime::Runtime::new().expect("tokio");
            rt.block_on(async move {
                let session = SESSION.lock().unwrap().take();
                let Some(session) = session else {
                    if let Ok(mut g) = live.lock() {
                        g.typing = false;
                        g.status = "Zuerst verbinden.".into();
                    }
                    return;
                };
                let _ = session.arm_and_focus(&base).await;
                let interval = interval_duration(strokes, max_speed);
                let t0 = std::time::Instant::now();
                let mut sent: u64 = 0;
                while !stop.load(Ordering::SeqCst) {
                    let due = t0 + due_after(sent, interval);
                    let now = std::time::Instant::now();
                    if due > now {
                        tokio::time::sleep(due - now).await;
                    }
                    if stop.load(Ordering::SeqCst) {
                        break;
                    }
                    match session.type_one().await {
                        Ok((ch, remaining, n)) => {
                            sent += 1;
                            if let Ok(mut g) = live.lock() {
                                g.remaining = remaining;
                                let show = if ch == ' ' { "␣".into() } else { ch.to_string() };
                                let pace = if max_speed {
                                    "MAX".to_string()
                                } else {
                                    format!("{strokes}/10min")
                                };
                                g.status = format!("Tippt »{show}« · {pace} · noch {n}");
                                g.typing = true;
                                g.badge = "tippt".into();
                            }
                        }
                        Err(e) => {
                            if stop.load(Ordering::SeqCst) {
                                break;
                            }
                            if let Ok(mut g) = live.lock() {
                                g.status = format!("Kein Tipptext — {e}");
                            }
                            let _ = session.arm_and_focus(&base).await;
                            tokio::time::sleep(Duration::from_millis(250)).await;
                        }
                    }
                }
                SESSION.lock().unwrap().replace(session);
                if let Ok(mut g) = live.lock() {
                    g.typing = false;
                    g.badge = if g.connected { "verbunden".into() } else { "getrennt".into() };
                    if stop.load(Ordering::SeqCst) {
                        g.status = "Gestoppt.".into();
                    }
                }
            });
        });
    }
}

static SESSION: Mutex<Option<browser::BrowserSession>> = Mutex::new(None);

const COL_BG: Color32 = Color32::from_rgb(7, 9, 13);
const COL_PANEL: Color32 = Color32::from_rgb(16, 20, 28);
const COL_CARD: Color32 = Color32::from_rgb(22, 28, 38);
const COL_LINE: Color32 = Color32::from_rgb(42, 52, 68);
const COL_TEXT: Color32 = Color32::from_rgb(244, 246, 248);
const COL_MUTED: Color32 = Color32::from_rgb(154, 164, 178);
const COL_ACCENT: Color32 = Color32::from_rgb(62, 224, 160);
const COL_ACCENT_DIM: Color32 = Color32::from_rgb(18, 64, 48);
const COL_DANGER: Color32 = Color32::from_rgb(251, 113, 133);

fn apply_theme(ctx: &egui::Context) {
    let mut style = (*ctx.style()).clone();
    style.visuals.dark_mode = true;
    style.visuals.panel_fill = COL_BG;
    style.visuals.window_fill = COL_CARD;
    style.visuals.extreme_bg_color = COL_PANEL;
    style.visuals.override_text_color = Some(COL_TEXT);
    style.visuals.widgets.inactive.bg_fill = COL_PANEL;
    style.visuals.widgets.hovered.bg_fill = COL_LINE;
    style.visuals.widgets.active.bg_fill = COL_ACCENT_DIM;
    style.visuals.selection.bg_fill = COL_ACCENT_DIM;
    style.visuals.widgets.inactive.fg_stroke = Stroke::new(1.0_f32, COL_MUTED);
    style.visuals.widgets.hovered.fg_stroke = Stroke::new(1.0_f32, COL_ACCENT);
    style.spacing.item_spacing = Vec2::new(8.0, 6.0);
    ctx.set_style(style);
}

fn header(ui: &mut Ui, live: &Live) {
    Frame::new()
        .fill(COL_PANEL)
        .inner_margin(Margin::symmetric(20, 16))
        .show(ui, |ui| {
            ui.horizontal(|ui| {
                ui.vertical(|ui| {
                    ui.label(RichText::new("TypeHack").color(COL_TEXT).size(26.0).strong());
                    ui.label(RichText::new("native  ·  rust  ·  3.0").color(COL_ACCENT).size(12.0));
                });
                ui.with_layout(egui::Layout::right_to_left(egui::Align::Center), |ui| {
                    let (dot, label) = if live.typing {
                        (COL_ACCENT, live.badge.as_str())
                    } else if live.connected {
                        (Color32::from_rgb(125, 211, 252), live.badge.as_str())
                    } else {
                        (COL_DANGER, live.badge.as_str())
                    };
                    Frame::new()
                        .fill(COL_CARD)
                        .corner_radius(CornerRadius::same(20))
                        .inner_margin(Margin::symmetric(12, 6))
                        .stroke(Stroke::new(1.0_f32, COL_LINE))
                        .show(ui, |ui| {
                            ui.horizontal(|ui| {
                                let (rect, _) = ui.allocate_exact_size(Vec2::splat(8.0), egui::Sense::hover());
                                ui.painter().circle_filled(rect.center(), 4.0, dot);
                                ui.label(RichText::new(label).color(COL_TEXT).size(12.0));
                            });
                        });
                });
            });
        });
}

fn card(ui: &mut Ui, add: impl FnOnce(&mut Ui)) {
    Frame::new()
        .fill(COL_CARD)
        .stroke(Stroke::new(1.0_f32, COL_LINE))
        .corner_radius(CornerRadius::same(16))
        .inner_margin(Margin::same(16))
        .show(ui, |ui| add(ui));
}

fn field(ui: &mut Ui, label: &str, value: &mut String, password: bool) {
    ui.label(RichText::new(label).color(COL_MUTED).size(12.0));
    let mut edit = egui::TextEdit::singleline(value)
        .desired_width(f32::INFINITY)
        .font(FontId::proportional(15.0));
    if password {
        edit = edit.password(true);
    }
    ui.add(edit);
    ui.add_space(6.0);
}

fn accent_button(ui: &mut Ui, text: &str, enabled: bool) -> egui::Response {
    ui.add_enabled(
        enabled,
        egui::Button::new(RichText::new(text).color(Color32::from_rgb(5, 28, 20)).strong())
            .fill(if enabled { COL_ACCENT } else { COL_LINE })
            .corner_radius(CornerRadius::same(10))
            .min_size(Vec2::new(118.0, 36.0)),
    )
}

fn ghost_button(ui: &mut Ui, text: &str) -> egui::Response {
    ui.add(
        egui::Button::new(RichText::new(text).color(COL_DANGER))
            .fill(COL_PANEL)
            .stroke(Stroke::new(1.0_f32, COL_DANGER))
            .corner_radius(CornerRadius::same(10))
            .min_size(Vec2::new(72.0, 36.0)),
    )
}

fn main() -> eframe::Result<()> {
    println!("{WINDOW_TITLE}");
    let options = eframe::NativeOptions {
        viewport: egui::ViewportBuilder::default()
            .with_inner_size([440.0, 700.0])
            .with_min_inner_size([380.0, 560.0])
            .with_title(WINDOW_TITLE),
        ..Default::default()
    };
    eframe::run_native(
        WINDOW_TITLE,
        options,
        Box::new(|cc| Ok(Box::new(App::new(cc)))),
    )
}
