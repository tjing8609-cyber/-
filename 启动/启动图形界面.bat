@echo off
chcp 65001 > nul
title 知到自动播放器 - 图形化界面
echo.
echo ====================================
echo   知到自动播放器 - 图形化界面
echo ====================================
echo.
echo 正在启动图形化界面...
echo.

cd /d "%~dp0"
python gui_launcher.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 启动失败！可能原因：
    echo    1. 未安装Python
    echo    2. Python不在系统PATH中
    echo.
    pause
)
