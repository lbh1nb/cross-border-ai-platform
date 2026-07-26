"""PyInstaller 打包脚本。

把整个项目打包成单个 exe，用户双击即可启动 GUI，无需安装 Python 环境。

用法：
    python scripts/build_exe.py

输出：
    dist/跨境电商AI运营中台.exe（约 80-120MB）

前置条件：
    pip install pyinstaller PySide6
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent


def build_exe() -> bool:
    """打包成 exe。"""
    print("=" * 60)
    print("  PyInstaller 打包工具")
    print("=" * 60)

    # 清理旧的构建产物
    dist_dir = PROJECT_ROOT / "dist"
    build_dir = PROJECT_ROOT / "build"
    spec_file = PROJECT_ROOT / "cross-border-ai-platform.spec"

    for path in [dist_dir, build_dir]:
        if path.exists():
            print(f"  清理 {path.name}...")
            shutil.rmtree(path, ignore_errors=True)

    # 构建命令
    cmd = [
        sys.executable,
        "-m",
        "PyInstaller",
        "--noconfirm",
        "--onefile",
        "--windowed",  # 不显示控制台窗口
        "--name", "跨境电商AI运营中台",
        # 入口
        str(PROJECT_ROOT / "src" / "gui" / "main.py"),
        # 把 src 加入搜索路径，并收集所有子模块（避免打包后找不到 src.xxx）
        "--paths", str(PROJECT_ROOT / "src"),
        "--collect-submodules", "src",
        # 隐式导入（PyInstaller 自带 PySide6 hook，会自动收集 QtCore/QtGui/QtWidgets 依赖）
        "--hidden-import", "PySide6.QtCore",
        "--hidden-import", "PySide6.QtGui",
        "--hidden-import", "PySide6.QtWidgets",
        "--hidden-import", "httpx",
        "--hidden-import", "apscheduler",
        "--hidden-import", "apscheduler.schedulers.background",
        "--hidden-import", "apscheduler.triggers.cron",
        "--hidden-import", "apscheduler.jobstores.sqlalchemy",
        "--hidden-import", "apscheduler.executors.pool",
        "--hidden-import", "loguru",
        "--hidden-import", "pydantic",
        "--hidden-import", "pydantic_settings",
        # 工作目录
        "--distpath", str(dist_dir),
        "--workpath", str(build_dir),
        "--specpath", str(PROJECT_ROOT),
    ]

    print(f"  执行打包命令...")
    print(f"  工作目录: {PROJECT_ROOT}")
    print(f"  输出目录: {dist_dir}")
    print()

    result = subprocess.run(cmd, cwd=str(PROJECT_ROOT))

    if result.returncode == 0:
        exe_path = dist_dir / "跨境电商AI运营中台.exe"
        if exe_path.exists():
            size_mb = exe_path.stat().st_size / (1024 * 1024)
            print()
            print("=" * 60)
            print(f"  ✅ 打包成功！")
            print(f"  文件: {exe_path}")
            print(f"  大小: {size_mb:.1f} MB")
            print("=" * 60)
            print()
            print("  使用方法：")
            print("  1. 把 跨境电商AI运营中台.exe 复制到目标电脑")
            print("  2. 双击运行即可启动 GUI")
            print("  3. 首次运行会自动读取同目录下的 .env 配置")
            return True

    print()
    print("  ❌ 打包失败，请检查上方错误信息")
    return False


if __name__ == "__main__":
    success = build_exe()
    sys.exit(0 if success else 1)
