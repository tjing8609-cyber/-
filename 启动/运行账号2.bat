@echo off
chcp 65001 >nul
REM 知到自动播放 - 账号2（智能启动器）
cd /d "%~dp0.."
python code\zhidao_launcher.py --account 启动\account2.json
if errorlevel 1 (
    echo.
    echo [错误] Python执行失败，请检查：
    echo 1. 是否已安装Python
    echo 2. Python是否已添加到PATH环境变量
    echo 3. 是否安装了必要的依赖包（selenium等）
    echo.
)
pause
