# 跨境电商 AI 运营中台 - 一键安装开机自启动
# 双击 scripts\安装.bat 即可运行

param()
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AI Operations Platform - Install Auto-Start" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$projectRoot = Split-Path -Parent $PSScriptRoot
Set-Location $projectRoot

$pythonwExe = Join-Path $projectRoot ".venv\Scripts\pythonw.exe"
if (-not (Test-Path $pythonwExe)) {
    Write-Host "[ERROR] venv not found: $pythonwExe" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

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
    $shortcut.Description = "AI Operations Platform - Scheduler Service"
    $shortcut.Save()
    Write-Host "[OK] Auto-start installed successfully" -ForegroundColor Green
} catch {
    $errMsg = $_.Exception.Message
    Write-Host "[ERROR] Shortcut creation failed: $errMsg" -ForegroundColor Red
    Read-Host "Press Enter to exit"
    exit 1
}

Write-Host ""
Write-Host "  Shortcut: $shortcutPath" -ForegroundColor Gray
Write-Host "  Mode:     Background (pythonw.exe, no window)" -ForegroundColor Gray
Write-Host "  Trigger:  Auto-start on boot" -ForegroundColor Gray
Write-Host ""
Write-Host "  Scheduled Tasks:" -ForegroundColor Yellow
Write-Host "    - Product Collection: Mon-Fri 09:00" -ForegroundColor White
Write-Host "    - Inventory Check:    Every 30 min" -ForegroundColor White
Write-Host "    - Daily Report:       Daily 18:00 (Week 4)" -ForegroundColor White
Write-Host ""
Write-Host "  Data:  Feishu Bitable auto-update" -ForegroundColor Gray
Write-Host "  Log:   logs\app.log" -ForegroundColor Gray
Write-Host ""

Write-Host "[START] Launching scheduler in background..." -ForegroundColor Yellow
Start-Process -FilePath $pythonwExe -ArgumentList $scriptPath -WorkingDirectory $projectRoot -WindowStyle Hidden
Start-Sleep -Seconds 2
Write-Host "[OK] Scheduler started in background" -ForegroundColor Green

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Install complete! Scheduler will auto-start on boot." -ForegroundColor Green
Write-Host "  To stop:   Task Manager -> end pythonw.exe" -ForegroundColor Gray
Write-Host "  To remove: Run scripts\uninstall.ps1" -ForegroundColor Gray
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to exit"
