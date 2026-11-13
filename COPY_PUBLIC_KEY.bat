@echo off
setlocal
cd /d "%~dp0"
title Fortnite Pirate Token - public verification key
set "PUB=%LOCALAPPDATA%\FPT-Owner-Licensing\license-public.pem"
if not exist "%PUB%" (
  echo [ERROR] Owner public key is missing.
  echo First run OWNER_PANEL.bat and click Prepare Keys.
  pause
  exit /b 1
)
if exist "assets\license-public.pem" (
  fc /b "assets\license-public.pem" "%PUB%" >nul
  if errorlevel 1 (
    echo [ERROR] An INCOMPATIBLE public key already exists in assets.
    echo Do not overwrite this without reviewing previous licenses.
    pause
    exit /b 1
  )
)
copy /y "%PUB%" "assets\license-public.pem" >nul
if errorlevel 1 (
  echo [ERROR] Could not copy public key.
  pause
  exit /b 1
)
echo [OK] Public verification key is now available to the client build.
echo Only the public key was copied. Do NOT copy private-key.pem.
pause
