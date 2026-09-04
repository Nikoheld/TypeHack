//! Drive the shipped remaining-prompt and pace helpers — same fixtures as TypeHack 2.x.

use typehack::*;

const LINE_WITH_SPACES: &str = concat!(
    r#"<div id="typewriter-text">"#,
    r#"<span class="letter">H</span><span class="letter">a</span>"#,
    r#"<span class="letter">l</span><span class="letter">l</span>"#,
    r#"<span class="letter">o</span>"#,
    r#"<span class="space">&nbsp;</span>"#,
    r#"<span class="letter">W</span><span class="letter">e</span>"#,
    r#"<span class="letter">l</span><span class="letter">t</span>"#,
    r#"<span class="blank"></span>"#,
    r#"<span class="letter">ö</span>"#,
    " ",
    r#"<span class="letter">ü</span>"#,
    "</div>",
);

const SPACE_ONLY_NBSP: &str = r#"<div id="typewriter-text"><span class="space">&nbsp;</span></div>"#;
const SPACE_ONLY_TEXT: &str = r#"<div id="typewriter-text"> </div>"#;
const EMPTY_WRAPPER: &str = r#"<div class="current-line"></div>"#;
const DONE_PREFIX: &str = concat!(
    r#"<div id="typewriter-text">"#,
    r#"<span class="letter done">H</span>"#,
    r#"<span class="letter correct">a</span>"#,
    r#"<span class="letter">l</span>"#,
    r#"<span class="space">&nbsp;</span>"#,
    r#"<span class="letter">ö</span>"#,
    "</div>",
);
const TODO_LINE: &str = concat!(
    r#"<div id="text_todo_1">"#,
    "<span>H</span><span>a</span><span>l</span><span>l</span><span>o</span>",
    "<span></span>",
    "<span>W</span><span>e</span><span>l</span><span>t</span>",
    "<span> </span>",
    "<span>ö</span>",
    "</div>",
);
const TODO_SPACE_EMPTY: &str = r#"<div id="text_todo_1"><span></span></div>"#;
const TODO_SPACE_NBSP: &str = r#"<div id="text_todo_1"><span>&nbsp;</span></div>"#;
const TODO_SPACE_TEXT: &str = r#"<div id="text_todo_1"><span> </span></div>"#;
const TODO_AFTER_DONE_PARENT: &str = concat!(
    r#"<div class="tw-wrap">"#,
    r#"<div id="text_done_1"><span>H</span><span>a</span></div>"#,
    r#"<div id="text_todo_1"><span>l</span><span></span><span>ö</span></div>"#,
    "</div>",
);

#[test]
fn version_is_3_0_0() {
    assert_eq!(VERSION, "3.0.0");
    assert_eq!(WINDOW_TITLE, "TypeHack 3.0.0");
}

#[test]
fn clamp_and_interval_match_2x() {
    assert_eq!(clamp_strokes(2000), 2000);
    assert_eq!(clamp_strokes(50), 200);
    assert_eq!(clamp_strokes(99999), 8000);
    assert!((interval_seconds(2000) - 0.3).abs() < 1e-12);
    assert!((interval_seconds(600) - 1.0).abs() < 1e-12);
}

#[test]
fn wall_clock_schedule_hits_2000_per_10_min() {
    use std::time::Duration;
    use typehack::pace::{due_after, expected_strokes_per_10min, interval_duration};
    let iv = interval_duration(2000, false);
    assert!((iv.as_secs_f64() - 0.3).abs() < 1e-12);
    assert_eq!(due_after(0, iv), Duration::ZERO);
    assert!((due_after(1, iv).as_secs_f64() - 0.3).abs() < 1e-12);
    assert!((due_after(10, iv).as_secs_f64() - 3.0).abs() < 1e-9);
    assert!((expected_strokes_per_10min(iv) - 2000.0).abs() < 1e-6);
    assert!(interval_duration(2000, true).is_zero());
    assert!(expected_strokes_per_10min(Duration::ZERO).is_infinite());
}

#[test]
fn captcha_reload_not_login_or_lesson() {
    assert!(is_captcha_view(
        "https://at4.typewriter.at/_chal/x",
        "<form id='chal-form'><h1>Sicherheitsprüfung</h1></form>"
    ));
    assert!(!is_captcha_view(
        "https://at4.typewriter.at/index.php?r=site/login",
        r#"<form id="login-form"><input id="LoginForm_username"></form>"#
    ));
    assert!(!is_captcha_view(
        "https://at4.typewriter.at/index.php?r=typewriter/runLevel",
        r#"<div id="text_todo_1"><span>a</span></div>"#
    ));
}

#[test]
fn post_login_stays_on_dashboard_not_generate_level() {
    assert_eq!(OVERVIEW_PATH, "/index.php?r=user/overview");
    assert!(is_dashboard_url(
        "https://at4.typewriter.at/index.php?r=user/overview"
    ));
    assert!(!is_dashboard_url(
        "https://at4.typewriter.at/index.php?r=typewriter/generateLevel"
    ));
    assert!(!OVERVIEW_PATH.contains("generateLevel"));
}

#[test]
fn achievement_card_is_not_the_start_dialog() {
    assert!(is_achievement_dialog("Abzeichen Close"));
    assert!(!is_start_dialog("Abzeichen Close"));
    assert!(is_start_dialog(
        "Achtung! Fertig! ...\nDrücke eine beliebige Taste zum Starten\nStart"
    ));
    assert!(!is_start_dialog("Pause\nDer Schreibmodus wurde pausiert!"));
}

#[test]
fn extract_keeps_abstaende_and_umlauts() {
    let text = extract_prompt_from_html(LINE_WITH_SPACES);
    assert!(text.contains("Hallo"));
    assert!(text.contains("Welt"));
    assert!(text.contains('ö'));
    assert!(text.contains('ü'));
    assert!(text.contains(' '));
    assert_ne!(text.replace(' ', ""), text);
    assert!(text.contains("Hallo Welt"));
}

#[test]
fn space_only_remaining_is_typeable() {
    for html in [SPACE_ONLY_NBSP, SPACE_ONLY_TEXT] {
        let text = pick_remaining_prompt(&[html.to_string()]).unwrap();
        assert!(!text.is_empty());
        assert_eq!(text.trim_matches(['\n', '\r']), text);
        assert!(text.chars().all(|c| c == ' '));
        assert_eq!(glyphs_to_type(&text), vec![' '; text.len()]);
    }
}

#[test]
fn empty_wrapper_loses_to_real_line() {
    let picked = pick_remaining_prompt(&[EMPTY_WRAPPER.into(), LINE_WITH_SPACES.into()]).unwrap();
    assert_eq!(picked, extract_prompt_from_html(LINE_WITH_SPACES));
    let err = pick_remaining_prompt(&[EMPTY_WRAPPER.into()]).unwrap_err();
    assert!(err.0.to_lowercase().contains("leer"));
}

#[test]
fn skips_already_typed_spans() {
    let remaining = extract_prompt_from_html(DONE_PREFIX);
    assert!(!remaining.starts_with("Ha"));
    assert!(remaining.starts_with('l'));
    assert!(remaining.contains(' '));
    assert!(remaining.contains('ö'));
    assert_eq!(glyphs_to_type(&remaining), remaining.chars().collect::<Vec<_>>());
}

#[test]
fn text_todo_1_keeps_letter_and_empty_space_spans() {
    let text = extract_prompt_from_html(TODO_LINE);
    assert_eq!(text, "Hallo Welt ö");
    assert_eq!(glyphs_to_type(&text), "Hallo Welt ö".chars().collect::<Vec<_>>());
    assert!(PROMPT_SELECTORS.iter().any(|s| s.contains("text_todo_1")));
}

#[test]
fn text_todo_1_space_only_remaining_is_typeable() {
    for html in [TODO_SPACE_EMPTY, TODO_SPACE_NBSP, TODO_SPACE_TEXT] {
        let text = pick_remaining_prompt(&[html.into()]).unwrap();
        assert!(text.chars().all(|c| c == ' '));
        assert_eq!(glyphs_to_type(&text), vec![' '; text.len()]);
    }
}

#[test]
fn text_todo_1_preferred_over_done_parent() {
    let todo = r#"<div id="text_todo_1"><span>l</span><span></span><span>ö</span></div>"#;
    let picked = pick_remaining_prompt(&[
        TODO_AFTER_DONE_PARENT.into(),
        todo.into(),
        EMPTY_WRAPPER.into(),
    ])
    .unwrap();
    assert_eq!(picked, "l ö");
    assert!(!picked.starts_with("Ha"));
}

#[test]
fn pretty_printed_indent_is_not_typed_spaces() {
    let html = r#"<div id="typewriter-text">
  <span class="letter done">A</span>
  <span class="letter">b</span>
  <span class="space">&nbsp;</span>
  <span class="letter">ö</span>
</div>"#;
    let remaining = extract_prompt_from_html(html);
    assert_eq!(remaining, "b ö");
    assert_eq!(glyphs_to_type(&remaining), vec!['b', ' ', 'ö']);
}

#[test]
fn first_remaining_glyph_is_next_key() {
    let remaining = extract_prompt_from_html(r#"<div id="text_todo_1"><span>l</span><span></span><span>ö</span></div>"#);
    assert_eq!(first_remaining_glyph(&remaining).unwrap(), 'l');
    assert_eq!(first_remaining_glyph(" ö").unwrap(), ' ');
    assert_eq!(first_remaining_glyph("ö").unwrap(), 'ö');
}

#[test]
fn payload_is_glyph_not_scan_code() {
    for ch in [' ', '\u{00a0}', 'z', 'y', 'ö', 'ß', '*'] {
        let info = glyph_payload(ch);
        let want = if ch == ' ' || ch == '\u{00a0}' { ' ' } else { ch };
        assert_eq!(info.insert_text.chars().next().unwrap(), want);
        assert_eq!(keys_for_char(ch), want);
        assert!(
            !info.code.starts_with("Key"),
            "{ch:?} must not use physical Key* (QWERTZ remaps y/z)"
        );
    }
}

#[test]
fn space_uses_virtual_key_32() {
    let plan = key_plan_for_glyph(' ');
    assert_eq!(plan.vk, SPACE_VIRTUAL_KEY);
    assert_eq!(SPACE_VIRTUAL_KEY, 32);
    assert_eq!(key_plan_for_glyph('\u{00a0}').vk, 32);
    let payload = glyph_payload(' ');
    assert_eq!(payload.vk, 32);
    assert_eq!(payload.code, "Space");
}

#[test]
fn qwertz_y_and_z_stay_distinct() {
    let y = glyph_payload('y');
    let z = glyph_payload('z');
    assert_eq!(y.insert_text, "y");
    assert_eq!(z.insert_text, "z");
    assert_ne!(y.insert_text, z.insert_text);
    assert_ne!(y.code, "KeyZ");
    assert_ne!(z.code, "KeyY");
    assert_eq!(y.vk, 0);
    assert_eq!(z.vk, 0);
}

#[test]
fn ui_exposes_product_controls() {
    let all = typehack::ui_labels::all_controls();
    for need in [
        "E-Mail",
        "Passwort",
        "Server",
        "Anschläge / 10 Minuten",
        "Verbinden",
        "Start Typing",
        "Stop",
        "MAX Speed",
    ] {
        assert!(all.contains(&need), "missing {need}");
    }
}

#[test]
fn keys_for_char_spaces_and_letters() {
    assert_eq!(keys_for_char(' '), ' ');
    assert_eq!(keys_for_char('\u{00a0}'), ' ');
    assert_eq!(keys_for_char('a'), 'a');
    assert_eq!(normalize_prompt_text("a\u{00a0}b"), "a b");
}

#[test]
fn live_text_todo_current_char_plus_rest_blob() {
    let html = concat!(
        r#"<div id="text_todo_1">"#,
        r#"<span id="wvbgbgywma" style="background: rgba(84,84,84,0.2);">A</span>"#,
        r#"<span id="mlxpzkmrpk">laskaöl hjk Xaver *</span>"#,
        "</div>",
    );
    let text = extract_prompt_from_html(html);
    assert_eq!(first_remaining_glyph(&text).unwrap(), 'A');
    assert!(text.contains('ö'));
    assert!(text.contains('*'));
    assert!(text.starts_with("Alaska"));
}
