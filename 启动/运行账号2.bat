@echo off
cd /d "%~dp0.."
python code\zhidao_launcher.py --account 启动\account2.json
if %ERRORLEVEL% NEQ 0 pause
