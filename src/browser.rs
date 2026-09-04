//! Edge/Chrome session: login, Schreiben, Start-Dialog, remaining prompt, OS typing.

use std::path::PathBuf;
use std::process::{Child, Command, Stdio};
use std::time::{Duration, Instant};

use thirtyfour::prelude::*;

use typehack::keys::{force_foreground_typewriter, send_glyph};
use typehack::nav::{is_achievement_click_target, is_achievement_dialog, is_captcha_view, is_start_dialog};
use typehack::prompt::{first_remaining_glyph, pick_remaining_prompt, PROMPT_SELECTORS};

const LOGIN_PATH: &str = "/index.php?r=site/login";
const LEVEL_PATH: &str = "/index.php?r=typewriter/runLevel";
const GENERATE_PATH: &str = "/index.php?r=typewriter/generateLevel";

const FOCUS_JS: &str = r#"
window.focus();
if (typeof setFocusMobileText === 'function') { try { setFocusMobileText(); } catch (x) {} }
var nodes=document.querySelectorAll('input,textarea');
for (var i=0;i<nodes.length;i++){
  var e=nodes[i];
  var id=(e.id||''), name=(e.name||''), tp=(e.type||'').toLowerCase();
  if (tp==='password' || tp==='hidden' || tp==='submit' || tp==='button') continue;
  if (/login|user|email|pass/i.test(id+' '+name)) continue;
  try { e.focus({preventScroll:true}); return id||name||tp; } catch (x) {}
}
"#;

const COLLECT_JS: &str = r#"
var sels = arguments[0];
var htmls = [];
var seen = {};
function add(h) {
  h = (h || '').trim();
  if (!h || seen[h]) return;
  seen[h] = 1;
  htmls.push(h);
}
for (var i = 0; i < sels.length; i++) {
  try {
    var nodes = document.querySelectorAll(sels[i]);
    for (var j = 0; j < nodes.length && j < 30; j++) {
      var e = nodes[j];
      add(e.outerHTML);
      var id = e.id || '';
      if (id.indexOf('text_todo') === 0) continue;
      if (e.parentElement) add(e.parentElement.outerHTML);
    }
  } catch (x) {}
}
return htmls;
"#;

pub struct BrowserSession {
    driver: WebDriver,
    child: Option<Child>,
}

impl BrowserSession {
    pub async fn launch(browser: &str) -> Result<Self, String> {
        let port = 9518u16;
        let driver_path = find_msedgedriver().ok_or_else(|| {
            "msedgedriver.exe nicht gefunden. Edge installieren und TypeHack neu starten.".to_string()
        })?;
        let mut cmd = Command::new(&driver_path);
        cmd.arg(format!("--port={port}"))
            .stdin(Stdio::null())
            .stdout(Stdio::null())
            .stderr(Stdio::null());
        #[cfg(windows)]
        {
            use std::os::windows::process::CommandExt;
            cmd.creation_flags(0x08000000);
        }
        let child = cmd.spawn().map_err(|e| format!("msedgedriver: {e}"))?;
        tokio::time::sleep(Duration::from_millis(600)).await;

        let _ = browser;
        let mut caps = DesiredCapabilities::edge();
        let _ = caps.add_arg("--disable-blink-features=AutomationControlled");
        let _ = caps.add_arg("--remote-allow-origins=*");
        let _ = caps.add_arg("--no-first-run");
        let _ = caps.add_arg("--disable-popup-blocking");
        if let Some(bin) = edge_binary() {
            let _ = caps.set_binary(&bin);
        }
        let url = format!("http://127.0.0.1:{port}");
        let driver = WebDriver::new(&url, caps)
            .await
            .map_err(|e| format!("WebDriver: {e}"))?;
        let _ = driver.maximize_window().await;
        Ok(Self {
            driver,
            child: Some(child),
        })
    }

    pub async fn login(&self, email: &str, password: &str, base: &str) -> Result<(), String> {
        let base = base.trim_end_matches('/');
        self.driver
            .goto(&format!("{base}{LOGIN_PATH}"))
            .await
            .map_err(|e| format!("Login-Seite: {e}"))?;
        let deadline = Instant::now() + Duration::from_secs(180);
        let mut submitted = false;
        let mut last_reload = Instant::now();
        while Instant::now() < deadline {
            dismiss_overlays(&self.driver).await;
            close_achievement_dialogs(&self.driver).await;
            if logged_in(&self.driver).await {
                break;
            }
            if !submitted {
                if let (Some(user), Some(pw)) = (
                    first_css(&self.driver, "input#LoginForm_username, input[name*='username' i], input[type='email']").await,
                    first_css(&self.driver, "input#LoginForm_pw, input[type='password']").await,
                ) {
                    fill(&self.driver, &user, email).await;
                    fill(&self.driver, &pw, password).await;
                    if let Some(btn) = first_css(
                        &self.driver,
                        "#login-submit-btn, #login-form input[type='submit'], input[type='submit'][value='Login'], button[type='submit']",
                    )
                    .await
                    {
                        let _ = btn.click().await;
                    } else {
                        let _ = pw.send_keys(thirtyfour::Key::Enter).await;
                    }
                    submitted = true;
                } else if last_reload.elapsed() >= Duration::from_secs(2) {
                    reload_if_captcha(&self.driver).await;
                    last_reload = Instant::now();
                }
            }
            tokio::time::sleep(Duration::from_millis(120)).await;
        }
        close_achievement_dialogs(&self.driver).await;
        let _ = open_write_mode(&self.driver, base).await;
        close_achievement_dialogs(&self.driver).await;
        Ok(())
    }

    #[allow(dead_code)]
    pub async fn remaining(&self) -> Result<String, String> {
        remaining_prompt(&self.driver, Duration::from_secs(3)).await
    }

    pub async fn arm_and_focus(&self, base: &str) -> Result<(), String> {
        let _ = open_write_mode(&self.driver, base.trim_end_matches('/')).await;
        close_achievement_dialogs(&self.driver).await;
        click_lesson_start(&self.driver).await;
        focus_typer(&self.driver).await;
        force_foreground_typewriter();
        Ok(())
    }

    /// One remaining glyph. Does not sleep for pace — the caller owns the wall-clock schedule.
    pub async fn type_one(&self) -> Result<(char, String, usize), String> {
        close_achievement_dialogs(&self.driver).await;
        focus_typer(&self.driver).await;
        let before = remaining_now(&self.driver)
            .await
            .ok_or_else(|| "Tipptext ist leer".to_string())?;
        let ch = first_remaining_glyph(&before).map_err(|e| e.0)?;
        send_glyph(ch)?;
        let now = remaining_now(&self.driver).await.unwrap_or(before);
        Ok((ch, now.clone(), now.chars().count()))
    }

    pub async fn quit(mut self) {
        let _ = self.driver.quit().await;
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
        }
    }
}

async fn remaining_now(driver: &WebDriver) -> Option<String> {
    let htmls = collect_html(driver).await.ok()?;
    pick_remaining_prompt(&htmls).ok()
}

async fn remaining_prompt(driver: &WebDriver, timeout: Duration) -> Result<String, String> {
    let end = Instant::now() + timeout;
    let mut last = "Tipptext ist leer".to_string();
    while Instant::now() < end {
        match remaining_now(driver).await {
            Some(text) => return Ok(text),
            None => last = "Tipptext ist leer".into(),
        }
        tokio::time::sleep(Duration::from_millis(80)).await;
    }
    Err(last)
}

async fn collect_html(driver: &WebDriver) -> Result<Vec<String>, String> {
    let sels: Vec<serde_json::Value> = PROMPT_SELECTORS.iter().map(|s| serde_json::Value::String((*s).into())).collect();
    let ret = driver
        .execute(COLLECT_JS, vec![serde_json::Value::Array(sels)])
        .await
        .map_err(|e| format!("collect: {e}"))?;
    let json = ret.json().clone();
    if let serde_json::Value::Array(items) = json {
        Ok(items.into_iter().filter_map(|v| v.as_str().map(|s| s.to_string())).collect())
    } else {
        Ok(Vec::new())
    }
}

async fn focus_typer(driver: &WebDriver) {
    let _ = driver.execute(FOCUS_JS, vec![]).await;
}

async fn fill(driver: &WebDriver, el: &WebElement, text: &str) {
    let _ = el.click().await;
    let _ = el.clear().await;
    let _ = el.send_keys(text).await;
    let _ = driver
        .execute(
            "var e=arguments[0],v=arguments[1]; e.focus(); e.value=v; e.dispatchEvent(new Event('input',{bubbles:true})); e.dispatchEvent(new Event('change',{bubbles:true}));",
            vec![el.to_json().unwrap_or(serde_json::Value::Null), serde_json::Value::String(text.into())],
        )
        .await;
}

async fn first_css(driver: &WebDriver, css: &str) -> Option<WebElement> {
    let Ok(els) = driver.find_all(By::Css(css)).await else {
        return None;
    };
    for el in els {
        if el.is_displayed().await.unwrap_or(false) {
            return Some(el);
        }
    }
    None
}

async fn logged_in(driver: &WebDriver) -> bool {
    if first_css(driver, "input[type='password']").await.is_some() {
        let url = driver.current_url().await.map(|u| u.to_string()).unwrap_or_default();
        if url.contains("site/login") {
            return false;
        }
    }
    let url = driver.current_url().await.map(|u| u.to_string()).unwrap_or_default();
    if url.contains("site/login") {
        return false;
    }
    if url.contains("runLevel") || url.contains("practise") || url.contains("generateLevel") || url.contains("overview") {
        if url.contains("overview") {
            return driver.find_all(By::Css("a[href*='site/logout']")).await.map(|v| !v.is_empty()).unwrap_or(false);
        }
        return true;
    }
    driver
        .find_all(By::Css("a[href*='site/logout']"))
        .await
        .map(|v| !v.is_empty())
        .unwrap_or(false)
}

async fn dismiss_overlays(driver: &WebDriver) {
    let sels = [
        "button.fc-cta-consent",
        "button[aria-label='Consent']",
        "button.fc-data-preferences-accept-all",
        "button[aria-label='Accept all']",
    ];
    for s in sels {
        if let Some(el) = first_css(driver, s).await {
            let _ = driver.execute("arguments[0].click();", vec![el.to_json().unwrap_or(serde_json::Value::Null)]).await;
        }
    }
}

async fn reload_if_captcha(driver: &WebDriver) {
    let url = driver.current_url().await.map(|u| u.to_string()).unwrap_or_default();
    let html = driver.source().await.unwrap_or_default();
    if is_captcha_view(&url, &html) {
        let _ = driver.refresh().await;
        tokio::time::sleep(Duration::from_millis(400)).await;
    }
}

const CLOSE_ACHIEVEMENT_JS: &str = r#"
(function(){
  var nodes = document.querySelectorAll('.ui-dialog');
  for (var i=0;i<nodes.length;i++){
    var d = nodes[i];
    var t = (d.innerText||'').toLowerCase();
    if (t.indexOf('abzeichen')>=0 || t.indexOf('achievement')>=0) {
      try { if (window.jQuery) jQuery(d).dialog('close'); } catch(e) {}
      d.style.display = 'none';
    }
  }
})();
"#;

async fn close_achievement_dialogs(driver: &WebDriver) {
    let _ = driver.execute(CLOSE_ACHIEVEMENT_JS, vec![]).await;
}

async fn open_write_mode(driver: &WebDriver, base: &str) -> bool {
    if remaining_now(driver).await.is_some() {
        return true;
    }
    close_achievement_dialogs(driver).await;
    // Go straight to the lesson URL — do not click cockpit/badges (that opens Abzeichen).
    for path in [GENERATE_PATH, LEVEL_PATH] {
        let _ = driver.goto(&format!("{base}{path}")).await;
        tokio::time::sleep(Duration::from_millis(400)).await;
        close_achievement_dialogs(driver).await;
        if remaining_now(driver).await.is_some() {
            return true;
        }
    }
    remaining_now(driver).await.is_some()
}

async fn click_lesson_start(driver: &WebDriver) {
    close_achievement_dialogs(driver).await;
    if let Ok(dialogs) = driver.find_all(By::Css(".ui-dialog")).await {
        for dlg in dialogs {
            let text = dlg.text().await.unwrap_or_default();
            if is_achievement_dialog(&text) {
                continue;
            }
            if !is_start_dialog(&text) {
                continue;
            }
            if let Ok(btns) = dlg.find_all(By::Css("button")).await {
                for btn in btns {
                    let bt = btn.text().await.unwrap_or_default();
                    if is_achievement_click_target(&bt) {
                        continue;
                    }
                    if btn.is_displayed().await.unwrap_or(false) {
                        let _ = btn.click().await;
                        return;
                    }
                }
            }
        }
    }
}

fn edge_binary() -> Option<String> {
    for p in [
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    ] {
        if PathBuf::from(p).is_file() {
            return Some(p.into());
        }
    }
    None
}

fn find_msedgedriver() -> Option<PathBuf> {
    if let Ok(home) = std::env::var("USERPROFILE") {
        let root = PathBuf::from(home).join(r".cache\selenium\msedgedriver\win64");
        if let Ok(iter) = std::fs::read_dir(&root) {
            let mut best: Option<PathBuf> = None;
            for ent in iter.flatten() {
                let p = ent.path().join("msedgedriver.exe");
                if p.is_file() {
                    best = Some(p);
                }
            }
            if best.is_some() {
                return best;
            }
        }
    }
    for p in [
        PathBuf::from("msedgedriver.exe"),
        PathBuf::from(r".\msedgedriver.exe"),
    ] {
        if p.is_file() {
            return Some(p);
        }
    }
    None
}
