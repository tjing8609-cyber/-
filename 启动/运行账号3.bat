@echo off
cd /d "%~dp0.."
python code\zhidao_launcher.py --account 启动\account3.json
if %ERRORLEVEL% NEQ 0 pause
