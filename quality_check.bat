@echo off
cd /d "%~dp0"
python tools\run_tests.py
if %ERRORLEVEL% NEQ 0 pause
