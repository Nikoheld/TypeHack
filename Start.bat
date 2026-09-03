@echo off
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (
  py -3 TypeHack.py
) else (
  python TypeHack.py
)
pause
