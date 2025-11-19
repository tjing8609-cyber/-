@echo off
REM 知到自动播放 - 账号3（智能启动器）
cd /d C:\Users\16224\Desktop\zhidao
call conda activate study312
python code\zhidao_launcher.py --account 启动\account3.json
pause
