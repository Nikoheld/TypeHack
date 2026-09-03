#!/usr/bin/env python3
"""TypeHack — typewriter.at helper with a config-rich desktop UI."""

from __future__ import annotations

import json
import random
import sys
import threading
import time
from pathlib import Path

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

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
CONFIG_FILE = BASE_DIR / "config.json"

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
    "type_mode": "block",
    "delay_ms": 50,
    "char_delay_ms": 18,
    "jitter_pct": 15,
    "burst_chars": 0,
    "login_timeout_s": 180,
    "prompt_timeout_s": 8,
    "theme_accent": "#6ee7b7",
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


def prompt_text(driver, timeout: float = 8.0) -> str:
    el = first_present(driver, PROMPT_SELECTORS, timeout=timeout)
    text = (el.text or el.get_attribute("textContent") or "").strip()
    if not text:
        raise TimeoutException("Tipptext ist leer")
    return text


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
        self.root.geometry("920x620")
        self.root.minsize(820, 560)
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
        style.configure("TRadiobutton", background=PALETTE["card"], foreground=PALETTE["text"], font=("Segoe UI", 10))
        style.configure("TCombobox", fieldbackground=PALETTE["panel"], background=PALETTE["panel"], foreground=PALETTE["text"])
        style.configure("Horizontal.TScale", background=PALETTE["card"], troughcolor=PALETTE["line"])
        style.configure("Primary.TButton", font=("Segoe UI", 11, "bold"), padding=8)
        style.map("Primary.TButton", background=[("!disabled", accent), ("disabled", PALETTE["line"])], foreground=[("!disabled", "#052e1c")])
        style.configure("Ghost.TButton", font=("Segoe UI", 10), padding=6)
        style.configure("Danger.TButton", font=("Segoe UI", 10, "bold"), padding=6)
        style.map("Danger.TButton", background=[("!disabled", PALETTE["danger"])], foreground=[("!disabled", "#1a0508")])

        header = ttk.Frame(self.root, style="Panel.TFrame")
        header.pack(fill="x", padx=16, pady=(16, 8))
        ttk.Label(header, text="TypeHack", style="Title.TLabel").pack(side="left")
        self.badge = ttk.Label(header, text="●  getrennt", style="Accent.TLabel")
        self.badge.pack(side="right", padx=8)
        ttk.Label(header, text="typewriter.at  ·  Nikoheld", style="Sub.TLabel").pack(side="right")

        body = ttk.Frame(self.root)
        body.pack(fill="both", expand=True, padx=16, pady=8)

        side = ttk.Frame(body, style="Card.TFrame")
        side.pack(side="left", fill="y", padx=(0, 12))
        main = ttk.Frame(body, style="Card.TFrame")
        main.pack(side="left", fill="both", expand=True)

        self._section(side, "Konto")
        self.vars["email"] = tk.StringVar(value=load_credentials()[0] or "")
        self.vars["password"] = tk.StringVar(value=load_credentials()[1] or "")
        self._labeled_entry(side, "E-Mail / Benutzer", self.vars["email"])
        self._labeled_entry(side, "Passwort", self.vars["password"], show="•")
        self.vars["remember_login"] = tk.BooleanVar(value=bool(self.cfg["remember_login"]))
        ttk.Checkbutton(side, text="Login speichern", variable=self.vars["remember_login"]).pack(anchor="w", padx=14, pady=2)

        self._section(side, "Server")
        self.vars["url_preset"] = tk.StringVar(value=self.cfg.get("url_preset") or "Österreich (at4)")
        self.vars["base_url"] = tk.StringVar(value=self.cfg.get("base_url") or DEFAULT_CONFIG["base_url"])
        preset = ttk.Combobox(side, textvariable=self.vars["url_preset"], values=list(PRESET_URLS), state="readonly", width=28)
        preset.pack(padx=14, pady=4, fill="x")
        preset.bind("<<ComboboxSelected>>", self._on_preset)
        self._labeled_entry(side, "Basis-URL", self.vars["base_url"])

        self._section(side, "Browser")
        self.vars["browser"] = tk.StringVar(value=self.cfg.get("browser") or "Auto")
        ttk.Combobox(side, textvariable=self.vars["browser"], values=("Auto", "Edge", "Chrome"), state="readonly", width=28).pack(
            padx=14, pady=4, fill="x"
        )

        self._section(side, "Fenster")
        self.vars["always_on_top"] = tk.BooleanVar(value=bool(self.cfg["always_on_top"]))
        self.vars["open_level_page"] = tk.BooleanVar(value=bool(self.cfg["open_level_page"]))
        self.vars["auto_start"] = tk.BooleanVar(value=bool(self.cfg["auto_start"]))
        ttk.Checkbutton(side, text="Immer im Vordergrund", variable=self.vars["always_on_top"], command=self._apply_topmost).pack(
            anchor="w", padx=14, pady=2
        )
        ttk.Checkbutton(side, text="Nach Login Level-Seite öffnen", variable=self.vars["open_level_page"]).pack(anchor="w", padx=14, pady=2)
        ttk.Checkbutton(side, text="Nach Login automatisch tippen", variable=self.vars["auto_start"]).pack(anchor="w", padx=14, pady=2)

        ttk.Button(side, text="Einstellungen speichern", style="Ghost.TButton", command=self.save_settings).pack(
            fill="x", padx=14, pady=(12, 16)
        )

        # Main column
        self.preview = tk.Label(
            main,
            text="Noch kein Text. Verbinden, Level wählen, dann Start.",
            wraplength=520,
            justify="left",
            bg=PALETTE["panel"],
            fg=PALETTE["text"],
            font=("Cascadia Mono", 13),
            padx=16,
            pady=16,
            anchor="nw",
        )
        self.preview.pack(fill="both", expand=True, padx=16, pady=(16, 8))

        self.status_label = ttk.Label(main, text="Bereit. Zuerst mit typewriter.at verbinden.", style="Muted.TLabel")
        self.status_label.pack(anchor="w", padx=16)

        btns = ttk.Frame(main, style="Card.TFrame")
        btns.pack(fill="x", padx=16, pady=10)
        self.connect_button = ttk.Button(btns, text="Verbinden", style="Primary.TButton", command=self.connect)
        self.connect_button.pack(side="left", padx=(0, 8))
        self.start_button = ttk.Button(btns, text="Start Typing", style="Primary.TButton", command=self.toggle_typing, state="disabled")
        self.start_button.pack(side="left", padx=4)
        ttk.Button(btns, text="Stop", style="Ghost.TButton", command=self.stop_typing).pack(side="left", padx=4)
        ttk.Button(btns, text="Panic", style="Danger.TButton", command=self.panic_button_callback).pack(side="right")

        self._section(main, "Tipp-Verhalten", bg="card")
        mode_row = ttk.Frame(main, style="Card.TFrame")
        mode_row.pack(fill="x", padx=16)
        self.vars["type_mode"] = tk.StringVar(value=self.cfg.get("type_mode") or "block")
        ttk.Radiobutton(mode_row, text="Ganzen Block", variable=self.vars["type_mode"], value="block").pack(side="left", padx=(0, 12))
        ttk.Radiobutton(mode_row, text="Zeichen für Zeichen", variable=self.vars["type_mode"], value="char").pack(side="left")

        grid = ttk.Frame(main, style="Card.TFrame")
        grid.pack(fill="x", padx=16, pady=8)
        self.vars["delay_ms"] = tk.DoubleVar(value=float(self.cfg.get("delay_ms") or 50))
        self.vars["char_delay_ms"] = tk.DoubleVar(value=float(self.cfg.get("char_delay_ms") or 18))
        self.vars["jitter_pct"] = tk.DoubleVar(value=float(self.cfg.get("jitter_pct") or 15))
        self.vars["burst_chars"] = tk.IntVar(value=int(self.cfg.get("burst_chars") or 0))
        self.vars["login_timeout_s"] = tk.IntVar(value=int(self.cfg.get("login_timeout_s") or 180))
        self.vars["prompt_timeout_s"] = tk.IntVar(value=int(self.cfg.get("prompt_timeout_s") or 8))
        self._slider(grid, 0, "Pause nach Block (ms)", self.vars["delay_ms"], 0, 800)
        self._slider(grid, 1, "Pause pro Zeichen (ms)", self.vars["char_delay_ms"], 0, 120)
        self._slider(grid, 2, "Jitter %", self.vars["jitter_pct"], 0, 60)
        self._slider(grid, 3, "Burst-Größe (0 = alles)", self.vars["burst_chars"], 0, 40)
        self._slider(grid, 4, "Login-Timeout (s)", self.vars["login_timeout_s"], 20, 300)
        self._slider(grid, 5, "Text-Suche Timeout (s)", self.vars["prompt_timeout_s"], 2, 30)

        foot = ttk.Frame(self.root, style="Panel.TFrame")
        foot.pack(fill="x", padx=16, pady=(0, 12))
        ttk.Label(foot, text="Quit schließt Browser. Panic beendet nur die App.", style="Sub.TLabel").pack(side="left")
        ttk.Button(foot, text="Beenden", style="Ghost.TButton", command=self.quit_callback).pack(side="right")

        self.root.protocol("WM_DELETE_WINDOW", self.quit_callback)
        self._apply_topmost()

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
        cfg = self.current_config()
        base = cfg["base_url"].rstrip("/")
        self.driver.get(base + LOGIN_PATH)
        timeout = int(cfg.get("login_timeout_s") or 180)
        user = WebDriverWait(self.driver, timeout).until(lambda d: first_present(d, LOGIN_USER, timeout=1.5))
        user.clear()
        user.send_keys(email)
        pw = first_present(self.driver, LOGIN_PASS, timeout=10)
        pw.clear()
        pw.send_keys(password + Keys.ENTER)
        try:
            WebDriverWait(self.driver, 30).until(
                EC.any_of(
                    EC.presence_of_element_located((By.CLASS_NAME, "ui-dialog-buttonset")),
                    EC.url_contains("typewriter"),
                    EC.presence_of_element_located((By.CSS_SELECTOR, "a[href*='runLevel']")),
                )
            )
        except TimeoutException:
            self.set_status("Login-Wartezeit vorbei — wenn du drin bist, Level manuell öffnen.")
        if cfg.get("open_level_page"):
            self.driver.get(base + LEVEL_PATH)

    def type_into_page(self, text: str) -> None:
        try:
            el = self.driver.switch_to.active_element
            el.send_keys(text)
        except Exception:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(text)

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
                mode = cfg.get("type_mode") or "block"
                burst = int(cfg.get("burst_chars") or 0)
                if mode == "char":
                    for ch in language_text:
                        if self.stop_flag.is_set():
                            break
                        self.type_into_page(ch)
                        time.sleep(delay_seconds(cfg, char=True))
                elif burst > 0:
                    for i in range(0, len(language_text), burst):
                        if self.stop_flag.is_set():
                            break
                        self.type_into_page(language_text[i : i + burst])
                        time.sleep(delay_seconds(cfg))
                else:
                    self.type_into_page(language_text)
                    time.sleep(delay_seconds(cfg))
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
