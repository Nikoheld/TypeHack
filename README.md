# TypeHack

Hilfsprogramm für [typewriter.at](https://www.typewriter.at) (öffentliche Instanz `at4.typewriter.at`).

## Was neu ist

- **Kein mitgelieferter `msedgedriver.exe` mehr.** Selenium 4.27+ (Selenium Manager) holt den Treiber passend zur installierten Edge- oder Chrome-Version.
- Login wartet auf das Formular — auch wenn typewriter.at zuerst eine **ALTCHA**-Prüfung zeigt (im Browser lösen).
- Tippen geht über das Browser-Fenster (`send_keys`), nicht mehr über pynput ins falsche Fenster.
- Start/Stop ist nicht mehr verdreht. Credentials liegen in `credentials.json` (steht in `.gitignore`).

## Windows: Installer (kein Python nötig)

1. Unter [Releases](https://github.com/Nikoheld/TypeHack/releases) **TypeHack-Setup-2.3.0.exe** laden.
2. Installer starten (legt TypeHack nach `%LOCALAPPDATA%\TypeHack`, Desktop-Verknüpfung optional).
3. **TypeHack** öffnen — Microsoft Edge ist auf Windows 10/11 schon da.

**Installer bauen (einmalig auf einem Windows-PC):** `build.bat` ausführen, dann `installer\TypeHack.iss` in [Inno Setup](https://jrsoftware.org/isinfo.php) kompilieren. Ergebnis: `dist\TypeHack-Setup-2.1.0.exe`.

Oder GitHub Actions: Datei `installer/github-actions-build-windows.yml` nach `.github/workflows/build-windows.yml` kopieren und den Workflow starten — Artifact **TypeHack-Setup**.

## Windows einrichten (Entwickler, mit Python)

1. [Python 3.12+](https://www.python.org/downloads/) installieren, **Add python.exe to PATH** ankreuzen.
2. `Installieren.bat` ausführen.
3. `Start.bat` oder `py -3 TypeHack.py`.
4. `Start.bat` öffnet das **TypeHack-Fenster** (kein Konsolen-Login mehr).
5. E-Mail/Passwort, Server (AT/DE/CH/eigene URL), Browser, Tempo, Jitter, Tipp-Modus einstellen.
6. **Verbinden** — Captcha im Browser lösen, falls nötig. Level wählen.
7. **Start Typing**.

Einstellungen liegen in `config.json`, Login in `credentials.json` (beide nicht im Git).

## Auto-Update

Die App prüft beim Start GitHub Releases. Gibt es eine neuere **TypeHack-Setup-*.exe**, kannst du sie installieren (SHA-256, stiller Inno-Setup, Neustart). Optionen: *Beim Start prüfen*, *Updates still installieren*.

**Quit** schließt Browser + App. **Panic!** bricht nur das Python-Programm ab.

## Abhängigkeiten

Siehe `requirements.txt`:

- selenium
- colorama

## Bekannte Grenzen

- Die Tipp-Seite hängt an CSS/XPath-Kandidaten. Ändert typewriter.at das Layout, Selectors in `TypeHack.py` (`PROMPT_SELECTORS`) anpassen.
- Server-IPs sehen oft nur die ALTCHA-Seite; ein normaler Schul-PC mit Edge kommt in der Regel durch.
- Plus-Versionen: im GUI **Benutzerdefiniert** und die Schul-URL eintragen.
