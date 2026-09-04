# TypeHack 3.0.1

Native **Rust** helper for [typewriter.at](https://www.typewriter.at) (public instance `at4.typewriter.at`).

The 2.x Python/Tk app is no longer the shipped runtime. **3.0** is a full rebuild: faster process, new desktop UI, OS keystrokes into the hidden typewriter input.

## Run (Windows)

1. [Rust](https://rustup.rs) (MSVC toolchain) and Microsoft Edge.
2. `cargo test`
3. `cargo run --release --bin TypeHack` or `Start.bat`
4. E-Mail / Passwort, Server (AT/DE/CH), Anschläge / 10 Minuten.
5. **Verbinden** — Captcha im Browser lösen (Seite wird nur neu geladen, nicht angeklickt).
6. Im **Dashboard** selbst eine Lektion wählen.
7. **Start Typing** — Edge-Fenster vorn lassen.

Settings: `config.json`, login: `credentials.json` (gitignored).

## What 3.0.1 does

- Remaining prompt from `#text_todo_1` (empty span = space, skip done spans, umlauts, `*`).
- Space = virtual key **32**. y/z/ö are characters, not KeyY/KeyZ.
- Pace = Anschläge / 10 Minuten (200–8000, 2000 → 0.3 s wall-clock).
- **MAX Speed** dumps the whole remaining line with OS keys (no Selenium between keystrokes), targeting **≥ 100000 Anschläge / 10 min**.
- After login stays on `user/overview`. Does **not** open `generateLevel`.
- Captcha: reload only. Achievement cards: closed, never clicked.

## Build

```
cargo build --release --bin TypeHack
```

Output: `target/release/TypeHack.exe`
