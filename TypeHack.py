#!/usr/bin/env python3
"""TypeHack — typewriter.at helper with a config-rich desktop UI."""

from __future__ import annotations

import ctypes
import json
import os
import random
import sys
import threading
import time
from html.parser import HTMLParser
from pathlib import Path

import updater
from colorama import Fore, Style, init as colorama_init
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

colorama_init(autoreset=True)

def app_dir() -> Path:
    """Writable folder next to the exe (installer) or the source file (dev)."""
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent
    return Path(__file__).resolve().parent


BASE_DIR = app_dir()
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
CONFIG_FILE = BASE_DIR / "config.json"
VERSION = "2.5.0"

PRESET_URLS = {
    "Österreich (at4)": "https://at4.typewriter.at",
    "Deutschland (de4)": "https://de4.typewriter.at",
    "Schweiz (ch4)": "https://ch4.typewriter.at",
    "Benutzerdefiniert": "",
}

DEFAULT_CONFIG = {
    "base_url": "https://at4.typewriter.at",
    "url_preset": "Österreich (at4)",
    "browser": "Auto",
    "remember_login": True,
    "always_on_top": True,
    "open_level_page": True,
    "auto_start": False,
    "type_mode": "char",
    "delay_ms": 50,
    "char_delay_ms": 18,
    "strokes_per_10min": 2000,
    "jitter_pct": 0,
    "burst_chars": 0,
    "login_timeout_s": 180,
    "prompt_timeout_s": 8,
    "theme_accent": "#6ee7b7",
    "auto_update_check": True,
    "auto_install_updates": True,
}

LOGIN_PATH = "/index.php?r=site/login"
LEVEL_PATH = "/index.php?r=typewriter/runLevel"

LOGIN_USER = [
    (By.ID, "LoginForm_username"),
    (By.NAME, "LoginForm[username]"),
    (By.CSS_SELECTOR, "input[name*='username' i]"),
    (By.CSS_SELECTOR, "input[type='email']"),
    (By.CSS_SELECTOR, "input[name*='email' i]"),
    (By.ID, "username"),
]
LOGIN_PASS = [
    (By.ID, "LoginForm_pw"),
    (By.ID, "LoginForm_password"),
    (By.NAME, "LoginForm[password]"),
    (By.NAME, "LoginForm[pw]"),
    (By.CSS_SELECTOR, "input[type='password']"),
]
LOGIN_SUBMIT = [
    (By.ID, "login-submit-btn"),
    (By.CSS_SELECTOR, "#login-form input[type='submit']"),
    (By.CSS_SELECTOR, "input[type='submit'][value='Login']"),
    (By.CSS_SELECTOR, "button[type='submit']"),
]
OVERLAY_CLICK = [
    (By.CSS_SELECTOR, "button.fc-cta-consent"),
    (By.CSS_SELECTOR, "button[aria-label='Consent']"),
    (By.CSS_SELECTOR, "button.fc-data-preferences-accept-all"),
    (By.CSS_SELECTOR, "button[aria-label='Accept all']"),
    (By.XPATH, "//button[normalize-space()='Consent' or normalize-space()='Zustimmen' or contains(., 'Alle akzeptieren') or contains(., 'Accept all')]"),
]
CAPTCHA_CLICK = [
    (By.CSS_SELECTOR, "#chal-form button"),
    (By.CSS_SELECTOR, "form#chal-form button"),
    (By.CSS_SELECTOR, ".altcha, .altcha-checkbox, button.altcha"),
    (By.CSS_SELECTOR, "#altcha"),
    (By.CSS_SELECTOR, "input[name='altcha']"),
    (By.XPATH, "//button[contains(., 'Roboter') or contains(., 'Captcha') or contains(., 'Verify') or contains(., 'Mensch')]"),
    (By.CSS_SELECTOR, "label:has(input[type='checkbox'])"),
]
PROMPT_SELECTORS = [
    (By.ID, "text_todo_1"),
    (By.CSS_SELECTOR, "[id^='text_todo']"),
    (By.ID, "text_todo"),
    (By.CSS_SELECTOR, "#typewriter-text"),
    (By.CSS_SELECTOR, ".typewriter-text"),
    (By.CSS_SELECTOR, "#textToType"),
    (By.CSS_SELECTOR, "#tw-text"),
    (By.CSS_SELECTOR, "#twText"),
    (By.CSS_SELECTOR, ".tw-text"),
    (By.CSS_SELECTOR, ".typewriter-line"),
    (By.CSS_SELECTOR, ".current-line"),
    (By.CSS_SELECTOR, "[data-prompt]"),
    (By.CSS_SELECTOR, ".letter, .char, span.letter, span.char"),
]
START_CLICK = [
    (By.CSS_SELECTOR, ".ui-dialog-buttonset button"),
    (By.CSS_SELECTOR, ".ui-dialog-buttonset .ui-button"),
    (By.CSS_SELECTOR, "div.ui-dialog button"),
    (By.CLASS_NAME, "cockpitStartButton"),
    (By.CSS_SELECTOR, "a.cockpitStartButton, button.cockpitStartButton"),
    (By.XPATH, "//button[contains(., 'OK') or contains(., 'Start') or contains(., 'Weiter') or contains(., 'Begin') or contains(., 'Los') or contains(., 'Übung')]"),
    (By.XPATH, "//span[contains(@class,'ui-button-text') and (contains(.,'OK') or contains(.,'Start') or contains(.,'Weiter') or contains(.,'Los'))]"),
]
WRITE_CLICK = [
    (By.CLASS_NAME, "cockpitStartButton"),
    (By.CSS_SELECTOR, "a.cockpitStartButton, button.cockpitStartButton"),
    (By.CSS_SELECTOR, "a[href*='generateLevel'], a[href*='runLevel']"),
    (By.XPATH, "//a[contains(., 'Schreiben') and not(contains(., 'Abmelden'))]"),
    (By.XPATH, "//a[contains(@href,'typewriter/generateLevel') or contains(@href,'typewriter/runLevel')]"),
]

PALETTE = {
    "bg": "#0b0d12",
    "panel": "#12151c",
    "card": "#1a1f29",
    "line": "#2a3140",
    "text": "#f4f4f5",
    "muted": "#9aa3b2",
    "accent": "#6ee7b7",
    "accent2": "#7dd3fc",
    "danger": "#fb7185",
    "warn": "#fbbf24",
}


def merge_config(raw: dict | None) -> dict:
    cfg = dict(DEFAULT_CONFIG)
    if isinstance(raw, dict):
        for key, value in raw.items():
            if key in cfg:
                cfg[key] = value
    return cfg


def load_config(path: Path = CONFIG_FILE) -> dict:
    try:
        return merge_config(json.loads(path.read_text(encoding="utf-8")))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return merge_config(None)


def save_config(cfg: dict, path: Path = CONFIG_FILE) -> None:
    path.write_text(json.dumps(merge_config(cfg), indent=2), encoding="utf-8")


def load_credentials(path: Path = CREDENTIALS_FILE) -> tuple[str | None, str | None]:
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (FileNotFoundError, json.JSONDecodeError, OSError):
        return None, None
    email = str(data.get("email") or "").strip() or None
    password = str(data.get("password") or "") or None
    return email, password


def save_credentials(email: str, password: str, path: Path = CREDENTIALS_FILE) -> None:
    path.write_text(json.dumps({"email": email, "password": password}, indent=2), encoding="utf-8")


def clamp_strokes(n) -> int:
    try:
        value = int(float(n))
    except Exception:
        value = 2000
    return max(200, min(8000, value))


def interval_seconds(cfg: dict) -> float:
    """Seconds between keystrokes from Anschläge / 10 minutes."""
    n = clamp_strokes(cfg.get("strokes_per_10min") or 0)
    base = 600.0 / n
    jitter = max(0.0, min(100.0, float(cfg.get("jitter_pct") or 0))) / 100.0
    factor = 1.0 + random.uniform(-jitter, jitter) if jitter else 1.0
    return max(0.02, base * factor)


def delay_seconds(cfg: dict, *, char: bool = False) -> float:
    if cfg.get("strokes_per_10min"):
        return interval_seconds(cfg)
    base_ms = float(cfg.get("char_delay_ms") if char else cfg.get("delay_ms") or 0)
    jitter = max(0.0, min(100.0, float(cfg.get("jitter_pct") or 0))) / 100.0
    factor = 1.0 + random.uniform(-jitter, jitter) if jitter else 1.0
    return max(0.0, (base_ms / 1000.0) * factor)


def first_present(driver, locators, timeout: float = 2.0):
    end = time.time() + timeout
    while time.time() < end:
        el = first_visible(driver, locators)
        if el is not None:
            return el
        time.sleep(0.12)
    raise TimeoutException("Kein passendes Element gefunden")


def first_visible(driver, locators, *, enabled: bool = False):
    for by, value in locators:
        try:
            for el in driver.find_elements(by, value):
                try:
                    if not el.is_displayed():
                        continue
                    if enabled and not el.is_enabled():
                        continue
                    return el
                except Exception:
                    continue
        except Exception:
            continue
    return None


def dismiss_overlays(driver) -> bool:
    clicked = False
    for by, value in OVERLAY_CLICK:
        try:
            els = driver.find_elements(by, value)
        except Exception:
            continue
        for el in els:
            try:
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    clicked = True
            except Exception:
                continue
    return clicked


def nudge_captcha(driver) -> bool:
    """One cheap click if a captcha control is already there. Never blocks."""
    for by, value in CAPTCHA_CLICK:
        try:
            els = driver.find_elements(by, value)
        except Exception:
            continue
        for el in els:
            try:
                if el.is_displayed():
                    driver.execute_script("arguments[0].click();", el)
                    return True
            except Exception:
                continue
    return False


def fill_input(driver, el, text: str) -> None:
    try:
        el.click()
    except Exception:
        try:
            driver.execute_script("arguments[0].focus();", el)
        except Exception:
            pass
    try:
        el.clear()
        el.send_keys(text)
        if (el.get_attribute("value") or "") == text:
            return
    except Exception:
        pass
    driver.execute_script(
        "var e=arguments[0],v=arguments[1];"
        "e.focus(); e.value=v;"
        "e.dispatchEvent(new Event('input',{bubbles:true}));"
        "e.dispatchEvent(new Event('change',{bubbles:true}));",
        el,
        text,
    )


def logged_in_markers(driver) -> bool:
    if first_visible(driver, LOGIN_PASS):
        return False
    url = driver.current_url or ""
    if "site/login" in url:
        return False
    if any(bit in url for bit in ("runLevel", "practise")):
        return True
    try:
        if driver.find_elements(By.CLASS_NAME, "ui-dialog-buttonset"):
            return True
        if driver.find_elements(By.CSS_SELECTOR, "a[href*='site/logout']"):
            return True
    except Exception:
        pass
    return False


# Spans already accepted/rejected by typewriter.at — never replay these.
_DONE_HINTS = (
    "done",
    "typed",
    "correct",
    "ok",
    "past",
    "completed",
    "right",
    "hit",
    "success",
    "written",
    "already",
    "error",
    "wrong",
    "false",
    "miss",
)
_SPACE_HINTS = ("space", "blank", "gap", "nbsp", "whitespace", "word-sep", "wordsep", "word_sep")
_SKIP_TAGS = {"script", "style", "noscript", "svg"}
# typewriter.at remaining chars are bare <span>s; empty ones are Abstände.
_LEAF_SPACE_TAGS = {"span", "i", "b", "em", "strong", "font"}


def normalize_prompt_text(raw: str) -> str:
    text = raw or ""
    for src in ("\xa0", "\u202f", "\u2002", "\u2003", "\u2009", "\t"):
        text = text.replace(src, " ")
    return text.replace("\n", "").replace("\r", "")


def keys_for_char(ch: str):
    """Glyph identity (layout-independent). Space is the character ' ', not a scan code."""
    if ch in (" ", "\xa0", "\u202f", "\u2009"):
        return " "
    if ch in ("\n", "\r"):
        return "\n"
    return ch


def _attr_blob(attrs) -> str:
    data = {str(k).lower(): str(v or "") for k, v in attrs}
    return f"{data.get('class', '')} {data.get('id', '')} {data.get('data-type', '')} {data.get('data-kind', '')}".lower()


def _token_match(blob: str, hints: tuple[str, ...]) -> bool:
    parts = set(blob.replace("_", "-").replace(",", " ").split())
    for hint in hints:
        for part in parts:
            if part == hint or part.startswith(hint + "-") or part.endswith("-" + hint):
                return True
    return False


class _PromptParser(HTMLParser):
    """Walk typewriter markup → remaining glyphs, including Abstände, skipping completed spans."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self.skip = 0
        self.tag_stack: list[str] = []
        self.spacey_stack: list[bool] = []
        self.had_data_stack: list[bool] = []

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = (tag or "").lower()
        self.tag_stack.append(tag)
        if tag in _SKIP_TAGS:
            self.skip += 1
            self.spacey_stack.append(False)
            self.had_data_stack.append(True)
            return
        blob = _attr_blob(attrs)
        if self.skip or _token_match(blob, _DONE_HINTS):
            self.skip += 1
            self.spacey_stack.append(False)
            self.had_data_stack.append(True)
            return
        spacey = _token_match(blob, _SPACE_HINTS)
        self.spacey_stack.append(spacey)
        self.had_data_stack.append(False)

    def handle_endtag(self, tag: str) -> None:
        if not self.tag_stack:
            return
        opened = self.tag_stack.pop()
        spacey = self.spacey_stack.pop() if self.spacey_stack else False
        had = self.had_data_stack.pop() if self.had_data_stack else False
        if self.skip:
            self.skip = max(0, self.skip - 1)
            return
        leaf_space = (not had) and (spacey or opened in _LEAF_SPACE_TAGS)
        if leaf_space:
            self.parts.append(" ")
            had = True
        if had and self.had_data_stack:
            self.had_data_stack[-1] = True

    def handle_startendtag(self, tag: str, attrs) -> None:
        self.handle_starttag(tag, attrs)
        self.handle_endtag(tag)

    def handle_data(self, data: str) -> None:
        if self.skip or not data:
            return
        if not data.strip(" \t\n\r\xa0\u202f"):
            # Pretty-printed markup inserts "\n  " between spans — not a typed Abstand.
            if "\n" in data or "\r" in data:
                return
            data = " "
        if self.had_data_stack:
            self.had_data_stack[-1] = True
        self.parts.append(data)


def extract_prompt_from_html(html: str) -> str:
    """Remaining typeable text from a typewriter fragment. Spaces count; done spans do not."""
    parser = _PromptParser()
    parser.feed(html or "")
    parser.close()
    return normalize_prompt_text("".join(parser.parts))


def _root_id(html: str) -> str:
    blob = (html or "").lstrip()[:200].lower()
    for key in ('id="', "id='"):
        start = blob.find(key)
        if start < 0:
            continue
        start += len(key)
        quote = '"' if key.endswith('"') else "'"
        end = blob.find(quote, start)
        if end > start:
            return blob[start:end]
    return ""


def pick_remaining_prompt(htmls: list[str]) -> str:
    """Choose the real remaining line. Prefer #text_todo_*; empty wrappers lose; space-only is valid."""
    todo: list[str] = []
    other: list[str] = []
    for html in htmls:
        text = extract_prompt_from_html(html)
        if text == "":
            continue
        if _root_id(html).startswith("text_todo"):
            todo.append(text)
        else:
            other.append(text)
    pool = todo or other
    if not pool:
        raise TimeoutException("Tipptext ist leer")
    return max(pool, key=len)


def glyphs_to_type(text: str) -> list[str]:
    """One list entry per keystroke, layout-independent glyph identity."""
    return [keys_for_char(ch) for ch in normalize_prompt_text(text)]


def glyph_payload(ch: str) -> dict:
    """CDP/key event for this glyph. Identity is `text`, never a physical KeyY/KeyZ code."""
    glyph = keys_for_char(ch)
    if glyph == " ":
        return {"glyph": " ", "key": " ", "code": "Space", "vk": 32, "text": " ", "insert_text": " "}
    if glyph == "\n":
        return {"glyph": "\n", "key": "Enter", "code": "Enter", "vk": 13, "text": "\r", "insert_text": "\n"}
    return {
        "glyph": glyph,
        "key": glyph,
        "code": "",
        "vk": 0,
        "text": glyph,
        "insert_text": glyph,
    }


def collect_prompt_html(driver) -> list[str]:
    htmls: list[str] = []
    seen: set[str] = set()

    def add(html: str | None) -> None:
        raw = (html or "").strip()
        if not raw or raw in seen:
            return
        seen.add(raw)
        htmls.append(raw)

    for by, value in PROMPT_SELECTORS:
        try:
            els = driver.find_elements(by, value)
        except Exception:
            continue
        for el in els[:30]:
            try:
                add(el.get_attribute("outerHTML"))
            except Exception:
                continue
            el_id = ""
            try:
                el_id = el.get_attribute("id") or ""
            except Exception:
                el_id = ""
            # Parent of #text_todo_1 often also wraps #text_done_* — that would replay typed letters.
            if str(el_id).startswith("text_todo"):
                continue
            try:
                parent = driver.execute_script(
                    "var e=arguments[0]; return e && e.parentElement ? e.parentElement.outerHTML : '';",
                    el,
                )
                add(parent)
            except Exception:
                continue
    return htmls


def prompt_text(driver, timeout: float = 8.0) -> str:
    """Remaining prompt including Abstände. Whitespace-only is typeable, not empty."""
    end = time.time() + timeout
    last: Exception | None = None
    while time.time() < end:
        try:
            return pick_remaining_prompt(collect_prompt_html(driver))
        except TimeoutException as exc:
            last = exc
        time.sleep(0.12)
    raise last or TimeoutException("Tipptext ist leer")


def pass_altcha_then_reload(driver) -> bool:
    """Kept for compatibility: never wait, never refresh — that caused the 20s login delay."""
    return nudge_captcha(driver)


def focus_typer(driver) -> None:
    """Focus the hidden typewriter input. Do not click #text_todo_1 — that steals focus."""
    try:
        driver.execute_script(
            "window.focus();"
            "if (typeof setFocusMobileText === 'function') { try { setFocusMobileText(); } catch (x) {} }"
            "var nodes=document.querySelectorAll('input,textarea');"
            "for (var i=0;i<nodes.length;i++){"
            "  var e=nodes[i];"
            "  var id=(e.id||''), name=(e.name||''), tp=(e.type||'').toLowerCase();"
            "  if (tp==='password' || tp==='hidden' || tp==='submit' || tp==='button') continue;"
            "  if (/login|user|email|pass/i.test(id+' '+name)) continue;"
            "  try { e.focus({preventScroll:true}); return id||name||tp; } catch (x) {}"
            "}"
        )
    except Exception:
        pass


# Sticky name of the send method that last moved the remaining prompt.
_PREFERRED_SEND: list[str] = []
SEND_METHODS = ("os", "js", "cdp", "chains")

# Win32 keyboard / window helpers (OS-level keys land even when CDP does not).
ULONG_PTR = ctypes.c_size_t
VK_SPACE = 0x20
VK_RETURN = 0x0D
VK_MENU = 0x12
KEYEVENTF_KEYUP = 0x0002
KEYEVENTF_UNICODE = 0x0004
INPUT_KEYBOARD = 1
SW_RESTORE = 9
SW_SHOW = 5
_JS_SEND_GLYPH = r"""
var ch = arguments[0];
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
    Object.defineProperty(ev, 'charCode', {get: function(){return type === 'keypress' ? which : 0;}});
    Object.defineProperty(ev, 'key', {get: function(){return key;}});
  } catch (e) {}
  target.dispatchEvent(ev);
}
var nodes = [document.activeElement, document.getElementById('text_todo_1'), document.body, document];
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
"""


class _KEYBDINPUT(ctypes.Structure):
    _fields_ = (
        ("wVk", ctypes.c_ushort),
        ("wScan", ctypes.c_ushort),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    )


class _MOUSEINPUT(ctypes.Structure):
    _fields_ = (
        ("dx", ctypes.c_long),
        ("dy", ctypes.c_long),
        ("mouseData", ctypes.c_ulong),
        ("dwFlags", ctypes.c_ulong),
        ("time", ctypes.c_ulong),
        ("dwExtraInfo", ULONG_PTR),
    )


class _HARDWAREINPUT(ctypes.Structure):
    _fields_ = (
        ("uMsg", ctypes.c_ulong),
        ("wParamL", ctypes.c_ushort),
        ("wParamH", ctypes.c_ushort),
    )


class _INPUT(ctypes.Structure):
    class _U(ctypes.Union):
        _fields_ = (("ki", _KEYBDINPUT), ("mi", _MOUSEINPUT), ("hi", _HARDWAREINPUT))

    _anonymous_ = ("u",)
    _fields_ = (("type", ctypes.c_ulong), ("u", _U))


def preferred_send() -> str | None:
    return _PREFERRED_SEND[0] if _PREFERRED_SEND else None


def remember_send(name: str | None) -> None:
    _PREFERRED_SEND.clear()
    if name:
        _PREFERRED_SEND.append(name)


def remaining_prompt_now(driver) -> str | None:
    """Current remaining prompt, or None if it cannot be read yet."""
    try:
        return pick_remaining_prompt(collect_prompt_html(driver))
    except Exception:
        return None


def first_remaining_glyph(text: str) -> str:
    glyphs = glyphs_to_type(text)
    if not glyphs:
        raise TimeoutException("Tipptext ist leer")
    return glyphs[0]


def _send_input(inputs: list[_INPUT]) -> None:
    if not inputs or os.name != "nt":
        raise OSError("SendInput nur unter Windows")
    arr = (_INPUT * len(inputs))(*inputs)
    sent = ctypes.windll.user32.SendInput(len(inputs), ctypes.byref(arr), ctypes.sizeof(_INPUT))
    if sent != len(inputs):
        raise OSError(f"SendInput {sent}/{len(inputs)}")


def _vk_down(vk: int) -> None:
    # keybd_event reaches Chromium; SendInput often does not (UIPI / focus).
    ctypes.windll.user32.keybd_event(vk, 0, 0, 0)


def _vk_up(vk: int) -> None:
    ctypes.windll.user32.keybd_event(vk, 0, KEYEVENTF_KEYUP, 0)


def _vk_tap(vk: int) -> None:
    _vk_down(vk)
    _vk_up(vk)


def _unicode_tap(ch: str) -> None:
    code = ord(ch)
    down = _INPUT(type=INPUT_KEYBOARD, ki=_KEYBDINPUT(0, code, KEYEVENTF_UNICODE, 0, 0))
    up = _INPUT(type=INPUT_KEYBOARD, ki=_KEYBDINPUT(0, code, KEYEVENTF_UNICODE | KEYEVENTF_KEYUP, 0, 0))
    _send_input([down, up])


def os_send_glyph(ch: str) -> None:
    """Real OS keystroke into the foreground window (the Edge/Chrome lesson)."""
    ch = keys_for_char(ch)
    if os.name != "nt":
        raise OSError("OS-Tasten nur unter Windows")
    if ch == " ":
        _vk_tap(VK_SPACE)
        return
    if ch == "\n":
        _vk_tap(VK_RETURN)
        return
    scan = ctypes.windll.user32.VkKeyScanW(ord(ch))
    if scan == -1 or scan == 0xFFFF:
        _unicode_tap(ch)
        return
    vk = scan & 0xFF
    shift = bool(scan & 0x100)
    ctrl = bool(scan & 0x200)
    alt = bool(scan & 0x400)
    if shift:
        _vk_down(0x10)
    if ctrl:
        _vk_down(0x11)
    if alt:
        _vk_down(0x12)
    _vk_tap(vk)
    if alt:
        _vk_up(0x12)
    if ctrl:
        _vk_up(0x11)
    if shift:
        _vk_up(0x10)


def _window_title(hwnd: int) -> str:
    n = ctypes.windll.user32.GetWindowTextLengthW(hwnd) + 1
    buf = ctypes.create_unicode_buffer(n)
    ctypes.windll.user32.GetWindowTextW(hwnd, buf, n)
    return buf.value


def _window_class(hwnd: int) -> str:
    buf = ctypes.create_unicode_buffer(256)
    ctypes.windll.user32.GetClassNameW(hwnd, buf, 256)
    return buf.value


def chrome_hwnds() -> list[int]:
    found: list[int] = []
    if os.name != "nt":
        return found

    @ctypes.WINFUNCTYPE(ctypes.c_int, ctypes.c_void_p, ctypes.c_ssize_t)
    def cb(hwnd, _lparam):
        if not ctypes.windll.user32.IsWindowVisible(hwnd):
            return 1
        cls = _window_class(hwnd)
        if cls != "Chrome_WidgetWin_1":
            return 1
        title = _window_title(hwnd)
        if not title or title.lower() == "typehack":
            return 1
        found.append(int(hwnd))
        return 1

    ctypes.windll.user32.EnumWindows(cb, 0)
    return found


def pick_browser_hwnd(driver=None) -> int | None:
    hwnds = chrome_hwnds()
    if not hwnds:
        return None
    needle = ""
    try:
        needle = ((driver.title if driver is not None else "") or "").strip().lower()
    except Exception:
        needle = ""
    scored: list[tuple[int, int]] = []
    skip = ("discord", "nzxt", "kennwort", "password", "spotify", "slack", "teams", "vscode", "cursor")
    for hwnd in hwnds:
        title = _window_title(hwnd).lower()
        if any(bit in title for bit in skip):
            continue
        score = 0
        if "typewriter" in title:
            score += 12
        if needle and needle[:24] in title:
            score += 8
        if "microsoft edge" in title or "google chrome" in title:
            score += 3
        if "data:;," in title or title.startswith("data:"):
            score -= 5
        scored.append((score, hwnd))
    if not scored:
        return None
    scored.sort(reverse=True)
    return scored[0][1]


def force_foreground(hwnd: int) -> bool:
    """Bring hwnd to the front without injecting Alt into the page."""
    if not hwnd or os.name != "nt":
        return False
    user32 = ctypes.windll.user32
    kernel32 = ctypes.windll.kernel32
    user32.ShowWindow(hwnd, SW_RESTORE)
    user32.ShowWindow(hwnd, SW_SHOW)
    if user32.GetForegroundWindow() == hwnd:
        return True
    fg = user32.GetForegroundWindow()
    fg_thread = user32.GetWindowThreadProcessId(fg, None)
    cur_thread = kernel32.GetCurrentThreadId()
    attached = False
    if fg_thread and cur_thread and fg_thread != cur_thread:
        attached = bool(user32.AttachThreadInput(cur_thread, fg_thread, True))
    user32.BringWindowToTop(hwnd)
    ok = bool(user32.SetForegroundWindow(hwnd))
    if attached:
        user32.AttachThreadInput(cur_thread, fg_thread, False)
    return ok or user32.GetForegroundWindow() == hwnd


def foreground_browser(driver) -> bool:
    """Put the Selenium Edge/Chrome window in front so OS keystrokes hit the lesson."""
    try:
        driver.switch_to.window(driver.current_window_handle)
    except Exception:
        pass
    try:
        driver.execute_script("window.focus();")
    except Exception:
        pass
    hwnd = pick_browser_hwnd(driver)
    if hwnd:
        return force_foreground(hwnd)
    return False


def js_send_glyph(driver, glyph: str) -> None:
    driver.execute_script(_JS_SEND_GLYPH, keys_for_char(glyph))


def cdp_send_glyph(driver, glyph: str) -> None:
    info = glyph_payload(glyph)
    vk = int(info.get("vk") or 0)
    if info["glyph"] == " ":
        vk = VK_SPACE
    common = {
        "key": info["key"],
        "code": info["code"] or ("Space" if info["glyph"] == " " else ""),
        "windowsVirtualKeyCode": vk,
        "nativeVirtualKeyCode": vk,
        "text": info["text"],
        "unmodifiedText": info["text"],
    }
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {**common, "type": "keyDown"})
    if info["text"]:
        driver.execute_cdp_cmd(
            "Input.dispatchKeyEvent",
            {"type": "char", "key": info["key"], "text": info["text"], "unmodifiedText": info["text"]},
        )
    driver.execute_cdp_cmd("Input.dispatchKeyEvent", {**common, "type": "keyUp"})


def chains_send_glyph(driver, glyph: str) -> None:
    from selenium.webdriver.common.action_chains import ActionChains

    ActionChains(driver).send_keys(keys_for_char(glyph)).perform()


def _dispatch_glyph(driver, glyph: str, method: str) -> None:
    if method == "os":
        os_send_glyph(glyph)
    elif method == "js":
        js_send_glyph(driver, glyph)
    elif method == "cdp":
        cdp_send_glyph(driver, glyph)
    elif method == "chains":
        chains_send_glyph(driver, glyph)
    else:
        raise ValueError(method)


def _click_first(driver, locators) -> bool:
    for by, value in locators:
        try:
            els = driver.find_elements(by, value)
        except Exception:
            continue
        for el in els:
            try:
                if not el.is_displayed():
                    continue
                href = (el.get_attribute("href") or "").lower()
                text = (el.text or "").lower()
                if "logout" in href or "abmelden" in text or "site/logout" in href:
                    continue
                try:
                    el.click()
                except Exception:
                    driver.execute_script("arguments[0].click();", el)
                return True
            except Exception:
                continue
    return False


def open_write_mode(driver, base: str | None = None) -> bool:
    """From the overview, open Schreiben / generateLevel so #text_todo_1 exists."""
    if remaining_prompt_now(driver):
        return True
    if _click_first(driver, WRITE_CLICK):
        time.sleep(0.6)
        if remaining_prompt_now(driver):
            return True
    if base:
        for path in ("/index.php?r=typewriter/generateLevel", LEVEL_PATH):
            try:
                driver.get(base.rstrip("/") + path)
                time.sleep(0.5)
            except Exception:
                continue
            if remaining_prompt_now(driver):
                return True
    return remaining_prompt_now(driver) is not None


def arm_lesson(driver, base: str | None = None) -> bool:
    """Open Schreibmodus, click start/OK dialogs, send Enter so the lesson hears keys."""
    opened = open_write_mode(driver, base)
    clicked = _click_first(driver, START_CLICK)
    focus_typer(driver)
    try:
        os_send_glyph("\n")
    except Exception:
        try:
            chains_send_glyph(driver, "\n")
        except Exception:
            pass
    return opened or clicked


def send_glyph(driver, glyph: str, *, method: str | None = None) -> str:
    """Deliver one remaining glyph. Default: OS key into the focused browser, then JS/CDP/chains."""
    glyph = keys_for_char(glyph)
    focus_typer(driver)
    order: list[str] = []
    if method:
        order = [method]
    else:
        pref = preferred_send()
        order = list(SEND_METHODS)
        if pref in order:
            order.remove(pref)
            order.insert(0, pref)
    last_error: Exception | None = None
    for name in order:
        try:
            _dispatch_glyph(driver, glyph, name)
            remember_send(name)
            return name
        except Exception as exc:
            last_error = exc
            continue
    if last_error:
        raise last_error
    raise RuntimeError("kein Tipp-Verfahren")


def send_glyph_verified(driver, glyph: str, before: str, *, settle_s: float = 0.12) -> str | None:
    """Try send methods until the remaining prompt actually changes."""
    glyph = keys_for_char(glyph)
    methods: list[str] = []
    pref = preferred_send()
    if pref:
        methods.append(pref)
    for name in SEND_METHODS:
        if name not in methods:
            methods.append(name)
    for name in methods:
        try:
            send_glyph(driver, glyph, method=name)
        except Exception:
            continue
        time.sleep(max(0.0, settle_s))
        after = remaining_prompt_now(driver)
        if after is None:
            remember_send(name)
            return name
        if after != before:
            remember_send(name)
            return name
    return None


CAPTCHA_RELOAD_S = 2.0
_CAPTCHA_MARKERS = (
    "sicherheitsprüfung",
    "sicherheitspruefung",
    "chal-form",
    "id=\"chal-form\"",
    "altcha",
    "i'm not a robot",
    "ich bin kein roboter",
    "einen moment bitte",
    "/_chal/",
    "verification failed",
)


def is_captcha_view(html: str, url: str = "") -> bool:
    """True only for the challenge screen — not login, not the lesson."""
    blob = f"{url}\n{html}".lower()
    if "loginform" in blob or "login-form" in blob or 'id="text_todo' in blob or "id='text_todo" in blob:
        return False
    return any(marker in blob for marker in _CAPTCHA_MARKERS)


def should_reload_captcha(*, captcha: bool, elapsed_s: float, threshold_s: float = CAPTCHA_RELOAD_S) -> bool:
    return bool(captcha) and float(elapsed_s) >= float(threshold_s)


def maybe_reload_stuck_captcha(driver, seen_since: float | None, now: float | None = None) -> float | None:
    """If the captcha/challenge view has been up for 2s, refresh the tab. Returns new seen_since."""
    now = time.time() if now is None else now
    try:
        url = driver.current_url or ""
        html = driver.page_source or ""
    except Exception:
        return seen_since
    if not is_captcha_view(html, url):
        return None
    if seen_since is None:
        return now
    if not should_reload_captcha(captcha=True, elapsed_s=now - seen_since):
        return seen_since
    driver.refresh()
    return now


def type_char(driver, ch: str) -> None:
    """One remaining glyph as a real character. Layout-independent: send the glyph, not KeyY/KeyZ."""
    send_glyph(driver, keys_for_char(ch))


def _stealth(options) -> None:
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_argument("--remote-allow-origins=*")
    options.add_argument("--no-first-run")
    options.add_argument("--disable-popup-blocking")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)


def _first_existing(*paths: str) -> str | None:
    for path in paths:
        if Path(path).is_file():
            return path
    return None


def build_edge():
    options = EdgeOptions()
    binary = _first_existing(
        r"C:\Program Files (x86)\Microsoft\Edge\Application\msedge.exe",
        r"C:\Program Files\Microsoft\Edge\Application\msedge.exe",
    )
    if binary:
        options.binary_location = binary
    _stealth(options)
    return webdriver.Edge(options=options)


def build_chrome():
    options = ChromeOptions()
    binary = _first_existing(
        r"C:\Program Files\Google\Chrome\Application\chrome.exe",
        r"C:\Program Files (x86)\Google\Chrome\Application\chrome.exe",
    )
    if binary:
        options.binary_location = binary
    _stealth(options)
    return webdriver.Chrome(options=options)


def create_driver(browser: str = "Auto"):
    order = {
        "Edge": [(build_edge, "Edge")],
        "Chrome": [(build_chrome, "Chrome")],
        "Auto": [(build_edge, "Edge"), (build_chrome, "Chrome")],
    }.get(browser, [(build_edge, "Edge"), (build_chrome, "Chrome")])
    errors = []
    for factory, name in order:
        try:
            print(f"Starte {name} (Selenium Manager)…")
            return factory()
        except WebDriverException as exc:
            errors.append(f"{name}: {exc}")
            print(f"{name} fehlgeschlagen: {exc}")
    raise WebDriverException("Kein Browser startbar:\n" + "\n".join(errors))


class TypeHackApp:
    def __init__(self) -> None:
        self.cfg = load_config()
        self.root = None
        self.stop_flag = threading.Event()
        self.typing = False
        self.connected = False
        self.driver = None
        self.vars: dict = {}

    def create_widgets(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.tk = tk
        self.cfg = load_config()
        accent = str(self.cfg.get("theme_accent") or PALETTE["accent"])
        self.root = tk.Tk()
        self.root.title("TypeHack")
        self.root.geometry("420x620")
        self.root.minsize(380, 520)
        self.root.configure(bg=PALETTE["bg"])

        style = ttk.Style(self.root)
        style.theme_use("clam")
        style.configure("TFrame", background=PALETTE["bg"])
        style.configure("Card.TFrame", background=PALETTE["card"])
        style.configure("Panel.TFrame", background=PALETTE["panel"])
        style.configure("TLabel", background=PALETTE["card"], foreground=PALETTE["text"], font=("Segoe UI", 10))
        style.configure("Muted.TLabel", background=PALETTE["card"], foreground=PALETTE["muted"], font=("Segoe UI", 9))
        style.configure("Title.TLabel", background=PALETTE["panel"], foreground=PALETTE["text"], font=("Segoe UI", 18, "bold"))
        style.configure("Sub.TLabel", background=PALETTE["panel"], foreground=PALETTE["muted"], font=("Segoe UI", 10))
        style.configure("Accent.TLabel", background=PALETTE["panel"], foreground=accent, font=("Segoe UI", 10, "bold"))
        style.configure("TCheckbutton", background=PALETTE["card"], foreground=PALETTE["text"], font=("Segoe UI", 10))
        style.configure("TCombobox", fieldbackground=PALETTE["panel"], background=PALETTE["panel"], foreground=PALETTE["text"])
        style.configure("Horizontal.TScale", background=PALETTE["card"], troughcolor=PALETTE["line"])
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=8)
        style.map(
            "Primary.TButton",
            background=[("!disabled", accent), ("disabled", PALETTE["line"])],
            foreground=[("!disabled", "#052e1c")],
        )
        style.configure("Ghost.TButton", font=("Segoe UI", 10), padding=6)
        style.configure("Danger.TButton", font=("Segoe UI", 10, "bold"), padding=6)
        style.map("Danger.TButton", background=[("!disabled", PALETTE["danger"])], foreground=[("!disabled", "#1a0508")])

        canvas = tk.Canvas(self.root, bg=PALETTE["bg"], highlightthickness=0, bd=0)
        scroll = ttk.Scrollbar(self.root, orient="vertical", command=canvas.yview)
        inner = ttk.Frame(canvas, style="Card.TFrame")
        inner.bind("<Configure>", lambda e: canvas.configure(scrollregion=canvas.bbox("all")))
        win = canvas.create_window((0, 0), window=inner, anchor="nw")
        canvas.configure(yscrollcommand=scroll.set)

        def _stretch(event):
            canvas.itemconfigure(win, width=event.width)

        canvas.bind("<Configure>", _stretch)

        def _wheel(event):
            delta = -1 if event.delta > 0 else 1
            if getattr(event, "num", None) == 4:
                delta = -1
            if getattr(event, "num", None) == 5:
                delta = 1
            canvas.yview_scroll(delta, "units")

        canvas.bind_all("<MouseWheel>", _wheel)
        canvas.bind_all("<Button-4>", _wheel)
        canvas.bind_all("<Button-5>", _wheel)
        canvas.pack(side="left", fill="both", expand=True)
        scroll.pack(side="right", fill="y")

        pad = {"padx": 16, "pady": 4}
        header = ttk.Frame(inner, style="Panel.TFrame")
        header.pack(fill="x", padx=12, pady=(12, 8))
        ttk.Label(header, text="TypeHack", style="Title.TLabel").pack(side="left")
        self.badge = ttk.Label(header, text="● getrennt", style="Accent.TLabel")
        self.badge.pack(side="right")

        self.vars["email"] = tk.StringVar(value=load_credentials()[0] or "")
        self.vars["password"] = tk.StringVar(value=load_credentials()[1] or "")
        self.vars["remember_login"] = tk.BooleanVar(value=True)
        self.vars["url_preset"] = tk.StringVar(value=self.cfg.get("url_preset") or "Österreich (at4)")
        self.vars["base_url"] = tk.StringVar(value=self.cfg.get("base_url") or DEFAULT_CONFIG["base_url"])
        self.vars["browser"] = tk.StringVar(value=self.cfg.get("browser") or "Auto")
        self.vars["always_on_top"] = tk.BooleanVar(value=bool(self.cfg.get("always_on_top", True)))
        self.vars["open_level_page"] = tk.BooleanVar(value=True)
        self.vars["auto_start"] = tk.BooleanVar(value=False)
        self.vars["type_mode"] = tk.StringVar(value="char")
        self.vars["delay_ms"] = tk.DoubleVar(value=50)
        self.vars["char_delay_ms"] = tk.DoubleVar(value=float(self.cfg.get("char_delay_ms") or 18))
        self.vars["strokes_per_10min"] = tk.IntVar(value=clamp_strokes(self.cfg.get("strokes_per_10min") or 2000))
        self.vars["jitter_pct"] = tk.DoubleVar(value=0)
        self.vars["burst_chars"] = tk.IntVar(value=0)
        self.vars["login_timeout_s"] = tk.IntVar(value=180)
        self.vars["prompt_timeout_s"] = tk.IntVar(value=8)
        self.vars["auto_update_check"] = tk.BooleanVar(value=True)
        self.vars["auto_install_updates"] = tk.BooleanVar(value=True)

        self._labeled_entry(inner, "E-Mail", self.vars["email"])
        self._labeled_entry(inner, "Passwort", self.vars["password"], show="•")
        ttk.Label(inner, text="Server", style="Muted.TLabel").pack(anchor="w", padx=16)
        preset = ttk.Combobox(inner, textvariable=self.vars["url_preset"], values=list(PRESET_URLS), state="readonly")
        preset.pack(fill="x", padx=16, pady=(0, 6))
        preset.bind("<<ComboboxSelected>>", self._on_preset)

        ttk.Label(inner, text="Anschläge / 10 Minuten", style="Muted.TLabel").pack(anchor="w", padx=16)
        pace = ttk.Frame(inner, style="Card.TFrame")
        pace.pack(fill="x", padx=16, pady=(0, 2))
        self.strokes_entry = tk.Entry(
            pace,
            textvariable=self.vars["strokes_per_10min"],
            width=7,
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
            justify="center",
        )
        self.strokes_entry.pack(side="left")
        ttk.Scale(
            pace,
            from_=400,
            to=5000,
            variable=self.vars["strokes_per_10min"],
            orient="horizontal",
        ).pack(side="left", fill="x", expand=True, padx=(8, 0))
        self.pace_label = ttk.Label(inner, text="", style="Muted.TLabel")
        self.pace_label.pack(anchor="w", padx=16, pady=(0, 4))

        def _pace(*_a):
            try:
                n = clamp_strokes(self.vars["strokes_per_10min"].get())
            except Exception:
                return
            per_s = n / 600.0
            ms = int(round(600000 / n))
            self.pace_label.config(text=f"≈ {per_s:.2f} Anschläge/s  ·  {ms} ms Abstand")

        self.vars["strokes_per_10min"].trace_add("write", _pace)
        _pace()

        self.preview = tk.Label(
            inner,
            text="Verbinden → Captcha lösen → Login startet sofort → Level wählen → Start.",
            wraplength=360,
            justify="left",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=("Segoe UI", 11),
            padx=12,
            pady=12,
            anchor="nw",
        )
        self.preview.pack(fill="x", padx=16, pady=8)

        self.status_label = ttk.Label(inner, text="Bereit.", style="Muted.TLabel")
        self.status_label.pack(anchor="w", padx=16)

        btns = ttk.Frame(inner, style="Card.TFrame")
        btns.pack(fill="x", padx=16, pady=10)
        self.connect_button = ttk.Button(btns, text="Verbinden", style="Primary.TButton", command=self.connect)
        self.connect_button.pack(side="left", padx=(0, 6))
        self.start_button = ttk.Button(btns, text="Start", style="Primary.TButton", command=self.toggle_typing, state="disabled")
        self.start_button.pack(side="left", padx=4)
        ttk.Button(btns, text="Stop", style="Ghost.TButton", command=self.stop_typing).pack(side="left", padx=4)
        ttk.Button(btns, text="Beenden", style="Danger.TButton", command=self.quit_callback).pack(side="right")

        self.update_label = ttk.Label(inner, text=f"v{VERSION}  ·  Updates still", style="Muted.TLabel")
        self.update_label.pack(anchor="w", padx=16, pady=(4, 2))
        self.update_progress = ttk.Progressbar(inner, mode="determinate", maximum=100)
        self.update_progress.pack(fill="x", padx=16, pady=(0, 16))

        self.root.protocol("WM_DELETE_WINDOW", self.quit_callback)
        self._apply_topmost()
        if self.cfg.get("auto_update_check", True):
            self.root.after(1800, lambda: self.check_updates(silent=True))

    def _section(self, parent, title: str, bg: str = "card") -> None:
        from tkinter import ttk

        style = "TLabel"
        ttk.Label(parent, text=title.upper(), style=style, foreground=PALETTE["accent2"], font=("Segoe UI", 8, "bold")).pack(
            anchor="w", padx=14, pady=(14, 4)
        )

    def _labeled_entry(self, parent, label: str, var, show: str | None = None) -> None:
        from tkinter import ttk
        import tkinter as tk

        ttk.Label(parent, text=label, style="Muted.TLabel").pack(anchor="w", padx=14)
        entry = tk.Entry(
            parent,
            textvariable=var,
            show=show or "",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            insertbackground=PALETTE["text"],
            relief="flat",
            highlightthickness=1,
            highlightbackground=PALETTE["line"],
        )
        entry.pack(fill="x", padx=14, pady=(0, 6), ipady=5)

    def _slider(self, parent, row: int, label: str, var, frm: float, to: float) -> None:
        from tkinter import ttk

        ttk.Label(parent, text=label, style="Muted.TLabel").grid(row=row, column=0, sticky="w", pady=3)
        ttk.Scale(parent, from_=frm, to=to, variable=var, orient="horizontal", length=220).grid(row=row, column=1, sticky="ew", padx=8)
        val = ttk.Label(parent, text="", width=5)
        val.grid(row=row, column=2, sticky="e")

        def tick(*_a):
            try:
                val.config(text=str(int(float(var.get()))))
            except Exception:
                pass

        var.trace_add("write", tick)
        tick()
        parent.columnconfigure(1, weight=1)

    def _on_preset(self, *_a) -> None:
        name = self.vars["url_preset"].get()
        url = PRESET_URLS.get(name, "")
        if url:
            self.vars["base_url"].set(url)

    def _apply_topmost(self) -> None:
        if self.root:
            self.root.attributes("-topmost", bool(self.vars["always_on_top"].get()))

    def current_config(self) -> dict:
        cfg = merge_config(None)
        cfg.update(
            {
                "base_url": self.vars["base_url"].get().strip() or DEFAULT_CONFIG["base_url"],
                "url_preset": self.vars["url_preset"].get(),
                "browser": self.vars["browser"].get(),
                "remember_login": bool(self.vars["remember_login"].get()),
                "always_on_top": bool(self.vars["always_on_top"].get()),
                "open_level_page": bool(self.vars["open_level_page"].get()),
                "auto_start": bool(self.vars["auto_start"].get()),
                "type_mode": self.vars["type_mode"].get(),
                "delay_ms": float(self.vars["delay_ms"].get()),
                "char_delay_ms": float(self.vars["char_delay_ms"].get()),
                "strokes_per_10min": clamp_strokes(self.vars["strokes_per_10min"].get()),
                "jitter_pct": float(self.vars["jitter_pct"].get()),
                "burst_chars": int(float(self.vars["burst_chars"].get())),
                "login_timeout_s": int(float(self.vars["login_timeout_s"].get())),
                "prompt_timeout_s": int(float(self.vars["prompt_timeout_s"].get())),
                "auto_update_check": bool(self.vars["auto_update_check"].get()),
                "auto_install_updates": bool(self.vars["auto_install_updates"].get()),
            }
        )
        return cfg

    def save_settings(self) -> None:
        cfg = self.current_config()
        save_config(cfg)
        self.cfg = cfg
        if cfg["remember_login"]:
            email = self.vars["email"].get().strip()
            password = self.vars["password"].get()
            if email and password:
                save_credentials(email, password)
        self.set_status("Einstellungen gespeichert.")

    def set_status(self, text: str) -> None:
        if self.root:
            self.root.after(0, lambda: self.status_label.config(text=text))

    def set_badge(self, text: str) -> None:
        if self.root:
            self.root.after(0, lambda: self.badge.config(text=text))

    def check_updates(self, silent: bool = False) -> None:
        if self.typing:
            if not silent:
                self.set_status("Update wartet, bis das Tippen stoppt.")
            return
        threading.Thread(target=self._check_update_worker, args=(silent,), daemon=True).start()

    def _check_update_worker(self, silent: bool) -> None:
        try:
            info = updater.fetch_latest()
        except Exception as exc:
            if not silent:
                self.set_status(f"Update-Check fehlgeschlagen: {exc}")
            return
        if not info or not info.get("version"):
            if not silent:
                self.set_status(f"TypeHack {VERSION} — kein Release gefunden.")
            return
        if not updater.is_newer(str(info["version"]), VERSION):
            if not silent:
                self.set_status(f"TypeHack {VERSION} ist aktuell.")
            if self.update_label:
                self.root.after(0, lambda: self.update_label.config(text=f"Installiert: v{VERSION} (aktuell)"))
            return
        self.root.after(0, lambda: self._offer_update(info, silent))

    def _offer_update(self, info: dict, silent: bool) -> None:
        ver = info.get("version")
        self.update_label.config(text=f"Neu: v{ver}")
        auto = bool(self.vars["auto_install_updates"].get())
        if not auto:
            from tkinter import messagebox

            if not messagebox.askyesno(
                "TypeHack Update",
                f"Version {ver} ist verfügbar (jetzt {VERSION}).\nJetzt herunterladen und installieren?",
            ):
                self.set_status(f"Update {ver} übersprungen.")
                return
        self.set_status(f"Lade TypeHack {ver}…")
        threading.Thread(target=self._download_update_worker, args=(info,), daemon=True).start()

    def _download_update_worker(self, info: dict) -> None:
        def progress(done: int, total: int) -> None:
            pct = int(done * 100 / total) if total else 0
            if self.root:
                self.root.after(0, lambda p=pct: self.update_progress.config(value=p))

        try:
            setup = updater.apply_update(info, progress=progress)
        except Exception as exc:
            self.set_status(f"Update fehlgeschlagen: {exc}")
            return
        exe = Path(sys.executable) if getattr(sys, "frozen", False) else None
        self.set_status("Installer startet…")
        updater.launch_installer(setup, restart_exe=exe)
        if sys.platform.startswith("win"):
            self.root.after(400, self.quit_callback)

    def connect(self) -> None:
        if self.connected:
            self.set_status("Schon verbunden.")
            return
        email = self.vars["email"].get().strip()
        password = self.vars["password"].get()
        if not email or not password:
            self.set_status("E-Mail und Passwort eintragen.")
            return
        self.save_settings()
        self.connect_button.config(state="disabled")
        self.set_status("Starte Browser… Captcha lösen, Login kommt sofort danach.")
        threading.Thread(target=self._connect_worker, args=(email, password), daemon=True).start()

    def _connect_worker(self, email: str, password: str) -> None:
        try:
            self.driver = create_driver(self.cfg.get("browser") or "Auto")
            try:
                self.driver.maximize_window()
            except Exception:
                pass
            self.login(email, password)
            self.connected = True
            self.set_badge("●  verbunden")
            self.set_status("Verbunden. Level wählen, dann Schreibmodus / Start Typing.")
            if self.root:
                self.root.after(0, lambda: self.start_button.config(state="normal"))
                self.root.after(0, lambda: self.connect_button.config(text="Verbunden", state="disabled"))
            if self.cfg.get("auto_start"):
                self.root.after(800, self.toggle_typing)
        except Exception as exc:
            self.set_status(f"Verbindung fehlgeschlagen: {exc}")
            if self.root:
                self.root.after(0, lambda: self.connect_button.config(state="normal"))
            if self.driver:
                try:
                    self.driver.quit()
                except Exception:
                    pass
                self.driver = None

    def _set_topmost(self, value: bool) -> None:
        def apply() -> None:
            try:
                if self.root:
                    self.root.attributes("-topmost", bool(value))
            except Exception:
                pass

        if not self.root:
            return
        try:
            if threading.current_thread() is threading.main_thread():
                apply()
            else:
                self.root.after(0, apply)
        except Exception:
            pass

    def toggle_typing(self) -> None:
        if self.typing:
            self.stop_typing()
            return
        if not self.driver:
            self.set_status("Zuerst verbinden.")
            return
        self.stop_flag.clear()
        self.typing = True
        remember_send(None)
        self._set_topmost(False)
        self.start_button.config(text="Stop Typing")
        self.set_badge("●  tippt")
        self.set_status("Schreibmodus an — Browser kommt in den Vordergrund.")
        threading.Thread(target=self.start_typing, daemon=True).start()

    def stop_typing(self) -> None:
        self.stop_flag.set()
        self.typing = False
        if self.start_button:
            self.start_button.config(text="Start Typing")
        self.set_badge("●  verbunden" if self.connected else "●  getrennt")
        self.set_status("Gestoppt.")
        self._apply_topmost()

    def quit_callback(self) -> None:
        self.stop_flag.set()
        self.typing = False
        if self.driver:
            try:
                self.driver.quit()
            except Exception:
                pass
        if self.root:
            self.root.destroy()
        sys.exit(0)

    def panic_button_callback(self) -> None:
        self.stop_flag.set()
        self.typing = False
        sys.exit(0)

    def login(self, email: str, password: str) -> None:
        cfg = self.current_config()
        base = cfg["base_url"].rstrip("/")
        self.driver.get(base + LOGIN_PATH)
        timeout = int(cfg.get("login_timeout_s") or 180)
        deadline = time.time() + timeout
        submitted = False
        last_note = ""
        captcha_since: float | None = None
        while time.time() < deadline:
            prev = captcha_since
            captcha_since = maybe_reload_stuck_captcha(self.driver, captcha_since)
            if prev is not None and captcha_since is not None and captcha_since != prev:
                self.set_status("Captcha-Tab neu geladen…")
            dismiss_overlays(self.driver)
            if logged_in_markers(self.driver):
                self.set_status("Eingeloggt.")
                break
            user = first_visible(self.driver, LOGIN_USER)
            pw = first_visible(self.driver, LOGIN_PASS)
            if user and pw and not submitted:
                self.set_status("Login-Felder da — melde an…")
                fill_input(self.driver, user, email)
                fill_input(self.driver, pw, password)
                btn = first_visible(self.driver, LOGIN_SUBMIT)
                try:
                    if btn is not None:
                        try:
                            btn.click()
                        except Exception:
                            self.driver.execute_script("arguments[0].click();", btn)
                    else:
                        pw.send_keys(Keys.ENTER)
                except Exception:
                    try:
                        self.driver.execute_script(
                            "var e=arguments[0]; if(e.form) e.form.submit();",
                            pw,
                        )
                    except Exception:
                        pass
                submitted = True
                self.set_status("Login abgeschickt…")
            elif not submitted:
                nudge_captcha(self.driver)
                note = "Captcha im Browser lösen — Login startet sofort danach."
                if note != last_note:
                    self.set_status(note)
                    last_note = note
            time.sleep(0.12)
        else:
            self.set_status("Login-Wartezeit vorbei — wenn du drin bist, Level manuell öffnen.")
        if cfg.get("open_level_page"):
            try:
                if not open_write_mode(self.driver, base):
                    self.driver.get(base + LEVEL_PATH)
            except Exception:
                pass

    def type_into_page(self, text: str) -> None:
        for ch in glyphs_to_type(text):
            type_char(self.driver, ch)

    def start_typing(self) -> None:
        try:
            self._set_topmost(False)
            time.sleep(0.25)
            cfg = self.current_config()
            base = str(cfg.get("base_url") or DEFAULT_CONFIG["base_url"])
            foreground_browser(self.driver)
            arm_lesson(self.driver, base)
            focus_typer(self.driver)
            captcha_since: float | None = None
            stalls = 0
            while not self.stop_flag.is_set():
                captcha_since = maybe_reload_stuck_captcha(self.driver, captcha_since)
                cfg = self.current_config()
                base = str(cfg.get("base_url") or DEFAULT_CONFIG["base_url"])
                try:
                    language_text = prompt_text(self.driver, timeout=min(3.0, float(cfg.get("prompt_timeout_s") or 8)))
                except Exception:
                    self.set_status("Kein Tipptext — öffne Schreiben / Lektion…")
                    foreground_browser(self.driver)
                    arm_lesson(self.driver, base)
                    time.sleep(0.6)
                    continue
                if self.root:
                    self.root.after(0, lambda t=language_text: self.preview.config(text=t))
                ch = first_remaining_glyph(language_text)
                used = send_glyph_verified(self.driver, ch, language_text)
                if used:
                    stalls = 0
                    left = remaining_prompt_now(self.driver)
                    n = len(left) if left is not None else max(0, len(language_text) - 1)
                    show = "␣" if ch == " " else ch
                    self.set_status(f"Tippt »{show}« per {used} · noch {n} Zeichen")
                else:
                    stalls += 1
                    foreground_browser(self.driver)
                    arm_lesson(self.driver, base)
                    focus_typer(self.driver)
                    remember_send(None)
                    if stalls == 1:
                        self.set_status("Tasten kommen nicht an — Browser-Fenster in den Vordergrund…")
                    elif stalls >= 3:
                        self.set_status("Schreibmodus aktiv, aber die Lektion nimmt keine Tasten. Lektion im Browser starten, dann TypeHack nicht anklicken.")
                if self.stop_flag.is_set():
                    break
                time.sleep(interval_seconds(cfg))
        except Exception as exc:
            self.set_status(f"Fehler: {exc}")
            print(f"An error occurred: {exc}")
        finally:
            self.typing = False
            self._apply_topmost()
            if self.root:
                self.root.after(0, lambda: self.start_button.config(text="Start Typing"))
                self.set_badge("●  verbunden" if self.connected else "●  getrennt")


def print_banner() -> None:
    print(Fore.CYAN + Style.BRIGHT + "TypeHack")
    print(Fore.MAGENTA + Style.BRIGHT + "Made by Nikoheld" + Style.RESET_ALL)


def main() -> None:
    print_banner()
    app = TypeHackApp()
    app.create_widgets()
    app.root.mainloop()


if __name__ == "__main__":
    main()
