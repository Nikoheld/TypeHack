@echo off
setlocal
cd /d "%~dp0"

where py >nul 2>&1
if %errorlevel%==0 (
  set PY=py -3
) else (
  set PY=python
)

echo Installing Python packages (Selenium Manager fetches Edge/Chrome drivers)...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
  echo pip failed. Install Python 3.12+ from https://www.python.org/downloads/ and tick "Add python.exe to PATH".
  pause
  exit /b 1
)

echo Done. Start with Start.bat or:  %PY% TypeHack.py
pause
