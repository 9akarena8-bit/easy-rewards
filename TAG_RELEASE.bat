@echo off
setlocal
cd /d "%~dp0"
title Easy Rewards - publish v1.4.2 release
where git >nul 2>nul
if errorlevel 1 (echo Git for Windows is required.& pause & exit /b 1)
echo.
echo Only use AFTER the v1.4.2 pull request has been merged into main.
echo This pushes tag v1.4.2 to GitHub and triggers Windows installer building.
set /p CONFIRM=Type RELEASE to create the tag: 
if /i not "%CONFIRM%"=="RELEASE" exit /b 0
set "TEMP_REPO=%TEMP%\easyrewards_release_%RANDOM%"
git clone --branch main https://github.com/9akarena8-bit/easy-rewards.git "%TEMP_REPO%"
if errorlevel 1 goto error
cd /d "%TEMP_REPO%"
for /f "usebackq delims=" %%v in ("VERSION") do set "VERS=%%v"
if not "%VERS%"=="1.4.2" (echo Wrong version in main: %VERS%&goto error)
git tag v1.4.2
if errorlevel 1 goto error
git push origin v1.4.2
if errorlevel 1 goto error
echo Published tag. See GitHub Actions and Releases.
cd /d "%~dp0"
pause
exit /b 0
:error
cd /d "%~dp0"
echo Release tag was NOT published.
pause
exit /b 1
