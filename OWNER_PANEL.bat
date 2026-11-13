@echo off
setlocal
cd /d "%~dp0"
title Fortnite Pirate Token - private owner console
py -3.11 -c "import cryptography" >nul 2>nul
if errorlevel 1 (
  echo Installing offline license signing dependency...
  py -3.11 -m pip install -r merchant_service\requirements-offline.txt
  if errorlevel 1 goto failed
)
py -3.11 owner_access.py
if errorlevel 1 goto failed
exit /b 0
:failed
echo.
echo Owner panel could not start. Please copy this error.
pause
exit /b 1
