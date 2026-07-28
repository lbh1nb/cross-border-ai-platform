"""主窗口：侧边栏 + 页面切换。

布局：
    +------+--------------------------+
    | 侧边栏 |                          |
    | 向导  |     当前页面内容          |
    | 配置  |                          |
    | 审批  |                          |
    | 任务  |                          |
    | 看板  |                          |
    | 检查  |                          |
    | Agent|                          |
    | 手册  |                          |
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

from src.gui.pages.ai_agent_page import AiAgentPage
from src.gui.pages.approval_page import ApprovalPage
from src.gui.pages.config_page import ConfigPage
from src.gui.pages.dashboard_page import DashboardPage
from src.gui.pages.health_check_page import HealthCheckPage
from src.gui.pages.manual_page import ManualPage
from src.gui.pages.setup_wizard_page import SetupWizardPage
from src.gui.pages.task_page import TaskPage


class MainWindow(QMainWindow):
    """主窗口：侧边栏导航 + 多页面切换。"""

    def __init__(self) -> None:
        super().__init__()
        self.setWindowTitle("跨境电商 AI 运营中台 v0.6.0")
        self.resize(1280, 800)
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
        self.setup_wizard_page = SetupWizardPage()
        self.config_page = ConfigPage()
        self.approval_page = ApprovalPage()
        self.task_page = TaskPage()
        self.dashboard_page = DashboardPage()
        self.health_check_page = HealthCheckPage()
        self.ai_agent_page = AiAgentPage()
        self.manual_page = ManualPage()

        # 顺序必须与侧边栏 items 一致
        self.stack.addWidget(self.setup_wizard_page)
        self.stack.addWidget(self.config_page)
        self.stack.addWidget(self.approval_page)
        self.stack.addWidget(self.task_page)
        self.stack.addWidget(self.dashboard_page)
        self.stack.addWidget(self.health_check_page)
        self.stack.addWidget(self.ai_agent_page)
        self.stack.addWidget(self.manual_page)
        layout.addWidget(self.stack, stretch=1)

        # 向导页"打开系统配置页"按钮 → 切换到配置页
        self.setup_wizard_page._goto_page.connect(self._goto_page)

        self.setCentralWidget(central)

    def _build_sidebar(self) -> QWidget:
        """构建侧边栏（白底浅灰文字，现代简约风格）。"""
        sidebar = QWidget()
        sidebar.setObjectName("sidebar")
        sidebar.setFixedWidth(200)
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        title = QLabel("AI 运营中台")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "background-color: #ffffff; color: #303133; "
            "font-size: 17px; font-weight: 700; padding: 22px 16px; "
            "border-bottom: 1px solid #ebeef5;"
        )
        layout.addWidget(title)

        # 导航菜单
        self.nav = QListWidget()
        self.nav.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        items = [
            "🚀  部署向导",
            "📋  系统配置",
            "✅  审批流管理",
            "⚙️  任务控制",
            "📊  数据看板",
            "🔍  健康检查",
            "🤖  AI Agent",
            "📖  操作手册",
        ]
        for text in items:
            item = QListWidgetItem(text)
            self.nav.addItem(item)
        self.nav.setCurrentRow(0)
        self.nav.currentRowChanged.connect(self._on_nav_changed)
        layout.addWidget(self.nav, stretch=1)

        # 状态栏
        self.status_label = QLabel("●  就绪")
        self.status_label.setStyleSheet(
            "background-color: #ffffff; color: #67c23a; "
            "font-size: 12px; padding: 10px; "
            "border-top: 1px solid #ebeef5;"
        )
        self.status_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.status_label)

        return sidebar

    def _on_nav_changed(self, row: int) -> None:
        """侧边栏切换页面。"""
        self.stack.setCurrentIndex(row)
        # 切换到数据看板时刷新数据
        if row == 4:
            self.dashboard_page.refresh_data()
        # 切换到健康检查页时不自动跑，让用户主动点
        # 切换到 AI Agent 页时刷新 API Key 状态
        if row == 6:
            self.ai_agent_page._update_api_status()
        # 切换到操作手册时重新加载（用户可能改过文件）
        if row == 7:
            self.manual_page._load_manual()

    def _goto_page(self, page_id: str) -> None:
        """从其他页面（如部署向导）跳转到指定页面。

        Args:
            page_id: 页面标识，对应侧边栏的页面
                "wizard" → 部署向导 (0)
                "config" → 系统配置 (1)
                "approval" → 审批流管理 (2)
                "task" → 任务控制 (3)
                "dashboard" → 数据看板 (4)
                "health" → 健康检查 (5)
                "ai_agent" → AI Agent (6)
                "manual" → 操作手册 (7)
        """
        page_map = {
            "wizard": 0,
            "config": 1,
            "approval": 2,
            "task": 3,
            "dashboard": 4,
            "health": 5,
            "ai_agent": 6,
            "manual": 7,
        }
        row = page_map.get(page_id, 0)
        self.nav.setCurrentRow(row)
