@echo off
chcp 65001 > nul
title 知到自动播放器 - 图形化启动器
echo.
echo =========================================
echo   知到自动播放器 - 图形化启动器 v1.0
echo =========================================
echo.
echo 正在启动图形化界面...
echo.

cd /d "%~dp0"
python 图形化启动器.py

if %ERRORLEVEL% NEQ 0 (
    echo.
    echo ❌ 启动失败！
    echo.
    echo 可能原因：
    echo   1. 未安装Python 3
    echo   2. Python未添加到系统PATH
    echo.
    echo 解决方法：
    echo   1. 访问 https://www.python.org/ 下载并安装Python
    echo   2. 安装时勾选 "Add Python to PATH"
    echo.
    pause
)
