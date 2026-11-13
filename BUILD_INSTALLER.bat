@echo off
setlocal
cd /d "%~dp0"
title Easy Rewards - Windows installer build

py -3.11 --version >nul 2>nul
if errorlevel 1 (
    echo Python 3.11 not found. Install it first.
    pause
    exit /b 1
)
if not exist ".buildenv\Scripts\python.exe" (
    py -3.11 -m venv .buildenv
    if errorlevel 1 goto error
)

".buildenv\Scripts\python.exe" -m pip install --disable-pip-version-check -r requirements.txt -r requirements-ui.txt -r merchant_service\requirements-offline.txt "pyinstaller>=6,<7"
if errorlevel 1 goto error

if not exist "assets\license-public.pem" (
    echo ERROR: missing assets\license-public.pem
    echo Launch OWNER_PANEL.bat, create an owner key and copy the PUBLIC key to assets.
    echo Never copy private-key.pem into the project or installer.
    pause
    exit /b 1
)

echo.
echo [1/2] Building Windows executable...
".buildenv\Scripts\python.exe" -m PyInstaller --noconfirm --clean EasyRewards.spec
if errorlevel 1 goto error

echo.
echo Ready: dist\EasyRewards\EasyRewards.exe
set "ISCC="
if exist "%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 7\ISCC.exe"
if exist "%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe" set "ISCC=%LOCALAPPDATA%\Programs\Inno Setup 6\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 7\ISCC.exe"
if exist "%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe" set "ISCC=%ProgramFiles(x86)%\Inno Setup 6\ISCC.exe"
if not defined ISCC (
    echo.
    echo [2/2] Installer compiler not found.
    echo Install Inno Setup from https://jrsoftware.org/isdl.php
    echo Then run BUILD_INSTALLER.bat again to create the single setup.exe.
    pause
    exit /b 0
)
echo [2/2] Building setup.exe...
"%ISCC%" "installer.iss"
if errorlevel 1 goto error
echo.
echo READY: release\EasyRewards_Setup_1.4.3.exe
pause
exit /b 0
:error
echo.
echo Build failed. Copy the error text from this window.
pause
exit /b 1
