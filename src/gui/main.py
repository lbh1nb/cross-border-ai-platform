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

    # 全局样式
    app.setStyleSheet("""
        QMainWindow {
            background-color: #f5f5f5;
        }
        QListWidget {
            background-color: #2c3e50;
            color: white;
            font-size: 14px;
            border: none;
            outline: none;
        }
        QListWidget::item {
            padding: 12px 16px;
            border-bottom: 1px solid #34495e;
        }
        QListWidget::item:selected {
            background-color: #3498db;
            color: white;
        }
        QListWidget::item:hover {
            background-color: #34495e;
        }
        QStackedWidget {
            background-color: #ffffff;
        }
        QLabel {
            font-size: 14px;
        }
        QLineEdit, QSpinBox, QDoubleSpinBox {
            padding: 6px 8px;
            font-size: 14px;
            border: 1px solid #bdc3c7;
            border-radius: 4px;
        }
        QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus {
            border: 2px solid #3498db;
        }
        QPushButton {
            padding: 8px 16px;
            font-size: 14px;
            border: none;
            border-radius: 4px;
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
            background-color: #95a5a6;
        }
        QPushButton[danger="true"] {
            background-color: #e74c3c;
        }
        QPushButton[danger="true"]:hover {
            background-color: #c0392b;
        }
        QTableWidget {
            gridline-color: #ecf0f1;
            font-size: 13px;
        }
        QHeaderView::section {
            background-color: #34495e;
            color: white;
            padding: 6px;
            border: none;
            font-size: 13px;
        }
        QTextEdit {
            font-family: Consolas, 'Courier New', monospace;
            font-size: 12px;
            background-color: #2c3e50;
            color: #ecf0f1;
            border: none;
        }
        QGroupBox {
            font-size: 14px;
            font-weight: bold;
            border: 1px solid #bdc3c7;
            border-radius: 4px;
            margin-top: 12px;
            padding-top: 12px;
        }
        QGroupBox::title {
            subcontrol-origin: margin;
            left: 12px;
            padding: 0 6px;
        }
    """)

    window = MainWindow()
    window.show()
    sys.exit(app.exec())


if __name__ == "__main__":
    main()
