# 跨境电商 AI 运营中台 - 一键安装开机自启动
# 双击 scripts\安装.bat 即可运行
# 业务用户无需执行任何命令，全部自动化

param()
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  跨境电商 AI 运营中台 - 一键安装" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

# 检查 Python 虚拟环境
$pythonExe = Join-Path $projectRoot ".venv\Scripts\python.exe"
$pythonwExe = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonExe)) {
    Write-Host "[错误] 未找到 Python 虚拟环境: $pythonExe" -ForegroundColor Red
    Write-Host "       请联系 IT/运维人员先执行: pip install -e ." -ForegroundColor Yellow
    Read-Host "按回车键退出"
    exit 1
}

# ============================================================
# 步骤1：创建飞书业务视图（销售总览/预警看板/选品决策）
# ============================================================
Write-Host "[步骤 1/3] 创建飞书业务视图..." -ForegroundColor Yellow
$initViewsScript = Join-Path $projectRoot "scripts\init_views.py"
if (Test-Path $initViewsScript) {
    & $pythonExe $initViewsScript
    if ($LASTEXITCODE -ne 0) {
        Write-Host "[警告] 视图创建部分失败，但不影响后续流程" -ForegroundColor Yellow
        Write-Host "       可稍后手动打开飞书表格查看，视图可能已部分创建" -ForegroundColor Gray
    }
} else {
    Write-Host "[跳过] 未找到 init_views.py 脚本" -ForegroundColor Gray
}
Write-Host ""

# ============================================================
# 步骤2：安装开机自启快捷方式
# ============================================================
Write-Host "[步骤 2/3] 安装开机自启..." -ForegroundColor Yellow
$scriptPath = Join-Path $projectRoot "scripts\start_scheduler.py"
$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "AI-Operations-Platform.lnk"

try {
    $shell = New-Object -ComObject WScript.Shell
    $shortcut = $shell.CreateShortcut($shortcutPath)
    $shortcut.TargetPath = $pythonwExe
    $shortcut.Arguments = $scriptPath
    $shortcut.WorkingDirectory = $projectRoot
    $shortcut.WindowStyle = 7
    $shortcut.Description = "跨境电商 AI 运营中台 - 调度器"
    $shortcut.Save()
    Write-Host "[完成] 开机自启已安装" -ForegroundColor Green
} catch {
    $errMsg = $_.Exception.Message
    Write-Host "[错误] 快捷方式创建失败: $errMsg" -ForegroundColor Red
    Read-Host "按回车键退出"
    exit 1
}
Write-Host ""

# ============================================================
# 步骤3：启动后台调度器
# ============================================================
Write-Host "[步骤 3/3] 启动后台调度器..." -ForegroundColor Yellow
Start-Process -FilePath $pythonwExe -ArgumentList $scriptPath -WorkingDirectory $projectRoot -WindowStyle Hidden
Start-Sleep -Seconds 2
Write-Host "[完成] 调度器已在后台启动" -ForegroundColor Green
Write-Host ""

# ============================================================
# 安装完成摘要
# ============================================================
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  安装完成！系统已全部就绪" -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Write-Host "  自动运行的定时任务：" -ForegroundColor Yellow
Write-Host "    - 选品采集:    工作日 09:00（多平台增量同步）" -ForegroundColor White
Write-Host "    - 库存检查:    每 30 分钟（更新预警等级）" -ForegroundColor White
Write-Host "    - 日报生成:    每天 18:00（第4周实现）" -ForegroundColor White
Write-Host "    - 数据清理:    每 3 天 02:00（删除旧数据）" -ForegroundColor White
Write-Host ""
Write-Host "  业务用户使用方式：" -ForegroundColor Yellow
Write-Host "    打开飞书多维表格，切换到以下视图即可：" -ForegroundColor White
Write-Host "    - 销售日报表 -> '销售总览' 视图" -ForegroundColor White
Write-Host "    - 库存预警表 -> '预警看板' 视图" -ForegroundColor White
Write-Host "    - 选品池表   -> '选品决策' 视图" -ForegroundColor White
Write-Host ""
Write-Host "  日志文件: logs\app.log" -ForegroundColor Gray
Write-Host "  停止方法: 任务管理器 -> 结束 pythonw.exe" -ForegroundColor Gray
Write-Host "  卸载方法: 双击 scripts\卸载.bat" -ForegroundColor Gray
Write-Host ""
Read-Host "按回车键退出"
