@echo off
cd /d "%~dp0"
if exist "TypeHack.exe" (
  start "" "TypeHack.exe"
  exit /b 0
)
if exist "target\release\TypeHack.exe" (
  start "" "target\release\TypeHack.exe"
  exit /b 0
)
where cargo >nul 2>&1
if %errorlevel%==0 (
  cargo run --release --bin TypeHack
  exit /b %errorlevel%
)
echo TypeHack 3.0.2: cargo build --release
pause
