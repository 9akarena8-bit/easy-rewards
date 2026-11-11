@echo off
setlocal
cd /d "%~dp0"
title Easy Rewards - publish source to GitHub
where git >nul 2>nul
if errorlevel 1 (
 echo Git for Windows is not installed. Download https://git-scm.com/downloads/win
 pause
 exit /b 1
)
where py >nul 2>nul
if errorlevel 1 (
 echo Python Launcher not found. Use Python 3.11.
 pause
 exit /b 1
)
echo.
echo This will publish a NEW GitHub BRANCH, not replace main.
echo Repository: 9akarena8-bit/easy-rewards
set /p CONFIRM=Type YES and press Enter to proceed: 
if /i not "%CONFIRM%"=="YES" exit /b 0
py -3.11 tools\publish_github.py
if errorlevel 1 echo Upload did not finish. Check the error above.
pause
