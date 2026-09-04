# Bekannte Probleme

1. Alte Bundles mit `msedgedriver.exe` brechen, sobald Edge sich updated. Lösung: Selenium Manager (aktuelles TypeHack).
2. `at4.typewriter.at` kann eine ALTCHA-Sicherheitsprüfung vorschalten. Im Browser lösen, das Programm wartet auf das Login-Feld.
3. Plus-Instanzen nutzen eine andere Basis-URL als die Public-Version.
4. **2.2.0 / 2.3.0 Auto-Update:** `Die Datei "\\" wurde nicht gefunden` — der Updater startete Setup per `start ""`. Auf deutschem Windows ist der leere Titel der Dateiname `\\`. **2.2.0 kann sich nicht selbst updaten.** Einmal **TypeHack-Setup-2.4.0.exe** von Hand starten. Ab 2.3.1 startet der Updater Setup direkt.
5. **2.4.x Schreibmodus tippt nicht:** ActionChains/`send_keys` braucht ein fokussiertes Browserfenster. Das TypeHack-Fenster lag `always-on-top` darüber, und die Lektion startet oft erst nach dem jQuery-OK/Enter-Dialog. **2.5.0** holt Edge/Chrome in den Vordergrund, klickt den Start-Dialog, sendet echte OS-Tasten (Space = Taste 32) und prüft, ob `#text_todo_1` kürzer wird.
