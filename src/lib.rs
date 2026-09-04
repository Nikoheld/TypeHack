//! TypeHack 3.0 core: remaining-prompt extract, pace, OS keys, config.
//! The desktop UI (`src/main.rs`) and tests both call these shipped functions.

pub mod config;
pub mod driver;
pub mod install;
pub mod keys;
pub mod nav;
pub mod pace;
pub mod prompt;
pub mod ui_labels;
pub mod update;
pub mod version;

pub use config::{load_config, load_credentials, merge_config, save_config, save_credentials, Config, PRESET_URLS};
pub use keys::{key_plan_for_glyph, send_glyph, send_glyphs, KeyPlan, SPACE_VIRTUAL_KEY};
pub use nav::{is_achievement_dialog, is_captcha_view, is_dashboard_url, is_start_dialog, OVERVIEW_PATH};
pub use pace::{
    after_strokes_edited, clamp_strokes, due_after, interval_duration, interval_seconds, TypingMode,
    MAX_SPEED_MIN_STROKES, STROKES_DEFAULT, STROKES_MAX, STROKES_MIN,
};
pub use prompt::{
    extract_prompt_from_html, first_remaining_glyph, glyph_payload, glyphs_to_type, keys_for_char,
    normalize_prompt_text, pick_remaining_prompt, PromptError, PROMPT_SELECTORS,
};
pub use version::{is_newer, parse_version, APP_NAME, REPO, VERSION, WINDOW_TITLE};
pub use update::{digest_from_asset, pick_setup_asset, pick_update_asset, sha256_file, UpdateInfo};
