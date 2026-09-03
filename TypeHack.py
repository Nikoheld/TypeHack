#!/usr/bin/env python3
"""TypeHack — typewriter.at helper with a config-rich desktop UI."""

from __future__ import annotations

import json
import random
import sys
import threading
import time
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
VERSION = "2.3.1"

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
    (By.CSS_SELECTOR, "input[type='password']"),
]
PROMPT_SELECTORS = [
    (By.CSS_SELECTOR, "#typewriter-text"),
    (By.CSS_SELECTOR, ".typewriter-text"),
    (By.CSS_SELECTOR, "#textToType"),
    (By.CSS_SELECTOR, ".current-line"),
    (By.CSS_SELECTOR, ".tw-text"),
    (By.CSS_SELECTOR, "span.letter, span.char"),
    (By.XPATH, "/html/body/div[5]/div[2]/div[3]/div[2]/div[2]/span[1]"),
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


def delay_seconds(cfg: dict, *, char: bool = False) -> float:
    base_ms = float(cfg.get("char_delay_ms") if char else cfg.get("delay_ms") or 0)
    jitter = max(0.0, min(100.0, float(cfg.get("jitter_pct") or 0))) / 100.0
    factor = 1.0 + random.uniform(-jitter, jitter) if jitter else 1.0
    return max(0.0, (base_ms / 1000.0) * factor)


def first_present(driver, locators, timeout: float = 2.0):
    end = time.time() + timeout
    last = None
    while time.time() < end:
        for by, value in locators:
            try:
                el = driver.find_element(by, value)
                if el.is_displayed():
                    return el
            except Exception as exc:  # noqa: BLE001
                last = exc
        time.sleep(0.2)
    if last:
        raise last
    raise TimeoutException("Kein passendes Element gefunden")


def normalize_prompt_text(raw: str) -> str:
    return (raw or "").replace("\xa0", " ").replace("\u202f", " ").replace("\t", " ")


def keys_for_char(ch: str):
    if ch in (" ", "\xa0", "\u202f"):
        return Keys.SPACE
    if ch in ("\n", "\r"):
        return Keys.RETURN
    return ch


def prompt_text(driver, timeout: float = 8.0) -> str:
    el = first_present(driver, PROMPT_SELECTORS, timeout=timeout)
    try:
        js = (
            "var e=arguments[0];"
            "var spans=e.querySelectorAll('span');"
            "if(spans.length){"
            "  return Array.prototype.map.call(spans,function(s){"
            "    var t=s.textContent;"
            "    if(t==null||t===''||t===' '||t==='\\u00a0') return ' ';"
            "    return t;"
            "  }).join('');"
            "}"
            "return (e.textContent||'');"
        )
        text = driver.execute_script(js, el) or ""
    except Exception:
        text = el.get_attribute("textContent") or el.text or ""
    text = normalize_prompt_text(text).strip("\n\r")
    if not text.strip():
        raise TimeoutException("Tipptext ist leer")
    return text


def pass_altcha_then_reload(driver) -> bool:
    """Click the ALTCHA/captcha control once, then reload — that is how typewriter.at lets you in."""
    selectors = [
        (By.CSS_SELECTOR, "#chal-form button"),
        (By.CSS_SELECTOR, "form#chal-form button"),
        (By.CSS_SELECTOR, ".altcha, .altcha-checkbox, button.altcha"),
        (By.CSS_SELECTOR, "#altcha"),
        (By.CSS_SELECTOR, "input[name='altcha']"),
        (By.CSS_SELECTOR, "#chal-form"),
        (By.XPATH, "//button[contains(., 'Roboter') or contains(., 'Captcha') or contains(., 'Verify') or contains(., 'Mensch')]"),
        (By.CSS_SELECTOR, "input[type='checkbox']"),
    ]
    clicked = False
    for by, value in selectors:
        try:
            el = WebDriverWait(driver, 4).until(EC.element_to_be_clickable((by, value)))
            driver.execute_script("arguments[0].click();", el)
            clicked = True
            break
        except Exception:
            continue
    time.sleep(1.2)
    driver.refresh()
    time.sleep(0.8)
    return clicked


def _stealth(options) -> None:
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)


def build_edge():
    options = EdgeOptions()
    _stealth(options)
    return webdriver.Edge(options=options)


def build_chrome():
    options = ChromeOptions()
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
        self.root.geometry("420x560")
        self.root.minsize(380, 480)
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

        ttk.Label(inner, text="Tempo (links = schnell)", style="Muted.TLabel").pack(anchor="w", padx=16)
        ttk.Scale(inner, from_=1, to=80, variable=self.vars["char_delay_ms"], orient="horizontal").pack(fill="x", padx=16)

        self.preview = tk.Label(
            inner,
            text="Verbinden → Captcha klicken (TypeHack lädt neu) → Level wählen → Start.",
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
        self.set_status("Starte Browser… Captcha im Fenster lösen, falls nötig.")
        threading.Thread(target=self._connect_worker, args=(email, password), daemon=True).start()

    def _connect_worker(self, email: str, password: str) -> None:
        try:
            self.driver = create_driver(self.cfg.get("browser") or "Auto")
            self.login(email, password)
            self.connected = True
            self.set_badge("●  verbunden")
            self.set_status("Verbunden. Level wählen, dann Start Typing.")
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

    def toggle_typing(self) -> None:
        if self.typing:
            self.stop_typing()
            return
        if not self.driver:
            self.set_status("Zuerst verbinden.")
            return
        self.stop_flag.clear()
        self.typing = True
        self.start_button.config(text="Stop Typing")
        self.set_badge("●  tippt")
        self.set_status("Tippt… Typewriter-Fenster sichtbar lassen.")
        threading.Thread(target=self.start_typing, daemon=True).start()

    def stop_typing(self) -> None:
        self.stop_flag.set()
        self.typing = False
        if self.start_button:
            self.start_button.config(text="Start Typing")
        self.set_badge("●  verbunden" if self.connected else "●  getrennt")
        self.set_status("Gestoppt.")

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
        from selenium.webdriver.common.action_chains import ActionChains

        cfg = self.current_config()
        base = cfg["base_url"].rstrip("/")
        self.driver.get(base + LOGIN_PATH)
        timeout = int(cfg.get("login_timeout_s") or 180)
        self.set_status("Captcha: klicken, dann lädt TypeHack die Seite neu…")
        try:
            first_present(self.driver, LOGIN_USER, timeout=3)
        except Exception:
            pass_altcha_then_reload(self.driver)
        user = WebDriverWait(self.driver, timeout).until(lambda d: first_present(d, LOGIN_USER, timeout=1.5))
        user.clear()
        user.send_keys(email)
        pw = first_present(self.driver, LOGIN_PASS, timeout=10)
        pw.clear()
        pw.send_keys(password)
        ActionChains(self.driver).send_keys(Keys.ENTER).perform()
        try:
            WebDriverWait(self.driver, 30).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "ui-dialog-buttonset")),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='runLevel']")),
                    EC.url_contains("runLevel"),
                )
            )
        except TimeoutException:
            self.set_status("Login-Wartezeit vorbei — wenn du drin bist, Level manuell öffnen.")
        if cfg.get("open_level_page"):
            self.driver.get(base + LEVEL_PATH)

    def type_into_page(self, text: str) -> None:
        from selenium.webdriver.common.action_chains import ActionChains

        actions = ActionChains(self.driver)
        for ch in text:
            actions.send_keys(keys_for_char(ch))
        actions.perform()

    def start_typing(self) -> None:
        try:
            while not self.stop_flag.is_set():
                cfg = self.current_config()
                try:
                    language_text = prompt_text(self.driver, timeout=float(cfg.get("prompt_timeout_s") or 8))
                except Exception as exc:
                    self.set_status(f"Kein Tipptext: {exc}")
                    time.sleep(1.0)
                    continue
                if self.root:
                    self.root.after(0, lambda t=language_text: self.preview.config(text=t))
                for ch in language_text:
                    if self.stop_flag.is_set():
                        break
                    self.type_into_page(ch)
                    time.sleep(delay_seconds(cfg, char=True))
        except Exception as exc:
            self.set_status(f"Fehler: {exc}")
            print(f"An error occurred: {exc}")
        finally:
            self.typing = False
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
