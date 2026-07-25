# ============================================================
# TRAE IDE 终端启动脚本（由 TRAE settings.json 自动调用）
# 作用1：修正 PATH，让 python 命令指向 Python 3.12（覆盖 D:\ali\python.exe）
# 作用2：当前目录有 .venv 时自动激活虚拟环境
# ============================================================

# --- 1. 修正 PATH ---
$_py312 = "$env:LOCALAPPDATA\Programs\Python\Python312\Scripts;$env:LOCALAPPDATA\Programs\Python\Python312"
if ($env:PATH -notlike "$_py312;*") {
    $env:PATH = "$_py312;$env:PATH"
}

# --- 2. 自动激活 venv ---
$venvActivate = "$PWD\.venv\Scripts\Activate.ps1"
if (Test-Path $venvActivate) {
    . $venvActivate
}
