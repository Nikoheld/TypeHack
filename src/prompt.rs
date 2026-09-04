//! Remaining-prompt extract from typewriter.at markup.
//! Port of the 2.x `_PromptParser` so empty spans are spaces and done spans are skipped.

use std::collections::HashSet;

pub const PROMPT_SELECTORS: &[&str] = &[
    "#text_todo_1",
    "[id^='text_todo']",
    "#text_todo",
    "#typewriter-text",
    ".typewriter-text",
    "#textToType",
    "#tw-text",
    "#twText",
    ".tw-text",
    ".typewriter-line",
    ".current-line",
    "[data-prompt]",
    ".letter, .char, span.letter, span.char",
];

const DONE_HINTS: &[&str] = &[
    "done", "typed", "correct", "ok", "past", "completed", "right", "hit", "success",
    "written", "already", "error", "wrong", "false", "miss",
];
const SPACE_HINTS: &[&str] = &[
    "space", "blank", "gap", "nbsp", "whitespace", "word-sep", "wordsep", "word_sep",
];
const SKIP_TAGS: &[&str] = &["script", "style", "noscript", "svg"];
const LEAF_SPACE_TAGS: &[&str] = &["span", "i", "b", "em", "strong", "font"];

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct PromptError(pub String);

impl std::fmt::Display for PromptError {
    fn fmt(&self, f: &mut std::fmt::Formatter<'_>) -> std::fmt::Result {
        write!(f, "{}", self.0)
    }
}

impl std::error::Error for PromptError {}

pub fn normalize_prompt_text(raw: &str) -> String {
    let mut text = raw.to_string();
    for src in ['\u{00a0}', '\u{202f}', '\u{2002}', '\u{2003}', '\u{2009}', '\t'] {
        text = text.replace(src, " ");
    }
    text.replace(['\n', '\r'], "")
}

pub fn keys_for_char(ch: char) -> char {
    match ch {
        ' ' | '\u{00a0}' | '\u{202f}' | '\u{2009}' => ' ',
        '\n' | '\r' => '\n',
        other => other,
    }
}

pub fn glyphs_to_type(text: &str) -> Vec<char> {
    normalize_prompt_text(text).chars().map(keys_for_char).collect()
}

pub fn first_remaining_glyph(text: &str) -> Result<char, PromptError> {
    glyphs_to_type(text)
        .into_iter()
        .next()
        .ok_or_else(|| PromptError("Tipptext ist leer".into()))
}

#[derive(Debug, Clone, PartialEq, Eq)]
pub struct GlyphPayload {
    pub glyph: char,
    pub key: String,
    pub code: String,
    pub vk: u16,
    pub text: String,
    pub insert_text: String,
}

pub fn glyph_payload(ch: char) -> GlyphPayload {
    let glyph = keys_for_char(ch);
    if glyph == ' ' {
        return GlyphPayload {
            glyph: ' ',
            key: " ".into(),
            code: "Space".into(),
            vk: crate::keys::SPACE_VIRTUAL_KEY,
            text: " ".into(),
            insert_text: " ".into(),
        };
    }
    if glyph == '\n' {
        return GlyphPayload {
            glyph: '\n',
            key: "Enter".into(),
            code: "Enter".into(),
            vk: 13,
            text: "\r".into(),
            insert_text: "\n".into(),
        };
    }
    let s = glyph.to_string();
    GlyphPayload {
        glyph,
        key: s.clone(),
        code: String::new(),
        vk: 0,
        text: s.clone(),
        insert_text: s,
    }
}

fn token_match(blob: &str, hints: &[&str]) -> bool {
    let normalized = blob.replace('_', "-").replace(',', " ");
    let parts: HashSet<&str> = normalized.split_whitespace().collect();
    for hint in hints {
        for part in &parts {
            if part == hint || part.starts_with(&format!("{hint}-")) || part.ends_with(&format!("-{hint}")) {
                return true;
            }
        }
    }
    false
}

#[derive(Default)]
struct PromptParser {
    parts: Vec<String>,
    skip: i32,
    tag_stack: Vec<String>,
    spacey_stack: Vec<bool>,
    had_data_stack: Vec<bool>,
}

impl PromptParser {
    fn start_tag(&mut self, tag: &str, attrs: &[(String, String)]) {
        let tag = tag.to_ascii_lowercase();
        self.tag_stack.push(tag.clone());
        if SKIP_TAGS.contains(&tag.as_str()) {
            self.skip += 1;
            self.spacey_stack.push(false);
            self.had_data_stack.push(true);
            return;
        }
        let blob = attr_blob(attrs);
        if self.skip > 0 || token_match(&blob, DONE_HINTS) {
            self.skip += 1;
            self.spacey_stack.push(false);
            self.had_data_stack.push(true);
            return;
        }
        let spacey = token_match(&blob, SPACE_HINTS);
        self.spacey_stack.push(spacey);
        self.had_data_stack.push(false);
    }

    fn end_tag(&mut self) {
        if self.tag_stack.is_empty() {
            return;
        }
        let opened = self.tag_stack.pop().unwrap_or_default();
        let spacey = self.spacey_stack.pop().unwrap_or(false);
        let mut had = self.had_data_stack.pop().unwrap_or(false);
        if self.skip > 0 {
            self.skip -= 1;
            return;
        }
        let leaf_space = !had && (spacey || LEAF_SPACE_TAGS.contains(&opened.as_str()));
        if leaf_space {
            self.parts.push(" ".into());
            had = true;
        }
        if had {
            if let Some(parent) = self.had_data_stack.last_mut() {
                *parent = true;
            }
        }
    }

    fn data(&mut self, data: &str) {
        if self.skip > 0 || data.is_empty() {
            return;
        }
        let mut data = data.to_string();
        if data.trim_matches([' ', '\t', '\n', '\r', '\u{00a0}', '\u{202f}']).is_empty() {
            if data.contains('\n') || data.contains('\r') {
                return;
            }
            data = " ".into();
        }
        if let Some(had) = self.had_data_stack.last_mut() {
            *had = true;
        }
        self.parts.push(data);
    }
}

fn attr_blob(attrs: &[(String, String)]) -> String {
    let mut class = String::new();
    let mut id = String::new();
    let mut dtype = String::new();
    let mut dkind = String::new();
    for (k, v) in attrs {
        match k.to_ascii_lowercase().as_str() {
            "class" => class = v.clone(),
            "id" => id = v.clone(),
            "data-type" => dtype = v.clone(),
            "data-kind" => dkind = v.clone(),
            _ => {}
        }
    }
    format!("{class} {id} {dtype} {dkind}").to_ascii_lowercase()
}

fn decode_entities(raw: &str) -> String {
    let mut out = String::new();
    let mut chars = raw.chars().peekable();
    while let Some(c) = chars.next() {
        if c != '&' {
            out.push(c);
            continue;
        }
        let mut ent = String::from("&");
        while let Some(&n) = chars.peek() {
            ent.push(n);
            chars.next();
            if n == ';' {
                break;
            }
            if ent.len() > 12 {
                break;
            }
        }
        match ent.as_str() {
            "&nbsp;" => out.push('\u{00a0}'),
            "&amp;" => out.push('&'),
            "&lt;" => out.push('<'),
            "&gt;" => out.push('>'),
            "&quot;" => out.push('"'),
            other if other.starts_with("&#x") || other.starts_with("&#X") => {
                let hex = other.trim_start_matches("&#x").trim_start_matches("&#X").trim_end_matches(';');
                if let Ok(cp) = u32::from_str_radix(hex, 16) {
                    if let Some(ch) = char::from_u32(cp) {
                        out.push(ch);
                        continue;
                    }
                }
                out.push_str(other);
            }
            other if other.starts_with("&#") => {
                let num = other.trim_start_matches("&#").trim_end_matches(';');
                if let Ok(cp) = num.parse::<u32>() {
                    if let Some(ch) = char::from_u32(cp) {
                        out.push(ch);
                        continue;
                    }
                }
                out.push_str(other);
            }
            other => out.push_str(other),
        }
    }
    out
}

fn parse_attrs(inside: &str) -> (String, Vec<(String, String)>) {
    let inside = inside.trim();
    let mut parts = inside.splitn(2, char::is_whitespace);
    let tag = parts.next().unwrap_or("").to_ascii_lowercase();
    let rest = parts.next().unwrap_or("");
    let mut attrs = Vec::new();
    let mut buf = rest.chars().peekable();
    while let Some(c) = buf.peek().copied() {
        if c.is_whitespace() {
            buf.next();
            continue;
        }
        if c == '/' {
            buf.next();
            continue;
        }
        let mut name = String::new();
        while let Some(n) = buf.peek().copied() {
            if n == '=' || n.is_whitespace() || n == '/' {
                break;
            }
            name.push(n);
            buf.next();
        }
        while matches!(buf.peek(), Some(w) if w.is_whitespace()) {
            buf.next();
        }
        let mut value = String::new();
        if buf.peek() == Some(&'=') {
            buf.next();
            while matches!(buf.peek(), Some(w) if w.is_whitespace()) {
                buf.next();
            }
            if let Some(q @ ('"' | '\'')) = buf.peek().copied() {
                buf.next();
                for n in buf.by_ref() {
                    if n == q {
                        break;
                    }
                    value.push(n);
                }
            } else {
                while let Some(n) = buf.peek().copied() {
                    if n.is_whitespace() || n == '/' {
                        break;
                    }
                    value.push(n);
                    buf.next();
                }
            }
        }
        if !name.is_empty() {
            attrs.push((name.to_ascii_lowercase(), decode_entities(&value)));
        }
    }
    (tag, attrs)
}

fn feed_html(html: &str, parser: &mut PromptParser) {
    let mut i = 0;
    let chars: Vec<char> = html.chars().collect();
    while i < chars.len() {
        if chars[i] == '<' {
            if i + 3 < chars.len() && chars[i + 1] == '!' && chars[i + 2] == '-' && chars[i + 3] == '-' {
                i += 4;
                while i + 2 < chars.len() && !(chars[i] == '-' && chars[i + 1] == '-' && chars[i + 2] == '>') {
                    i += 1;
                }
                i = (i + 3).min(chars.len());
                continue;
            }
            let start = i + 1;
            i += 1;
            while i < chars.len() && chars[i] != '>' {
                i += 1;
            }
            let inner: String = chars[start..i.min(chars.len())].iter().collect();
            if i < chars.len() {
                i += 1;
            }
            let self_close = inner.trim_end().ends_with('/');
            let inner = inner.trim_end_matches('/').trim();
            if let Some(stripped) = inner.strip_prefix('/') {
                parser.end_tag();
                let _ = stripped;
            } else {
                let (tag, attrs) = parse_attrs(inner);
                if tag.starts_with('!') {
                    continue;
                }
                parser.start_tag(&tag, &attrs);
                if self_close {
                    parser.end_tag();
                }
            }
        } else {
            let start = i;
            while i < chars.len() && chars[i] != '<' {
                i += 1;
            }
            let raw: String = chars[start..i].iter().collect();
            parser.data(&decode_entities(&raw));
        }
    }
}

pub fn extract_prompt_from_html(html: &str) -> String {
    let mut parser = PromptParser::default();
    feed_html(html, &mut parser);
    while !parser.tag_stack.is_empty() {
        parser.end_tag();
    }
    normalize_prompt_text(&parser.parts.concat())
}

pub fn root_id(html: &str) -> String {
    let blob = html.trim_start().chars().take(200).collect::<String>().to_ascii_lowercase();
    for key in ["id=\"", "id='"] {
        if let Some(start) = blob.find(key) {
            let from = start + key.len();
            let quote = if key.ends_with('"') { '"' } else { '\'' };
            if let Some(end_rel) = blob[from..].find(quote) {
                if end_rel > 0 {
                    return blob[from..from + end_rel].to_string();
                }
            }
        }
    }
    String::new()
}

pub fn pick_remaining_prompt(htmls: &[String]) -> Result<String, PromptError> {
    let mut todo = Vec::new();
    let mut other = Vec::new();
    for html in htmls {
        let text = extract_prompt_from_html(html);
        if text.is_empty() {
            continue;
        }
        if root_id(html).starts_with("text_todo") {
            todo.push(text);
        } else {
            other.push(text);
        }
    }
    let pool = if todo.is_empty() { other } else { todo };
    pool.into_iter()
        .max_by_key(|s| s.len())
        .ok_or_else(|| PromptError("Tipptext ist leer".into()))
}
