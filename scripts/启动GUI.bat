@echo off
chcp 65001 >nul
title 跨境电商 AI 运营中台
cd /d "%~dp0\.."

REM 检查虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [错误] 未找到虚拟环境，请先运行 scripts\一键安装.bat
    pause
    exit /b 1
)

REM 启动 GUI
echo 正在启动 跨境电商 AI 运营中台...
".venv\Scripts\pythonw.exe" -m src.gui.main

if errorlevel 1 (
    echo.
    echo [启动失败] 请检查日志 logs\app_*.log
    pause
)
