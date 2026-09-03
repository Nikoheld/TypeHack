@echo off
setlocal
cd /d "%~dp0"
where py >nul 2>&1
if %errorlevel%==0 (set PY=py -3) else (set PY=python)

echo Building TypeHack.exe ...
%PY% -m pip install --upgrade pip
%PY% -m pip install -r requirements.txt pyinstaller
%PY% -m PyInstaller --noconfirm TypeHack.spec
echo.
echo Frozen app: dist\TypeHack\TypeHack.exe
echo Compile installer\TypeHack.iss with Inno Setup to get TypeHack-Setup-2.1.0.exe
pause
