@echo off
chcp 65001 >nul 2>&1
title 跨境电商 AI 运营中台 - 一键卸载

echo ============================================================
echo   跨境电商 AI 运营中台 - 一键卸载
echo ============================================================
echo.

echo 即将执行以下操作：
echo   1. 停止正在运行的后台调度器
echo   2. 删除开机自启快捷方式
echo   3. 保留 .env 配置和飞书数据（不删除）
echo.

set /p confirm=确认卸载？(y/n):
if /i not "%confirm%"=="y" (
    echo 已取消卸载
    pause
    exit /b 0
)
echo.

REM 停止调度器进程
echo [步骤 1/2] 停止后台调度器...
taskkill /f /im pythonw.exe >nul 2>&1
if errorlevel 1 (
    echo [信息] 未发现运行中的调度器
) else (
    echo [成功] 调度器已停止
)
echo.

REM 删除开机自启快捷方式
echo [步骤 2/2] 删除开机自启快捷方式...
powershell -ExecutionPolicy Bypass -File scripts\uninstall.ps1
if errorlevel 1 (
    echo [警告] 删除快捷方式失败，可手动删除
) else (
    echo [成功] 开机自启快捷方式已删除
)
echo.

echo ============================================================
echo   卸载完成！
echo ============================================================
echo.
echo 已停止后台调度器并删除开机自启。
echo .env 配置文件和飞书数据已保留。
echo.
echo 如需彻底删除项目，直接删除整个项目文件夹即可。
echo.
pause
