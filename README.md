# TypeHack 3.0.0

Native **Rust** helper for [typewriter.at](https://www.typewriter.at) (public instance `at4.typewriter.at`).

The 2.x Python/Tk app is no longer the shipped runtime. **3.0.0** is a full rebuild: faster process, new desktop UI, same lesson facts that made 2.5.0 type into the hidden input.

## Run (Windows)

1. [Rust](https://rustup.rs) (MSVC toolchain) and Microsoft Edge.
2. `cargo test`
3. `cargo run --release --bin TypeHack` or `Start.bat`
4. E-Mail / Passwort, Server (AT/DE/CH), Anschläge / 10 Minuten.
5. **Verbinden** — Captcha im Browser lösen.
6. **Start Typing** — Edge-Fenster vorn lassen.

Settings: `config.json`, login: `credentials.json` (gitignored).

## What 3.0 does

- Remaining prompt from `#text_todo_1` (empty span = space, skip done spans, umlauts, `*`).
- One glyph at a time. Space = virtual key **32**. y/z/ö are characters, not KeyY/KeyZ.
- Pace = Anschläge / 10 Minuten (200–8000, 2000 → 0.3 s).
- Opens Schreiben / `generateLevel`, Start-Dialog, focuses the hidden typewriter field, then `keybd_event` + `VkKeyScanW`.

## Build

```
cargo build --release --bin TypeHack
```

Output: `target/release/TypeHack.exe`
