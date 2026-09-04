//! Page-kind helpers: captcha → reload only; achievement dialogs stay closed.

/// Dashboard after login. Never auto-open generateLevel — the user picks the lesson.
pub const OVERVIEW_PATH: &str = "/index.php?r=user/overview";

pub fn is_dashboard_url(url: &str) -> bool {
    let u = url.to_ascii_lowercase();
    u.contains("user/overview")
}

pub fn is_captcha_view(url: &str, html: &str) -> bool {
    let blob = format!("{url}\n{html}").to_ascii_lowercase();
    if blob.contains("loginform") || blob.contains("login-form") || blob.contains("id=\"text_todo") {
        return false;
    }
    blob.contains("chal-form")
        || blob.contains("/_chal/")
        || blob.contains("sicherheitsprüfung")
        || blob.contains("sicherheitspruefung")
        || blob.contains("altcha")
}

pub fn is_achievement_dialog(text: &str) -> bool {
    let t = text.to_ascii_lowercase();
    t.contains("abzeichen") || t.contains("achievement") || t.contains("abzeichenkarte")
}

pub fn is_start_dialog(text: &str) -> bool {
    if is_achievement_dialog(text) {
        return false;
    }
    let t = text.to_ascii_lowercase();
    (t.contains("taste") && t.contains("start"))
        || t.contains("zum starten")
        || t.contains("beliebige taste")
}

pub fn is_achievement_click_target(text_or_href: &str) -> bool {
    let t = text_or_href.to_ascii_lowercase();
    t.contains("abzeichen") || t.contains("achievement") || t.contains("badge")
}