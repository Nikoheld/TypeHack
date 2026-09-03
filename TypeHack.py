#!/usr/bin/env python3
"""TypeHack — typewriter.at helper. Selenium Manager picks a matching Edge/Chrome driver."""

from __future__ import annotations

import json
import sys
import threading
import time
from getpass import getpass
from pathlib import Path

from colorama import Fore, Style, init as colorama_init
from selenium import webdriver
from selenium.common.exceptions import TimeoutException, WebDriverException
from selenium.webdriver.common.by import By
from selenium.webdriver.common.keys import Keys
from selenium.webdriver.edge.options import Options as EdgeOptions
from selenium.webdriver.chrome.options import Options as ChromeOptions
from selenium.webdriver.support import expected_conditions as EC
from selenium.webdriver.support.ui import WebDriverWait

colorama_init(autoreset=True)

BASE_DIR = Path(__file__).resolve().parent
CREDENTIALS_FILE = BASE_DIR / "credentials.json"
DEFAULT_BASE = "https://at4.typewriter.at"
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


def prompt_text(driver) -> str:
    el = first_present(driver, PROMPT_SELECTORS, timeout=8.0)
    text = (el.text or el.get_attribute("textContent") or "").strip()
    if not text:
        raise TimeoutException("Tipptext ist leer")
    return text


def build_edge():
    options = EdgeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Edge(options=options)


def build_chrome():
    options = ChromeOptions()
    options.add_argument("--disable-blink-features=AutomationControlled")
    options.add_experimental_option("excludeSwitches", ["enable-automation"])
    options.add_experimental_option("useAutomationExtension", False)
    return webdriver.Chrome(options=options)


def create_driver():
    errors = []
    for factory, name in ((build_edge, "Edge"), (build_chrome, "Chrome")):
        try:
            print(f"Starte {name} (Selenium Manager lädt den passenden Treiber)...")
            return factory()
        except WebDriverException as exc:
            errors.append(f"{name}: {exc}")
            print(f"{name} fehlgeschlagen: {exc}")
    raise WebDriverException("Weder Edge noch Chrome startbar:\n" + "\n".join(errors))


class TypeHackApp:
    def __init__(self, base_url: str = DEFAULT_BASE):
        self.base_url = base_url.rstrip("/")
        self.root: tk.Tk | None = None
        self.stop_flag = threading.Event()
        self.typing = False
        self.driver = None
        self.min_speed = 0.0
        self.max_speed = 4.0

    def create_widgets(self) -> None:
        import tkinter as tk
        from tkinter import ttk

        self.root = tk.Tk()
        self.root.title("TypeHack")
        self.root.minsize(280, 220)

        self.start_animation_label = tk.Label(self.root, text="", font=("Arial", 20), fg="white", bg="black")
        self.start_animation_label.pack(fill="x")

        self.status_label = tk.Label(self.root, text="Bereit. Level in Typewriter wählen, dann Start.", wraplength=320)
        self.status_label.pack(pady=4)

        self.start_button = tk.Button(self.root, text="Start Typing", command=self.toggle_typing)
        self.start_button.pack(pady=2)

        self.quit_button = tk.Button(self.root, text="Quit", command=self.quit_callback)
        self.quit_button.pack(pady=2)

        self.panic_button = tk.Button(self.root, text="Panic!", command=self.panic_button_callback)
        self.panic_button.pack(pady=2)

        self.language_label = tk.Label(self.root, text="", font=("Arial", 12), wraplength=320)
        self.language_label.pack(pady=4)

        tk.Label(self.root, text="Geschwindigkeit (links = schnell)").pack()
        self.speed_scale = ttk.Scale(
            self.root, from_=self.min_speed, to=self.max_speed, length=200, orient="horizontal"
        )
        self.speed_scale.set(0.05)
        self.speed_scale.pack()

        tk.Label(self.root, text="Made by Nikoheld", font=("Arial", 8), fg="gray").pack(side=tk.BOTTOM)
        self.root.protocol("WM_DELETE_WINDOW", self.quit_callback)

    def set_status(self, text: str) -> None:
        if self.root:
            self.root.after(0, lambda: self.status_label.config(text=text))

    def toggle_typing(self) -> None:
        if self.typing:
            self.stop_flag.set()
            self.typing = False
            self.start_button.config(text="Start Typing")
            self.set_status("Gestoppt.")
            return
        self.stop_flag.clear()
        self.typing = True
        self.start_button.config(text="Stop Typing")
        self.set_status("Tippt… Typewriter-Fenster im Vordergrund lassen.")
        threading.Thread(target=self.start_typing, daemon=True).start()

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
        login_url = self.base_url + LOGIN_PATH
        self.driver.get(login_url)
        print("Falls eine Sicherheitsprüfung (ALTCHA) kommt: im Browser lösen, dann warten wir auf das Login-Formular…")
        user = WebDriverWait(self.driver, 180).until(lambda d: first_present(d, LOGIN_USER, timeout=1.5))
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
            print("Login-Wartezeit vorbei — wenn du eingeloggt bist, Level manuell öffnen.")
        self.driver.get(self.base_url + LEVEL_PATH)

    def type_into_page(self, text: str) -> None:
        try:
            el = self.driver.switch_to.active_element
            el.send_keys(text)
        except Exception:
            self.driver.find_element(By.TAG_NAME, "body").send_keys(text)

    def start_typing(self) -> None:
        try:
            while not self.stop_flag.is_set():
                try:
                    language_text = prompt_text(self.driver)
                except Exception as exc:
                    self.set_status(f"Kein Tipptext: {exc}. Level starten, dann warten…")
                    time.sleep(1.0)
                    continue
                self.root.after(0, lambda t=language_text: self.language_label.config(text=t))
                self.type_into_page(language_text)
                speed = float(self.speed_scale.get())
                time.sleep(max(0.0, speed))
        except Exception as exc:
            self.set_status(f"Fehler: {exc}")
            print(f"An error occurred: {exc}")
        finally:
            self.typing = False
            if self.root:
                self.root.after(0, lambda: self.start_button.config(text="Start Typing"))

    def start_animation(self, text: str, index: int = 0) -> None:
        if index < len(text):
            current = self.start_animation_label["text"]
            self.start_animation_label.config(text=current + text[index])
            self.root.after(80, lambda: self.start_animation(text, index + 1))


def print_banner() -> None:
    print(Fore.CYAN + Style.BRIGHT + "TypeHack")
    print(Fore.MAGENTA + Style.BRIGHT + "Made by Nikoheld" + Style.RESET_ALL)


def main() -> None:
    print_banner()
    choice = input("Gespeicherte Anmeldedaten verwenden? (j/n): ").strip().lower()
    app = TypeHackApp()
    if choice == "j":
        email, password = load_credentials()
        if not email or not password:
            print("Keine gespeicherten Anmeldedaten. Starte mit n.")
            return
    elif choice == "n":
        email = input("E-Mail / Benutzername: ").strip()
        password = getpass("Passwort: ")
        save_credentials(email, password)
        print(f"Gespeichert in {CREDENTIALS_FILE.name} (nicht ins Git legen).")
    else:
        print("Ungültige Eingabe.")
        return

    app.driver = create_driver()
    print("Login…")
    app.login(email, password)
    print("Steuerfenster…")
    app.create_widgets()
    app.start_animation("TypeHack")
    app.root.attributes("-topmost", True)
    app.root.mainloop()


if __name__ == "__main__":
    main()
