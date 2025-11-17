@echo off
REM 知到自动播放 - 账号1（智能启动器）
cd /d C:\Users\16224\Desktop\zhidao
call conda activate study312
python zhidao_launcher.py --account account1.json
pause
