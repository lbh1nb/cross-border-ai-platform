"""主窗口：侧边栏 + 页面切换。

布局：
    +------+--------------------------+
    | 侧边栏 |                          |
    | 配置  |     当前页面内容          |
    | 审批  |                          |
    | 任务  |                          |
    | 看板  |                          |
    +------+--------------------------+
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMainWindow,
    QStackedWidget,
    QVBoxLayout,
    QWidget,
)

from src.gui.pages.approval_page import ApprovalPage
from src.gui.pages.config_page import ConfigPage
from src.gui.pages.dashboard_page import DashboardPage
from src.gui.pages.task_page import TaskPage


class MainWindow(QMainWindow):
    """主窗口：侧边栏导航 + 多页面切换。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("跨境电商 AI 运营中台")
        self.resize(1200, 750)
        self._init_ui()

    def _init_ui(self) -> None:
        """初始化 UI 布局。"""
        central = QWidget()
        layout = QHBoxLayout(central)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 侧边栏
        sidebar = self._build_sidebar()
        layout.addWidget(sidebar)

        # 页面堆栈
        self.stack = QStackedWidget()
        self.config_page = ConfigPage()
        self.approval_page = ApprovalPage()
        self.task_page = TaskPage()
        self.dashboard_page = DashboardPage()
        self.stack.addWidget(self.config_page)
        self.stack.addWidget(self.approval_page)
        self.stack.addWidget(self.task_page)
        self.stack.addWidget(self.dashboard_page)
        layout.addWidget(self.stack, stretch=1)

        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        """构建侧边栏。"""
        sidebar = QWidget()
        sidebar.setFixedWidth(180)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        title = QLabel("AI 运营中台")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "background-color: #2c3e50; color: #ecf0f1; "
            "font-size: 16px; font-weight: bold; padding: 16px;"
        )
        layout.addWidget(title)

        # 导航菜单
        self.nav = QListWidget()
        items = ["📋 配置", "✅ 审批流管理", "⚙️ 任务控制", "📊 数据看板"]
        for text in items:
            item = QListWidgetItem(text)
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav, stretch=1)

        # 状态栏
        self.status_label = QLabel("● 就绪")
        self.status_label.setStyleSheet(
            "background-color: #2c3e50; color: #2ecc71; "
            "font-size: 12px; padding: 8px;"
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        return sidebar

    def _on_nav_changed(self, row: int) -> None:
        """侧边栏切换页面。"""
        self.stack.setCurrentIndex(row)
        # 切换到数据看板时刷新数据
        if row == 3:
            self.dashboard_page.refresh_data()
