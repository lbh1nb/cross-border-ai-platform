"""PyInstaller 打包脚本：把项目打包成单个 exe。

打包后企业无需安装 Python 环境即可运行配置向导。

打包产物：
    dist/cross-border-ai-platform.exe  (单文件可执行)
    dist/cross-border-ai-platform/     (目录形式，启动更快)

用法：
    # 方式1：用 Python 脚本打包
    python scripts/build_exe.py

    # 方式2：用 PyInstaller 直接打包
    pyinstaller scripts/cross-border-ai-platform.spec

注意：
    打包前需先安装 pyinstaller：
        pip install pyinstaller

    打包后的 exe 仍需要 .env 配置文件才能运行。
    企业拿到 exe + .env 模板 + scripts/ 目录即可使用。
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

_PROJECT_ROOT = Path(__file__).resolve().parent.parent


def check_pyinstaller() -> bool:
    """检查 pyinstaller 是否已安装。"""
    try:
        import PyInstaller  # noqa: F401
        return True
    except ImportError:
        print("  pyinstaller 未安装，正在安装...")
        result = subprocess.run(
            [sys.executable, "-m", "pip", "install", "pyinstaller"],
            capture_output=True,
        )
        return result.returncode == 0


def build_exe() -> bool:
    """用 PyInstaller 打包。"""
    print("=" * 60)
    print("  PyInstaller 打包工具")
    print("=" * 60)
    print()

    if not check_pyinstaller():
        print("  [错误] pyinstaller 安装失败")
        return False

    # 入口脚本：配置向导
    entry_script = _PROJECT_ROOT / "scripts" / "setup_wizard.py"
    if not entry_script.exists():
        print(f"  [错误] 入口脚本不存在: {entry_script}")
        return False

    # 清理旧产物
    build_dir = _PROJECT_ROOT / "build"
    dist_dir = _PROJECT_ROOT / "dist"
    spec_file = _PROJECT_ROOT / "setup_wizard.spec"

    for path in [build_dir, dist_dir, spec_file]:
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path)
            else:
                path.unlink()

    # PyInstaller 命令
    cmd = [
        sys.executable, "-m", "PyInstaller",
        "--noconfirm",
        "--clean",
        "--name", "cross-border-ai-setup",
        # 单文件模式（启动慢但分发方便）
        "--onefile",
        # 控制台模式（向导需要交互输入）
        "--console",
        # 添加数据文件
        "--add-data", f".env.example;.",
        # hidden imports（动态导入的模块）
        "--hidden-import", "src.feishu.bitable",
        "--hidden-import", "src.feishu.auth",
        "--hidden-import", "src.feishu.sync_service",
        "--hidden-import", "src.feishu.field_mapping",
        "--hidden-import", "src.feishu.feishu_bot",
        "--hidden-import", "src.feishu.card_templates",
        "--hidden-import", "src.feishu.card_callback",
        "--hidden-import", "src.feishu.application_bot",
        "--hidden-import", "src.feishu.init_tables",
        "--hidden-import", "src.feishu.config_table",
        "--hidden-import", "src.feishu.permission",
        "--hidden-import", "src.feishu.table_schema",
        "--hidden-import", "src.pipeline.collectors",
        "--hidden-import", "src.pipeline.cleaners",
        "--hidden-import", "src.scheduler.scheduler",
        "--hidden-import", "src.scheduler.tasks",
        "--hidden-import", "src.scheduler.triggers",
        "--hidden-import", "src.scheduler.cleanup_task",
        "--hidden-import", "src.scheduler.inventory_alert",
        # 收集子包
        "--collect-submodules", "src",
        # 入口脚本
        str(entry_script),
    ]

    print("  正在打包（可能需要 1-2 分钟）...")
    result = subprocess.run(cmd, cwd=_PROJECT_ROOT)

    if result.returncode != 0:
        print("  [错误] 打包失败")
        return False

    exe_path = dist_dir / "cross-border-ai-setup.exe"
    if not exe_path.exists():
        print(f"  [错误] 打包产物不存在: {exe_path}")
        return False

    size_mb = exe_path.stat().st_size / (1024 * 1024)
    print()
    print("=" * 60)
    print("  打包成功！")
    print("=" * 60)
    print()
    print(f"  产物路径: {exe_path}")
    print(f"  文件大小: {size_mb:.1f} MB")
    print()
    print("  使用方法：")
    print("  1. 把 cross-border-ai-setup.exe 复制到目标电脑")
    print("  2. 双击运行")
    print("  3. 按向导提示完成配置")
    print()
    print("  注意：")
    print("  - .env 文件会在向导运行时自动生成")
    print("  - 飞书业务表/视图会在向导中自动创建")
    print("  - 仍需 IT 人员在飞书开放平台创建应用并获取凭证")
    return True


if __name__ == "__main__":
    success = build_exe()
    sys.exit(0 if success else 1)
