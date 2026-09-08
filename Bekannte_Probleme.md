# Bekannte Probleme

1. Alte Bundles mit `msedgedriver.exe` brechen, sobald Edge sich updated. Lösung: Selenium Manager (aktuelles TypeHack).
2. `at4.typewriter.at` kann eine ALTCHA-Sicherheitsprüfung vorschalten. Im Browser lösen, das Programm wartet auf das Login-Feld.
3. Plus-Instanzen nutzen eine andere Basis-URL als die Public-Version.
4. **2.2.0 / 2.3.0 Auto-Update:** `Die Datei "\\" wurde nicht gefunden` — der Updater startete Setup per `start ""`. Auf deutschem Windows ist der leere Titel der Dateiname `\\`. **2.2.0 kann sich nicht selbst updaten.** Einmal **TypeHack-Setup-2.4.0.exe** von Hand starten. Ab 2.3.1 startet der Updater Setup direkt.
5. **2.4.x Schreibmodus tippt nicht:** ActionChains/`send_keys` braucht ein fokussiertes Browserfenster. Das TypeHack-Fenster lag `always-on-top` darüber, und die Lektion startet oft erst nach dem jQuery-OK/Enter-Dialog. **2.5.0** holt Edge/Chrome in den Vordergrund, klickt den Start-Dialog, sendet echte OS-Tasten (Space = Taste 32) und prüft, ob `#text_todo_1` kürzer wird.
6. **3.0.0** ist ein Rust-Rebuild (kein Python/Tk mehr). `TypeHack.py` bleibt nur als 2.x-Archiv. Starten mit `target\release\TypeHack.exe` / Desktop-Verknüpfung.
7. **3.0.0 MAX Speed** war zu langsam, weil nach jeder Taste Selenium die Restzeile gelesen hat. **3.0.1** tippt die ganze Restzeile in einem OS-Burst (≥ 100000 Anschläge / 10 min).
8. **3.0.1** tippte weiter im Burst, wenn MAX Speed noch an war oder ein alter Schreib-Loop lief. **3.0.2**: 2000 wählen schaltet MAX aus; der Takt gilt sofort.
9. **3.1.0** installiert sich nach `%LOCALAPPDATA%\TypeHack`, lädt `msedgedriver` passend zu Edge und aktualisiert im Hintergrund von GitHub. Ohne Microsoft Edge geht Verbinden nicht.
10. **3.1.0** tippte ÄÖÜ auf Schweizer Tastatur falsch (Umschalt+ö = é). **3.1.1** nutzt die Layout-Taste der Vordergrund-App und Caps Lock für Groß-Umlaute.
11. **Erster Anschlag immer falsch:** der Start-Dialog „beliebige Taste“ frisst die erste Taste. **3.1.3** schließt den Dialog mit Enter, bevor die Lektion getippt wird.
12. **Zeichen ohne Taste** (ß auf CH, ^ tot, AltGr @€): OS-Taste, sonst JS/CDP. **3.1.4** kann jedes Lektionszeichen.
