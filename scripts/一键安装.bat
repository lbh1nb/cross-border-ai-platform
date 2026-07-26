@echo off
chcp 65001 >nul 2>&1
title 跨境电商 AI 运营中台 - 一键安装

echo ============================================================
echo   跨境电商 AI 运营中台 - 一键安装
echo ============================================================
echo.

REM 检查 Python 是否已安装
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未检测到 Python，请先安装 Python 3.11+
    echo 下载地址: https://www.python.org/downloads/
    echo 安装时请勾选 "Add Python to PATH"
    echo.
    pause
    exit /b 1
)

REM 检查虚拟环境
if not exist ".venv\Scripts\python.exe" (
    echo [步骤 1/4] 创建虚拟环境...
    python -m venv .venv
    if errorlevel 1 (
        echo [错误] 虚拟环境创建失败
        pause
        exit /b 1
    )
    echo [成功] 虚拟环境已创建
) else (
    echo [跳过] 虚拟环境已存在
)
echo.

REM 安装依赖
echo [步骤 2/4] 安装项目依赖...
.venv\Scripts\pip.exe install -e ".[dev]" -q
if errorlevel 1 (
    echo [错误] 依赖安装失败，请检查网络连接
    pause
    exit /b 1
)
echo [成功] 依赖安装完成
echo.

REM 检查 .env 配置
if not exist ".env" (
    echo [步骤 3/4] 启动配置向导...
    echo 未检测到 .env 配置文件，将启动配置向导引导你完成配置。
    echo.
    .venv\Scripts\python.exe scripts\setup_wizard.py
    if errorlevel 1 (
        echo [错误] 配置向导执行失败
        pause
        exit /b 1
    )
) else (
    echo [跳过] .env 配置已存在
    echo 如需重新配置，请删除 .env 文件后重新运行本脚本
)
echo.

REM 配置开机自启 + 启动调度器
echo [步骤 4/4] 配置开机自启并启动调度器...
powershell -ExecutionPolicy Bypass -File scripts\install.ps1
if errorlevel 1 (
    echo [警告] 开机自启配置失败，可手动启动调度器
    echo 手动启动命令: .venv\Scripts\python.exe scripts\start_scheduler.py
) else (
    echo [成功] 开机自启已配置，调度器已启动
)
echo.

echo ============================================================
echo   安装完成！
echo ============================================================
echo.
echo 项目已配置完成，电脑会自动后台运行：
echo   - 工作日 9:00 自动采集多平台选品
echo   - 每 30 分钟更新库存预警
echo   - 每 3 天凌晨 2:00 自动清理旧数据
echo.
echo 业务用户只需打开飞书多维表格查看数据。
echo.
echo 如需测试机器人告警，运行: python scripts\test_bot.py
echo 如需测试卡片发送，运行: python scripts\test_cards.py
echo.
pause
