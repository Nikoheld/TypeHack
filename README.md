# TypeHack 3.1.0

Native **Rust** helper for [typewriter.at](https://www.typewriter.at) (public instance `at4.typewriter.at`).

## Clean Windows install

No Python, no admin, no extra runtime:

1. Download `TypeHack-Setup-3.1.0.exe` or `TypeHack-3.1.0.exe` from [Releases](https://github.com/Nikoheld/TypeHack/releases).
2. Run it. The app copies itself to `%LOCALAPPDATA%\TypeHack`, creates Desktop + Start-menu shortcuts, and downloads a matching **msedgedriver** for the installed Microsoft Edge.
3. **Verbinden** — Captcha im Browser lösen (Seite wird nur neu geladen).
4. Im **Dashboard** eine Lektion wählen, dann **Start Typing**.

Windows 10/11 already includes Edge. If Edge is missing, install it from https://www.microsoft.com/edge.

Updates download in the background from GitHub and apply when you are not typing (checkbox **Automatisch aktualisieren**).

Settings: `%LOCALAPPDATA%\TypeHack\config.json`, login: `credentials.json` (gitignored).

## What 3.1 does

- Remaining prompt from `#text_todo_1` (empty span = space, skip done spans, umlauts, `*`).
- Space = virtual key **32**. y/z/ö are characters, not KeyY/KeyZ.
- Pace = Anschläge / 10 Minuten (200–8000, **2000 → 0.3 s**). Changing the number **turns MAX Speed off**.
- **MAX Speed** dumps the whole remaining line with OS keys (≥ 100000 Anschläge / 10 min).
- After login stays on `user/overview`. Does **not** open `generateLevel`.
- Captcha: reload only. Achievement cards: closed, never clicked.
- Self-install + Edge driver + silent GitHub auto-update.

## Build from source

```
cargo test
cargo build --release --bin TypeHack
```

Output: `target/release/TypeHack.exe`
