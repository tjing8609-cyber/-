@echo off
cd /d "%~dp0"
python tools\quality_check.py
if %ERRORLEVEL% NEQ 0 pause
