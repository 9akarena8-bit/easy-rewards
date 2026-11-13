@echo off
cd /d "%~dp0.."
py -3.11 -B -m unittest discover -s merchant_service/tests -v
pause
