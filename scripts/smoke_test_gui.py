"""GUI 烟雾测试。

启动 GUI 主窗口、切换所有页面，验证不崩溃。
3 秒后自动退出。

用法：
    python scripts/smoke_test_gui.py
"""

from __future__ import annotations

import sys
from pathlib import Path

# 把项目根目录加入搜索路径（main_window 内部用 `from src.xxx` 导入）
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))

from PySide6.QtCore import QTimer  # noqa: E402
from PySide6.QtWidgets import QApplication  # noqa: E402

from src.gui.main_window import MainWindow  # noqa: E402


def main() -> None:
    """启动 GUI 主窗口并切换所有页面，3 秒后退出。"""
    app = QApplication(sys.argv)
    window = MainWindow()
    window.show()

    # 切换所有页面，验证页面切换不崩溃
    stack = window.stack
    page_count = stack.count()
    print(f"主窗口加载了 {page_count} 个页面")

    def switch_pages() -> None:
        """逐一切换页面。"""
        for i in range(page_count):
            stack.setCurrentIndex(i)
            app.processEvents()
            print(f"  切换到页面 {i + 1}/{page_count}: {stack.widget(i).__class__.__name__}")
        print("所有页面切换成功，3 秒后退出...")

    QTimer.singleShot(200, switch_pages)
    QTimer.singleShot(3000, app.quit)

    sys.exit(app.exec())


if __name__ == "__main__":
    main()
