//! Edge/Chrome session: login, Schreiben, Start-Dialog, remaining prompt, OS typing.

use std::path::Path;
use std::process::{Child, Command, Stdio};
use std::sync::Mutex;
use std::time::{Duration, Instant};

use serde_json::json;
use thirtyfour::extensions::cdp::ChromeDevTools;
use thirtyfour::prelude::*;

use typehack::keys::{
    ensure_caps_off, force_foreground_typewriter, release_modifiers, send_glyph, send_glyphs, send_start_key,
};
use typehack::nav::{
    is_achievement_click_target, is_achievement_dialog, is_captcha_view, is_dashboard_url, is_start_button,
    is_start_dialog, OVERVIEW_PATH,
};
use typehack::prompt::{
    first_remaining_glyph, glyph_was_consumed, pick_remaining_prompt, PROMPT_SELECTORS,
};

const LOGIN_PATH: &str = "/index.php?r=site/login";

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

/// Layout-independent insert: hidden input + keyup/input + jQuery (typewriter.at).
const JS_SEND_GLYPH: &str = r#"
var ch = String(arguments[0] || '');
if (!ch) return false;
if (typeof setFocusMobileText === 'function') { try { setFocusMobileText(); } catch (x) {} }
var which = (ch === ' ' || ch === '\xa0') ? 32 : ch.charCodeAt(0);
var key = (ch === ' ' || ch === '\xa0') ? ' ' : ch;
var code = (key === ' ') ? 'Space' : '';
function fire(target, type) {
  if (!target || !target.dispatchEvent) return;
  var init = {
    key: key, code: code, bubbles: true, cancelable: true, composed: true,
    keyCode: which, which: which, charCode: type === 'keypress' ? which : 0,
    view: window
  };
  var ev;
  try { ev = new KeyboardEvent(type, init); } catch (e) { return; }
  try {
    Object.defineProperty(ev, 'keyCode', {get: function(){return which;}});
    Object.defineProperty(ev, 'which', {get: function(){return which;}});
    Object.defineProperty(ev, 'key', {get: function(){return key;}});
  } catch (e) {}
  target.dispatchEvent(ev);
}
var el = document.activeElement;
if (!el || el === document.body || el === document.documentElement) {
  var nodes = document.querySelectorAll('input,textarea');
  for (var i = 0; i < nodes.length; i++) {
    var e = nodes[i];
    var tp = (e.type || '').toLowerCase();
    if (tp === 'password' || tp === 'hidden' || tp === 'submit' || tp === 'button') continue;
    if (/login|user|email|pass/i.test((e.id || '') + ' ' + (e.name || ''))) continue;
    try { e.focus({preventScroll: true}); el = e; break; } catch (x) {}
  }
}
try {
  if (el && (el.tagName === 'INPUT' || el.tagName === 'TEXTAREA')) {
    el.focus();
    try { document.execCommand('insertText', false, key); } catch (x) {}
    try {
      el.dispatchEvent(new InputEvent('beforeinput', {bubbles: true, cancelable: true, inputType: 'insertText', data: key}));
      el.dispatchEvent(new InputEvent('input', {bubbles: true, inputType: 'insertText', data: key}));
    } catch (x) {
      el.dispatchEvent(new Event('input', {bubbles: true}));
    }
  }
} catch (x) {}
var nodes = [el, document.getElementById('text_todo_1'), document.body, document];
var seen = [];
nodes.forEach(function(n) {
  if (!n || seen.indexOf(n) >= 0) return;
  seen.push(n);
  fire(n, 'keydown'); fire(n, 'keypress'); fire(n, 'keyup');
});
if (window.jQuery) {
  ['keydown','keypress','keyup'].forEach(function(type) {
    var je = jQuery.Event(type);
    je.which = which; je.keyCode = which; je.charCode = which; je.key = key;
    jQuery(document).trigger(je);
    jQuery('body').trigger(je);
    jQuery('#text_todo_1').trigger(je);
  });
}
return true;
"#;

pub struct BrowserSession {
    driver: WebDriver,
    child: Option<Child>,
    last_burst: Mutex<Option<(String, Instant)>>,
}

impl BrowserSession {
    pub async fn launch(browser: &str) -> Result<Self, String> {
        let _ = browser;
        if typehack::driver::edge_binary().is_none() {
            return Err("Microsoft Edge fehlt. Bitte Edge installieren: https://www.microsoft.com/edge".into());
        }
        let driver_path = typehack::driver::ensure_msedgedriver().map_err(|e| format!("Edge-Treiber: {e}"))?;
        let mut last = "WebDriver startet nicht".to_string();
        for port in 9518u16..9532 {
            match launch_on_port(&driver_path, port).await {
                Ok(session) => return Ok(session),
                Err(e) => last = e,
            }
        }
        Err(format!("Browser startet nicht ({last}). TypeHack schließen und Verbinden erneut klicken."))
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
        stay_on_dashboard(&self.driver, base).await;
        close_achievement_dialogs(&self.driver).await;
        if !logged_in(&self.driver).await {
            return Err(
                "Login nicht geschafft. Captcha im Edge-Fenster lösen, dann nochmal Verbinden.".into(),
            );
        }
        Ok(())
    }

    #[allow(dead_code)]
    pub async fn remaining(&self) -> Result<String, String> {
        remaining_prompt(&self.driver, Duration::from_secs(3)).await
    }

    pub async fn arm_and_focus(&self, _base: &str) -> Result<(), String> {
        // Stay on the page the user opened. Do not jump to generateLevel.
        close_achievement_dialogs(&self.driver).await;
        dismiss_start_dialog(&self.driver).await;
        release_modifiers();
        ensure_caps_off();
        focus_typer(&self.driver).await;
        force_foreground_typewriter();
        Ok(())
    }

    /// One remaining glyph. Does not sleep for pace — the caller owns the wall-clock schedule.
    pub async fn type_one(&self) -> Result<(char, String, usize), String> {
        focus_typer(&self.driver).await;
        let before = remaining_now(&self.driver)
            .await
            .ok_or_else(|| "Tipptext ist leer".to_string())?;
        let ch = first_remaining_glyph(&before).map_err(|e| e.0)?;
        let now = self.deliver_glyph(ch, &before).await?;
        Ok((ch, now.clone(), now.chars().count()))
    }

    /// Dump the whole remaining line via OS keys — no Selenium between keystrokes.
    /// That's what makes MAX Speed (≥ 100000 / 10 min) possible.
    /// Returns `(0, remaining, n)` when the same line is still on screen so the
    /// caller waits instead of typing it twice. Retries after 80 ms if keys missed.
    pub async fn type_line_max(&self) -> Result<(usize, String, usize), String> {
        force_foreground_typewriter();
        let before = remaining_now(&self.driver)
            .await
            .ok_or_else(|| "Tipptext ist leer".to_string())?;
        let glyphs = typehack::glyphs_to_type(&before);
        if glyphs.is_empty() {
            return Err("Tipptext ist leer".into());
        }
        {
            let last = self.last_burst.lock().unwrap_or_else(|e| e.into_inner());
            if let Some((text, t0)) = last.as_ref() {
                if text == &before && t0.elapsed() < Duration::from_millis(80) {
                    return Ok((0, before.clone(), before.chars().count()));
                }
            }
        }
        send_glyphs(&glyphs)?;
        if let Ok(mut last) = self.last_burst.lock() {
            *last = Some((before.clone(), Instant::now()));
        }
        tokio::time::sleep(Duration::from_millis((2 + glyphs.len() / 8).min(20) as u64)).await;
        let mut now = remaining_now(&self.driver).await.unwrap_or_default();
        // OS keys miss ß, dead keys, AltGr on some layouts — finish leftovers via JS/CDP.
        let leftover = typehack::glyphs_to_type(&now);
        if !leftover.is_empty() && leftover.len() <= glyphs.len() {
            for ch in leftover {
                now = self.deliver_glyph(ch, &now).await.unwrap_or(now);
                if now.is_empty() {
                    break;
                }
            }
        }
        let n = now.chars().count();
        Ok((glyphs.len(), now, n))
    }

    async fn deliver_glyph(&self, ch: char, before: &str) -> Result<String, String> {
        send_glyph(ch)?;
        let mut now = remaining_now(&self.driver).await.unwrap_or_else(|| before.to_string());
        if glyph_was_consumed(before, &now, ch) {
            return Ok(now);
        }
        let _ = js_send_glyph(&self.driver, ch).await;
        now = remaining_now(&self.driver).await.unwrap_or(now);
        if glyph_was_consumed(before, &now, ch) {
            return Ok(now);
        }
        let _ = cdp_send_glyph(&self.driver, ch).await;
        now = remaining_now(&self.driver).await.unwrap_or(now);
        Ok(now)
    }

    pub async fn quit(mut self) {
        let _ = self.driver.quit().await;
        if let Some(mut child) = self.child.take() {
            let _ = child.kill();
        }
    }
}

async fn launch_on_port(driver_path: &Path, port: u16) -> Result<BrowserSession, String> {
    let mut cmd = Command::new(driver_path);
    cmd.arg(format!("--port={port}"))
        .stdin(Stdio::null())
        .stdout(Stdio::null())
        .stderr(Stdio::null());
    #[cfg(windows)]
    {
        use std::os::windows::process::CommandExt;
        cmd.creation_flags(0x08000000);
    }
    let mut child = cmd.spawn().map_err(|e| format!("msedgedriver: {e}"))?;
    tokio::time::sleep(Duration::from_millis(500)).await;
    let mut caps = DesiredCapabilities::edge();
    let _ = caps.add_arg("--disable-blink-features=AutomationControlled");
    let _ = caps.add_arg("--remote-allow-origins=*");
    let _ = caps.add_arg("--no-first-run");
    let _ = caps.add_arg("--disable-popup-blocking");
    if let Some(bin) = typehack::driver::edge_binary() {
        let _ = caps.set_binary(&bin.to_string_lossy());
    }
    let url = format!("http://127.0.0.1:{port}");
    match WebDriver::new(&url, caps).await {
        Ok(driver) => {
            let _ = driver.maximize_window().await;
            Ok(BrowserSession {
                driver,
                child: Some(child),
                last_burst: Mutex::new(None),
            })
        }
        Err(e) => {
            let _ = child.kill();
            Err(format!("WebDriver: {e}"))
        }
    }
}

async fn js_send_glyph(driver: &WebDriver, ch: char) -> Result<(), String> {
    let glyph = typehack::keys_for_char(ch).to_string();
    driver
        .execute(JS_SEND_GLYPH, vec![serde_json::Value::String(glyph)])
        .await
        .map(|_| ())
        .map_err(|e| format!("js: {e}"))
}

async fn cdp_send_glyph(driver: &WebDriver, ch: char) -> Result<(), String> {
    let info = typehack::glyph_payload(ch);
    let dt = ChromeDevTools::new(driver.handle.clone());
    let key = info.key.clone();
    let text = info.insert_text.clone();
    let vk = u32::from(info.vk);
    let down = json!({
        "type": "keyDown",
        "key": key,
        "text": text,
        "unmodifiedText": text,
        "windowsVirtualKeyCode": vk,
        "nativeVirtualKeyCode": vk,
    });
    let chr = json!({
        "type": "char",
        "key": key,
        "text": text,
        "unmodifiedText": text,
    });
    let up = json!({
        "type": "keyUp",
        "key": key,
        "windowsVirtualKeyCode": vk,
        "nativeVirtualKeyCode": vk,
    });
    dt.execute_cdp_with_params("Input.dispatchKeyEvent", down)
        .await
        .map_err(|e| format!("cdp: {e}"))?;
    dt.execute_cdp_with_params("Input.dispatchKeyEvent", chr)
        .await
        .map_err(|e| format!("cdp: {e}"))?;
    dt.execute_cdp_with_params("Input.dispatchKeyEvent", up)
        .await
        .map_err(|e| format!("cdp: {e}"))?;
    Ok(())
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

async fn has_logout(driver: &WebDriver) -> bool {
    for css in [
        "a[href*='site/logout']",
        "a[href*='logout']",
        "a[href*='site/logout']",
    ] {
        if driver.find_all(By::Css(css)).await.map(|v| !v.is_empty()).unwrap_or(false) {
            return true;
        }
    }
    false
}

async fn logged_in(driver: &WebDriver) -> bool {
    let url = driver.current_url().await.map(|u| u.to_string()).unwrap_or_default();
    if url.contains("site/login") || url.contains("/_chal") {
        return false;
    }
    if url.contains("runLevel") || url.contains("practise") || url.contains("generateLevel") {
        return true;
    }
    if has_logout(driver).await {
        return true;
    }
    if url.contains("overview") || url.contains("r=user/") {
        return first_css(driver, "input#LoginForm_pw, input[type='password']").await.is_none();
    }
    false
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

async fn stay_on_dashboard(driver: &WebDriver, base: &str) {
    let url = driver.current_url().await.map(|u| u.to_string()).unwrap_or_default();
    if is_dashboard_url(&url) {
        return;
    }
    if url.contains("generateLevel") || url.contains("runLevel") {
        let _ = driver.goto(&format!("{base}{OVERVIEW_PATH}")).await;
        tokio::time::sleep(Duration::from_millis(400)).await;
        return;
    }
    if !url.contains("site/login") {
        let _ = driver.goto(&format!("{base}{OVERVIEW_PATH}")).await;
        tokio::time::sleep(Duration::from_millis(400)).await;
    }
}

const START_DIALOG_JS: &str = r#"
(function(){
  var nodes = document.querySelectorAll('.ui-dialog, .modal, [role="dialog"]');
  for (var i=0;i<nodes.length;i++){
    var el = nodes[i];
    var st = window.getComputedStyle(el);
    if (st.display==='none' || st.visibility==='hidden') continue;
    var s = (el.innerText||'').toLowerCase();
    if (s.indexOf('abzeichen')>=0) continue;
    if (s.indexOf('beliebige taste')>=0 || s.indexOf('zum starten')>=0 || (s.indexOf('taste')>=0 && s.indexOf('start')>=0)) return true;
  }
  return false;
})()
"#;

async fn start_dialog_open(driver: &WebDriver) -> bool {
    if let Ok(ret) = driver.execute(START_DIALOG_JS, vec![]).await {
        if ret.json().as_bool() == Some(true) {
            return true;
        }
    }
    let Ok(dialogs) = driver.find_all(By::Css(".ui-dialog")).await else {
        return false;
    };
    for dlg in dialogs {
        if !dlg.is_displayed().await.unwrap_or(false) {
            continue;
        }
        let text = dlg.text().await.unwrap_or_default();
        if is_start_dialog(&text) {
            return true;
        }
    }
    false
}

async fn click_lesson_start(driver: &WebDriver) {
    close_achievement_dialogs(driver).await;
    let Ok(dialogs) = driver.find_all(By::Css(".ui-dialog")).await else {
        return;
    };
    for dlg in dialogs {
        let text = dlg.text().await.unwrap_or_default();
        if is_achievement_dialog(&text) || !is_start_dialog(&text) {
            continue;
        }
        if let Ok(btns) = dlg.find_all(By::Css("button")).await {
            let mut fallback = None;
            for btn in btns {
                let bt = btn.text().await.unwrap_or_default();
                if is_achievement_click_target(&bt) {
                    continue;
                }
                if !btn.is_displayed().await.unwrap_or(false) {
                    continue;
                }
                if is_start_button(&bt) {
                    let _ = btn.click().await;
                    return;
                }
                fallback = Some(btn);
            }
            if let Some(btn) = fallback {
                let _ = btn.click().await;
            }
        }
    }
}

/// The start overlay eats the first lesson key → always a mistake at the beginning.
/// Dismiss it with Enter, then wait until it is gone.
async fn dismiss_start_dialog(driver: &WebDriver) {
    close_achievement_dialogs(driver).await;
    if !start_dialog_open(driver).await {
        return;
    }
    click_lesson_start(driver).await;
    tokio::time::sleep(Duration::from_millis(150)).await;
    if start_dialog_open(driver).await {
        force_foreground_typewriter();
        focus_typer(driver).await;
        let _ = send_start_key();
    }
    let deadline = Instant::now() + Duration::from_secs(2);
    while Instant::now() < deadline && start_dialog_open(driver).await {
        tokio::time::sleep(Duration::from_millis(40)).await;
    }
    tokio::time::sleep(Duration::from_millis(120)).await;
}


