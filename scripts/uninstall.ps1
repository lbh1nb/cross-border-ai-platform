# 跨境电商 AI 运营中台 - 卸载开机自启动
# 双击 scripts\卸载.bat 即可运行

param()
$ErrorActionPreference = "Stop"

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  AI Operations Platform - Uninstall Auto-Start" -ForegroundColor Cyan
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""

$startupDir = [Environment]::GetFolderPath("Startup")
$shortcutPath = Join-Path $startupDir "AI-Operations-Platform.lnk"

if (Test-Path $shortcutPath) {
    Remove-Item $shortcutPath -Force
    Write-Host "[OK] Auto-start shortcut removed" -ForegroundColor Green
} else {
    Write-Host "[INFO] Shortcut not found, may not be installed" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "[STOP] Stopping scheduler process..." -ForegroundColor Yellow
$pythonwProcesses = Get-Process -Name "pythonw" -ErrorAction SilentlyContinue
if ($pythonwProcesses) {
    $pythonwProcesses | Stop-Process -Force
    Write-Host "[OK] Scheduler process stopped" -ForegroundColor Green
} else {
    Write-Host "[INFO] No running scheduler process found" -ForegroundColor Yellow
}

Write-Host ""
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host "  Uninstall complete! Scheduler will not auto-start." -ForegroundColor Green
Write-Host "============================================================" -ForegroundColor Cyan
Write-Host ""
Read-Host "Press Enter to exit"
