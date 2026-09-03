# TypeHack

Hilfsprogramm für [typewriter.at](https://www.typewriter.at) (öffentliche Instanz `at4.typewriter.at`).

## Was neu ist

- **Kein mitgelieferter `msedgedriver.exe` mehr.** Selenium 4.27+ (Selenium Manager) holt den Treiber passend zur installierten Edge- oder Chrome-Version.
- Login wartet auf das Formular — auch wenn typewriter.at zuerst eine **ALTCHA**-Prüfung zeigt (im Browser lösen).
- Tippen geht über das Browser-Fenster (`send_keys`), nicht mehr über pynput ins falsche Fenster.
- Start/Stop ist nicht mehr verdreht. Credentials liegen in `credentials.json` (steht in `.gitignore`).

## Windows einrichten

1. [Python 3.12+](https://www.python.org/downloads/) installieren, **Add python.exe to PATH** ankreuzen.
2. `Installieren.bat` ausführen.
3. `Start.bat` oder `py -3 TypeHack.py`.
4. Beim ersten Mal `n` — E-Mail und Passwort. Danach `j`.
5. Edge/Chrome öffnet typewriter.at. Captcha lösen, falls nötig. Level wählen.
6. Im TypeHack-Fenster **Start Typing**.

Geschwindigkeit: links schnell, rechts Pause zwischen den Blöcken.

**Quit** schließt Browser + App. **Panic!** bricht nur das Python-Programm ab.

## Abhängigkeiten

Siehe `requirements.txt`:

- selenium
- colorama

## Bekannte Grenzen

- Die Tipp-Seite hängt an CSS/XPath-Kandidaten. Ändert typewriter.at das Layout, Selectors in `TypeHack.py` (`PROMPT_SELECTORS`) anpassen.
- Server-IPs sehen oft nur die ALTCHA-Seite; ein normaler Schul-PC mit Edge kommt in der Regel durch.
- Plus-Versionen laufen auf der Schul-Subdomain (z. B. `schule.typewriter.at`). Dann `DEFAULT_BASE` in `TypeHack.py` ändern.
