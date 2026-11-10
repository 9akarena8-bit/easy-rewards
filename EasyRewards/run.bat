@echo off
setlocal
cd /d "%~dp0"
title Easy Rewards
set "EASY_REWARDS_LAUNCHER=1"

rem ---- find Python 3.10+ ------------------------------------------------------
set "PY="
where py >nul 2>nul && set "PY=py -3"
if not defined PY where python >nul 2>nul && set "PY=python"
if not defined PY goto nopython
%PY% -c "import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)" >nul 2>nul
if errorlevel 1 goto nopython
%PY% -c "import tkinter" >nul 2>nul
if errorlevel 1 goto notk

rem ---- private environment (created once) ------------------------------------
if not exist ".venv\Scripts\python.exe" (
    echo Creating the environment, this happens only once...
    %PY% -m venv .venv
    if errorlevel 1 goto fail
)

:run
echo Checking components...
".venv\Scripts\python.exe" -m pip install -q -r requirements.txt
if errorlevel 1 echo (could not reach the package server - trying to start anyway)
".venv\Scripts\python.exe" -m pip install -q -r requirements-ui.txt >nul 2>nul

".venv\Scripts\python.exe" app.py %*
set "RC=%errorlevel%"
if "%RC%"=="42" goto run
if not "%RC%"=="0" goto fail
exit /b 0

:nopython
echo.
echo  Python 3.10 or newer was not found.
echo  1. Download it from https://www.python.org/downloads/windows/
echo  2. In the installer tick "Add python.exe to PATH" and keep "tcl/tk" ticked.
echo  3. Run this file again.
start "" https://www.python.org/downloads/windows/
pause
exit /b 1

:notk
echo.
echo  This Python was installed without tcl/tk (needed for the window).
echo  Re-run the Python installer, choose Modify, and tick "tcl/tk and IDLE".
pause
exit /b 1

:fail
echo.
echo  Easy Rewards stopped because of an error.
echo  Details are in crash.log next to this file - please send it to whoever is helping you.
pause
exit /b 1
