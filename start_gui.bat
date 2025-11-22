@echo off
cd /d "%~dp0"
python auto_start.py
if %ERRORLEVEL% NEQ 0 pause
