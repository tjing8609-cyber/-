@echo off
cd /d "%~dp0"
python 图形化启动器.py
if %ERRORLEVEL% NEQ 0 pause
