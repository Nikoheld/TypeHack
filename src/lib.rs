//! TypeHack 3.0 core: remaining-prompt extract, pace, OS keys, config.
//! The desktop UI (`src/main.rs`) and tests both call these shipped functions.

pub mod config;
pub mod keys;
pub mod pace;
pub mod prompt;
pub mod ui_labels;
pub mod version;

pub use config::{load_config, load_credentials, merge_config, save_config, save_credentials, Config, PRESET_URLS};
pub use keys::{key_plan_for_glyph, send_glyph, KeyPlan, SPACE_VIRTUAL_KEY};
pub use pace::{clamp_strokes, interval_seconds, STROKES_MAX, STROKES_MIN};
pub use prompt::{
    extract_prompt_from_html, first_remaining_glyph, glyph_payload, glyphs_to_type, keys_for_char,
    normalize_prompt_text, pick_remaining_prompt, PromptError, PROMPT_SELECTORS,
};
pub use version::{APP_NAME, VERSION, WINDOW_TITLE};
