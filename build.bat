@echo off
setlocal
cd /d "%~dp0"
where cargo >nul 2>&1
if %errorlevel% neq 0 (
  echo Install Rust from https://rustup.rs and re-run build.bat
  pause
  exit /b 1
)
cargo test
if %errorlevel% neq 0 exit /b 1
cargo build --release --bin TypeHack
echo.
echo Built: target\release\TypeHack.exe
pause
