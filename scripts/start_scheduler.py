"""后台启动调度器：用 pythonw.exe 无窗口运行。

此脚本由 install.ps1 调用，也可单独执行。
启动后调度器在后台运行，所有定时任务自动触发。
"""

from __future__ import annotations

import sys
import os

# 切换到项目根目录（pythonw.exe 启动时工作目录可能不对）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)
sys.path.insert(0, project_root)

from src.scheduler.scheduler import SchedulerManager


def main() -> None:
    """后台启动调度器，所有任务自动按 cron 时间触发。"""
    manager = SchedulerManager(blocking=True)
    manager.start()


if __name__ == "__main__":
    main()
