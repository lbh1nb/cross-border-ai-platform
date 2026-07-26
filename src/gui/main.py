"""GUI 入口。

启动 PySide6 桌面应用。

用法：
    python -m src.gui.main

打包后：
    双击 跨境电商AI运营中台.exe
"""

from __future__ import annotations

import os
import sys
from pathlib import Path


# .env 空模板：首次运行时写入 exe 同目录，用户在 GUI 配置页填写后自动覆盖
_ENV_TEMPLATE = """# ============ 飞书应用凭证 ============
FEISHU_APP_ID=
FEISHU_APP_SECRET=

# ============ 飞书多维表格 ============
FEISHU_BITABLE_APP_TOKEN=
FEISHU_TENANT_DOMAIN=
FEISHU_TABLE_ID_SELECTION=
FEISHU_TABLE_ID_LISTING=
FEISHU_TABLE_ID_DAILY_REPORT=
FEISHU_TABLE_ID_INVENTORY=
FEISHU_TABLE_ID_COLLECTION_CONFIG=

# ============ 飞书机器人 ============
FEISHU_WEBHOOK_URL=
FEISHU_CHAT_ID=

# ============ 飞书审批流（GUI 审批流管理页一键启用后自动写入） ============
FEISHU_APPROVAL_CODE=
FEISHU_APPROVAL_APPROVER_OPEN_ID=
FEISHU_APPROVAL_NODE_ID=

# ============ 业务配置 ============
INVENTORY_ALERT_DAYS=14
PURCHASE_APPROVAL_THRESHOLD=5000
DATA_RETENTION_DAYS=3

# ============ 日志 ============
LOG_LEVEL=INFO
"""


# 打包模式下，先把 exe 同目录加入 sys.path 并切换工作目录，
# 这样 src 模块和 .env 文件都能在 exe 同目录被正确找到。
# 开发模式（python -m src.gui.main）不受影响。
if getattr(sys, "frozen", False):
    _exe_dir = Path(sys.executable).resolve().parent
    sys.path.insert(0, str(_exe_dir))
    os.chdir(_exe_dir)
    # 首次运行时自动创建空 .env 模板，让用户在 GUI 配置页填写
    _env_file = _exe_dir / ".env"
    if not _env_file.exists():
        _env_file.write_text(_ENV_TEMPLATE, encoding="utf-8")

from PySide6.QtWidgets import QApplication

from src.gui.main_window import MainWindow


def main() -> None:
    """启动 GUI 应用。"""
    app = QApplication(sys.argv)
    app.setApplicationName("跨境电商 AI 运营中台")
    app.setOrganizationName("AI Operations")

    # 全局样式：现代简约白底 + 卡片化 + 圆角阴影
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f5f7fa;
        }
        QWidget#sidebar {
            background-color: #ffffff;
            border-right: 1px solid #e4e7ed;
        }
        QListWidget {
            background-color: #ffffff;
            color: #303133;
            font-size: 14px;
            border: none;
            outline: none;
            padding: 8px 0;
        }
        QListWidget::item {
            padding: 14px 20px;
            border: none;
            margin: 2px 8px;
            border-radius: 6px;
            color: #606266;
        }
        QListWidget::item:selected {
            background-color: #ecf5ff;
            color: #3498db;
            font-weight: 600;
        }
        QListWidget::item:hover {
            background-color: #f5f7fa;
            color: #303133;
        }
        QStackedWidget {
            background-color: #f5f7fa;
        }
        QLabel {
            font-size: 14px;
            color: #303133;
        }
        QLineEdit, QSpinBox, QDoubleSpinBox, QComboBox {
            padding: 6px 10px;
            font-size: 14px;
            border: 1px solid #dcdfe6;
            border-radius: 4px;
            background-color: #ffffff;
            color: #303133;
            selection-background-color: #ecf5ff;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus, QComboBox:focus {
            border: 1px solid #3498db;
        }
        QPushButton {
            padding: 8px 18px;
            font-size: 14px;
            border: none;
            border-radius: 6px;
            background-color: #3498db;
            color: white;
        }
        QPushButton:hover {
            background-color: #2980b9;
        }
        QPushButton:pressed {
            background-color: #21618c;
        }
        QPushButton:disabled {
            background-color: #c0c4cc;
            color: #f5f7fa;
        }
        QPushButton[danger="true"] {
            background-color: #e74c3c;
        }
        QPushButton[danger="true"]:hover {
            background-color: #c0392b;
        }
        QTableWidget {
            background-color: #ffffff;
            alternate-background-color: #fafafa;
            gridline-color: #ebeef5;
            font-size: 13px;
            border: 1px solid #ebeef5;
            border-radius: 4px;
        }
        QTableWidget::item {
            padding: 6px;
        }
        QHeaderView::section {
            background-color: #fafafa;
            color: #606266;
            padding: 8px 6px;
            border: none;
            border-right: 1px solid #ebeef5;
            border-bottom: 1px solid #ebeef5;
            font-size: 13px;
            font-weight: 600;
        }
        QTextEdit {
            font-family: Consolas, 'Courier New', monospace;
            font-size: 12px;
            background-color: #fafafa;
            color: #303133;
            border: 1px solid #ebeef5;
            border-radius: 4px;
            padding: 8px;
        }
        QTabWidget::pane {
            border: 1px solid #ebeef5;
            border-radius: 4px;
            background-color: #ffffff;
            margin-top: -1px;
        }
        QTabBar::tab {
            background-color: #f5f7fa;
            color: #606266;
            padding: 8px 16px;
            border: 1px solid #ebeef5;
            border-bottom: none;
            border-top-left-radius: 4px;
            border-top-right-radius: 4px;
            margin-right: 2px;
        }
        QTabBar::tab:selected {
            background-color: #ffffff;
            color: #3498db;
            border-bottom: 2px solid #3498db;
        }
        QTabBar::tab:hover:!selected {
            background-color: #ecf5ff;
        }
        QGroupBox {
            font-size: 14px;
            font-weight: 600;
            color: #303133;
            border: 1px solid #ebeef5;
            border-radius: 8px;
            margin-top: 12px;
            padding-top: 16px;
            background-color: #ffffff;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
            color: #303133;
        }
        QScrollBar:vertical {
            background: transparent;
            width: 8px;
            margin: 0;
        }
        QScrollBar::handle:vertical {
            background: #c0c4cc;
            border-radius: 4px;
            min-height: 30px;
        }
        QScrollBar::handle:vertical:hover {
            background: #909399;
        }
        QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
            height: 0;
        }
        QScrollBar:horizontal {
            background: transparent;
            height: 8px;
            margin: 0;
        }
        QScrollBar::handle:horizontal {
            background: #c0c4cc;
            border-radius: 4px;
            min-width: 30px;
        }
        QScrollBar::handle:horizontal:hover {
            background: #909399;
        }
        QScrollBar::add-line:horizontal, QScrollBar::sub-line:horizontal {
            width: 0;
        }
        QScrollArea {
            background: transparent;
            border: none;
        }
        QScrollArea > QWidget > QWidget {
            background: transparent;
        }
        QComboBox QAbstractItemView {
            background-color: #ffffff;
            color: #303133;
            selection-background-color: #ecf5ff;
            selection-color: #3498db;
            border: 1px solid #dcdfe6;
            outline: none;
        }
        QCheckBox {
            color: #303133;
            spacing: 6px;
        }
        QCheckBox::indicator {
            width: 16px;
            height: 16px;
            border: 1px solid #dcdfe6;
            border-radius: 3px;
            background-color: #ffffff;
        }
        QCheckBox::indicator:checked {
            background-color: #3498db;
            border: 1px solid #3498db;
        }
        QRadioButton {
            color: #303133;
            spacing: 6px;
        }
        QRadioButton::indicator {
            width: 14px;
            height: 14px;
            border: 1px solid #dcdfe6;
            border-radius: 7px;
            background-color: #ffffff;
        }
        QRadioButton::indicator:checked {
            background-color: #3498db;
            border: 2px solid #ffffff;
            outline: 1px solid #3498db;
        }
        QMenu {
            background-color: #ffffff;
            color: #303133;
            border: 1px solid #ebeef5;
            border-radius: 4px;
            padding: 4px;
        }
        QMenu::item {
            padding: 6px 24px;
            border-radius: 4px;
        }
        QMenu::item:selected {
            background-color: #ecf5ff;
            color: #3498db;
        }
        QToolTip {
            background-color: #303133;
            color: #ffffff;
            border: none;
            border-radius: 4px;
            padding: 4px 8px;
        }
        QStatusBar {
            background-color: #ffffff;
            color: #606266;
            border-top: 1px solid #ebeef5;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
