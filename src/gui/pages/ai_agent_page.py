"""AI Agent 页面：选品分析 + 数据洞察 + 双 Agent 联动 三 Tab 可视化操作入口。

功能：
1. Tab1「选品分析」：输入品类名，点击按钮启动选品 Agent
2. Tab2「数据洞察」：选择日期，点击按钮手动触发数据洞察 Agent
   - 默认每日 18:00 由定时任务自动执行
   - 业务用户可在此 Tab 主动重跑或补跑指定日期
3. Tab3「双 Agent 联动」（v0.7.0 新增）：
   - 场景①：选品 → Listing 联动（一键跑通选品+Listing 优化）
   - 场景②：洞察 → 选品复盘（粘贴洞察结果触发复盘）

设计思想：
- 业务用户无需写代码，点按钮就能运行 AI Agent
- Agent 在后台线程执行，不阻塞 UI
- 执行过程透明，用户能看到 Agent 的每一步操作
"""

from __future__ import annotations

from datetime import datetime, timedelta

from PySide6.QtCore import QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDateEdit,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.config import settings
from src.observability.logger import get_logger

logger = get_logger()


# 默认品类列表（与采集配置表保持一致）
_DEFAULT_CATEGORIES = [
    "家居收纳",
    "厨房用品",
    "户外家具",
    "办公家具",
    "卧室家具",
]


# ============================================================
# 后台线程：选品分析 Agent
# ============================================================


class _AgentWorkerThread(QThread):
    """后台运行选品 Agent 的线程。

    避免 Agent 执行（可能耗时 30-60 秒）阻塞 UI。
    """

    # 信号：日志消息（UI 追加到日志框）
    log_message = Signal(str)
    # 信号：Agent 完成（传递结果字典）
    finished_result = Signal(dict)

    def __init__(self, category: str) -> None:
        super().__init__()
        self._category = category

    def run(self) -> None:
        """线程入口：运行选品 Agent。"""
        try:
            self.log_message.emit(f"🚀 启动选品分析 Agent，品类：{self._category}")
            self.log_message.emit("⏳ 正在初始化 LLM 和工具...")

            from src.ai.agents.selection_agent import run_selection_agent

            self.log_message.emit("🤖 Agent 开始执行（可能需要 30-60 秒）...")
            result = run_selection_agent(self._category)

            if result.get("success"):
                self.log_message.emit("✅ Agent 执行完成！")
                self.log_message.emit(f"\n{result.get('agent_output', '')}")
            else:
                self.log_message.emit(f"❌ Agent 执行失败：{result.get('error', '')}")

            self.finished_result.emit(result)

        except Exception as e:
            error_msg = str(e)
            logger.error("Agent 线程异常: {}", error_msg, exc_info=True)
            self.log_message.emit(f"❌ 线程异常：{error_msg}")
            self.finished_result.emit({
                "success": False,
                "error": error_msg,
                "category": self._category,
            })


# ============================================================
# 后台线程：数据洞察 Agent
# ============================================================


class _InsightWorkerThread(QThread):
    """后台运行数据洞察 Agent 的线程。

    数据洞察 Agent 默认由定时任务每日 18:00 自动触发，
    业务用户也可在 GUI 主动触发（重跑/补跑）。
    """

    log_message = Signal(str)
    finished_result = Signal(dict)

    def __init__(self, target_date: str = "") -> None:
        super().__init__()
        self._target_date = target_date

    def run(self) -> None:
        """线程入口：运行数据洞察 Agent。"""
        try:
            date_desc = self._target_date if self._target_date else "昨天"
            self.log_message.emit(f"🚀 启动数据洞察 Agent，分析日期：{date_desc}")
            self.log_message.emit("⏳ 正在初始化 LLM 和工具...")

            from src.ai.agents.insight_agent import run_insight_agent

            self.log_message.emit("🤖 Agent 开始执行（可能需要 30-60 秒）...")
            self.log_message.emit("   流程：拉数据 → LLM 三维度分析 → 写回表格 + 推送日报卡片")
            result = run_insight_agent(self._target_date)

            if result.get("success"):
                self.log_message.emit("✅ Agent 执行完成！")
                self.log_message.emit(f"\n{result.get('agent_output', '')}")
            else:
                self.log_message.emit(f"❌ Agent 执行失败：{result.get('error', '')}")

            self.finished_result.emit(result)

        except Exception as e:
            error_msg = str(e)
            logger.error("数据洞察 Agent 线程异常: {}", error_msg, exc_info=True)
            self.log_message.emit(f"❌ 线程异常：{error_msg}")
            self.finished_result.emit({
                "success": False,
                "error": error_msg,
                "target_date": self._target_date,
            })


# ============================================================
# 后台线程：双 Agent 联动（v0.7.0 新增）
# ============================================================


class _OrchestrationWorkerThread(QThread):
    """后台运行双 Agent 联动的线程。

    支持两个场景：
    - 场景①：选品 → Listing 联动（默认）
    - 场景②：洞察 → 选品复盘（通过 is_review=True 触发）
    """

    log_message = Signal(str)
    finished_result = Signal(dict)

    def __init__(
        self,
        category: str = "",
        is_review: bool = False,
        top_priority: str = "",
        action_items: list | None = None,
    ) -> None:
        super().__init__()
        self._category = category
        self._is_review = is_review
        self._top_priority = top_priority
        self._action_items = action_items or []

    def run(self) -> None:
        """线程入口：运行双 Agent 联动。"""
        try:
            from src.ai.orchestrator import (
                run_insight_to_selection_review,
                run_selection_to_listing,
            )

            # 进度回调
            def on_progress(msg: str, ctx: dict) -> None:
                self.log_message.emit(f"   → {msg}（状态={ctx.get('state')}）")

            if self._is_review:
                self.log_message.emit(
                    f"🚀 启动场景②：洞察 → 选品复盘"
                )
                self.log_message.emit(
                    f"   top_priority: {self._top_priority[:50]}..."
                )
                result = run_insight_to_selection_review(
                    top_priority=self._top_priority,
                    action_items=self._action_items,
                    category_hint=self._category,
                    progress_callback=on_progress,
                )
            else:
                self.log_message.emit(
                    f"🚀 启动场景①：选品 → Listing 联动，品类={self._category}"
                )
                self.log_message.emit(
                    "   流程：选品 Agent → 写入 Listing 库 → Listing Agent 优化"
                )
                result = run_selection_to_listing(
                    category=self._category,
                    progress_callback=on_progress,
                )

            if result.success:
                self.log_message.emit("✅ 联动执行完成！")
                self.log_message.emit(f"   摘要：{result.summary}")
            else:
                self.log_message.emit(f"❌ 联动执行失败：{result.summary}")

            self.finished_result.emit({
                "success": result.success,
                "summary": result.summary,
                "scenario": result.scenario,
                "state": result.state,
                "duration_seconds": result.duration_seconds,
            })

        except Exception as e:
            error_msg = str(e)
            logger.error(
                "双 Agent 联动线程异常: {}", error_msg, exc_info=True
            )
            self.log_message.emit(f"❌ 线程异常：{error_msg}")
            self.finished_result.emit({
                "success": False,
                "error": error_msg,
            })


# ============================================================
# Tab3：双 Agent 联动（v0.7.0 新增）
# ============================================================


class _OrchestrationTab(QWidget):
    """双 Agent 联动 Tab 页。

    提供两个场景入口：
    - 场景①：选品 → Listing 联动（输入品类，一键跑通选品+Listing 优化）
    - 场景②：洞察 → 选品复盘（输入 top_priority 和 action_items，触发复盘）
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker_thread: _OrchestrationWorkerThread | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 说明
        hint = QLabel(
            "双 Agent 联动会自动串联两个 Agent，无需人工切换：\n"
            "场景① 选品→Listing：选品 Agent 输出爆款候选 → 自动写入 Listing 库 → "
            "Listing Agent 生成优化文案（标题/五点描述/关键词）\n"
            "场景② 洞察→选品复盘：洞察发现爆款关键词 → 触发选品 Agent 重跑对应品类\n\n"
            "💡 未配置 API Key 时联动仍可跑通（Listing Agent 用 Mock 兜底模板化优化），"
            "接入 Key 后自动切换真实 LLM。"
        )
        hint.setStyleSheet(
            "color: #606266; font-size: 13px; background: #f4f4f5; "
            "padding: 12px; border-radius: 6px; border-left: 3px solid #9c27b0;"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 场景①：选品 → Listing
        scene1_label = QLabel("🔗 场景① 选品 → Listing 联动")
        scene1_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #9c27b0; margin-top: 8px;"
        )
        layout.addWidget(scene1_label)

        scene1_layout = QHBoxLayout()
        scene1_layout.setSpacing(8)

        cat_label = QLabel("选品品类：")
        cat_label.setStyleSheet("font-size: 13px; font-weight: 600;")
        scene1_layout.addWidget(cat_label)

        self.scene1_category = QComboBox()
        self.scene1_category.addItems(_DEFAULT_CATEGORIES)
        self.scene1_category.setEditable(True)
        self.scene1_category.setStyleSheet(
            "QComboBox { padding: 6px 12px; border: 1px solid #dcdfe6; "
            "border-radius: 4px; }"
            "QComboBox:hover { border-color: #9c27b0; }"
        )
        scene1_layout.addWidget(self.scene1_category)

        scene1_layout.addStretch()

        self.scene1_run_btn = QPushButton("🚀 启动联动")
        self.scene1_run_btn.setStyleSheet(
            "QPushButton { background-color: #9c27b0; color: white; "
            "padding: 8px 20px; border: none; border-radius: 4px; "
            "font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background-color: #b156cc; }"
            "QPushButton:disabled { background-color: #d3a6dc; }"
        )
        self.scene1_run_btn.clicked.connect(self._on_run_scene1)
        scene1_layout.addWidget(self.scene1_run_btn)

        layout.addLayout(scene1_layout)

        # 场景②：洞察 → 选品复盘
        scene2_label = QLabel("🔄 场景② 洞察 → 选品复盘")
        scene2_label.setStyleSheet(
            "font-size: 14px; font-weight: 700; color: #ff9800; margin-top: 12px;"
        )
        layout.addWidget(scene2_label)

        scene2_layout = QVBoxLayout()
        scene2_layout.setSpacing(6)

        priority_layout = QHBoxLayout()
        priority_label = QLabel("洞察 top_priority：")
        priority_label.setStyleSheet("font-size: 13px;")
        priority_layout.addWidget(priority_label)
        self.scene2_priority = QTextEdit()
        self.scene2_priority.setPlaceholderText(
            "粘贴数据洞察 Agent 输出的 top_priority 文本..."
        )
        self.scene2_priority.setMaximumHeight(50)
        self.scene2_priority.setStyleSheet(
            "QTextEdit { padding: 4px 8px; border: 1px solid #dcdfe6; "
            "border-radius: 4px; font-size: 13px; }"
        )
        priority_layout.addWidget(self.scene2_priority)
        scene2_layout.addLayout(priority_layout)

        actions_layout = QHBoxLayout()
        actions_label = QLabel("行动建议（每行一条）：")
        actions_label.setStyleSheet("font-size: 13px;")
        actions_layout.addWidget(actions_label)
        self.scene2_actions = QTextEdit()
        self.scene2_actions.setPlaceholderText(
            "粘贴 action_items，每行一条...\n"
            "（含「复盘」「选品」「爆款」「上升」「增长」关键词才会触发）"
        )
        self.scene2_actions.setMaximumHeight(70)
        self.scene2_actions.setStyleSheet(
            "QTextEdit { padding: 4px 8px; border: 1px solid #dcdfe6; "
            "border-radius: 4px; font-size: 13px; }"
        )
        actions_layout.addWidget(self.scene2_actions)
        scene2_layout.addLayout(actions_layout)

        review_cat_layout = QHBoxLayout()
        review_cat_label = QLabel("复盘品类：")
        review_cat_label.setStyleSheet("font-size: 13px;")
        review_cat_layout.addWidget(review_cat_label)
        self.scene2_category = QComboBox()
        self.scene2_category.addItems(_DEFAULT_CATEGORIES)
        self.scene2_category.setEditable(True)
        self.scene2_category.setStyleSheet(
            "QComboBox { padding: 6px 12px; border: 1px solid #dcdfe6; "
            "border-radius: 4px; }"
            "QComboBox:hover { border-color: #ff9800; }"
        )
        review_cat_layout.addWidget(self.scene2_category)
        review_cat_layout.addStretch()

        self.scene2_run_btn = QPushButton("🔍 触发复盘")
        self.scene2_run_btn.setStyleSheet(
            "QPushButton { background-color: #ff9800; color: white; "
            "padding: 8px 20px; border: none; border-radius: 4px; "
            "font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background-color: #ffa726; }"
            "QPushButton:disabled { background-color: #ffb74d; }"
        )
        self.scene2_run_btn.clicked.connect(self._on_run_scene2)
        review_cat_layout.addWidget(self.scene2_run_btn)

        scene2_layout.addLayout(review_cat_layout)
        layout.addLayout(scene2_layout)

        # 执行日志
        log_label = QLabel("📋 联动执行日志：")
        log_label.setStyleSheet(
            "font-size: 14px; font-weight: 600; margin-top: 8px;"
        )
        layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; "
            "font-family: 'Consolas', 'Courier New', monospace; "
            "font-size: 13px; padding: 8px; border: 1px solid #3c3c3c; "
            "border-radius: 4px; }"
        )
        self.log_text.setPlaceholderText(
            "选择场景后点击按钮启动联动...\n\n"
            "场景① 流程：\n"
            "1. 选品 Agent 抓取+分析+写入选品池\n"
            "2. 把 top_picks 写入 Listing 库（状态=待优化）\n"
            "3. Listing Agent 优化文案+写回 Listing 库+推送卡片\n\n"
            "场景② 流程：\n"
            "1. 检查 top_priority 和 action_items 是否含复盘关键词\n"
            "2. 命中则触发选品 Agent 重跑对应品类"
        )
        layout.addWidget(self.log_text, stretch=1)

    def _on_run_scene1(self) -> None:
        """点击场景①「启动联动」按钮。"""
        category = self.scene1_category.currentText().strip()
        if not category:
            self.log_text.append("❌ 请输入或选择品类")
            return

        self.scene1_run_btn.setEnabled(False)
        self.scene1_run_btn.setText("⏳ 联动运行中...")
        self.scene2_run_btn.setEnabled(False)
        self.log_text.clear()
        self.log_text.append(
            f"🚀 启动场景①：选品 → Listing 联动，品类={category}"
        )

        self._worker_thread = _OrchestrationWorkerThread(category=category)
        self._worker_thread.log_message.connect(self._on_log_message)
        self._worker_thread.finished_result.connect(self._on_finished)
        self._worker_thread.start()

    def _on_run_scene2(self) -> None:
        """点击场景②「触发复盘」按钮。"""
        top_priority = self.scene2_priority.toPlainText().strip()
        actions_text = self.scene2_actions.toPlainText().strip()
        category = self.scene2_category.currentText().strip()

        if not top_priority:
            self.log_text.append("❌ 请粘贴洞察 top_priority 文本")
            return

        action_items = [
            line.strip() for line in actions_text.split("\n") if line.strip()
        ]

        self.scene2_run_btn.setEnabled(False)
        self.scene2_run_btn.setText("⏳ 复盘运行中...")
        self.scene1_run_btn.setEnabled(False)
        self.log_text.clear()
        self.log_text.append("🚀 启动场景②：洞察 → 选品复盘")

        self._worker_thread = _OrchestrationWorkerThread(
            category=category,
            is_review=True,
            top_priority=top_priority,
            action_items=action_items,
        )
        self._worker_thread.log_message.connect(self._on_log_message)
        self._worker_thread.finished_result.connect(self._on_finished)
        self._worker_thread.start()

    def _on_log_message(self, message: str) -> None:
        """收到日志消息，追加到日志框。"""
        self.log_text.append(message)

    def _on_finished(self, result: dict) -> None:
        """联动执行完成。"""
        self.scene1_run_btn.setEnabled(True)
        self.scene1_run_btn.setText("🚀 启动联动")
        self.scene2_run_btn.setEnabled(True)
        self.scene2_run_btn.setText("🔍 触发复盘")


# ============================================================
# Tab1：选品分析
# ============================================================


class _SelectionAgentTab(QWidget):
    """选品分析 Agent Tab 页。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker_thread: _AgentWorkerThread | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 说明
        hint = QLabel(
            "选品分析 Agent 会自动完成：抓取商品数据 → LLM 分析市场容量/竞争强度/利润空间 → "
            "保存结果到多维表格 + 推送报告到飞书群。\n"
            "运行前请确保已配置 ANTHROPIC_API_KEY 或 OPENAI_API_KEY。"
        )
        hint.setStyleSheet(
            "color: #606266; font-size: 13px; background: #f4f4f5; "
            "padding: 12px; border-radius: 6px; border-left: 3px solid #409eff;"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 输入区
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        input_label = QLabel("选择品类：")
        input_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        input_layout.addWidget(input_label)

        self.category_combo = QComboBox()
        self.category_combo.addItems(_DEFAULT_CATEGORIES)
        self.category_combo.setEditable(True)
        self.category_combo.setStyleSheet(
            "QComboBox { padding: 6px 12px; border: 1px solid #dcdfe6; border-radius: 4px; }"
            "QComboBox:hover { border-color: #409eff; }"
        )
        input_layout.addWidget(self.category_combo, stretch=1)

        self.run_btn = QPushButton("🚀 运行 Agent")
        self.run_btn.setStyleSheet(
            "QPushButton { background-color: #409eff; color: white; "
            "padding: 8px 20px; border: none; border-radius: 4px; "
            "font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background-color: #66b1ff; }"
            "QPushButton:disabled { background-color: #a0cfff; }"
        )
        self.run_btn.clicked.connect(self._on_run_agent)
        input_layout.addWidget(self.run_btn)

        layout.addLayout(input_layout)

        # 执行日志
        log_label = QLabel("📋 执行日志：")
        log_label.setStyleSheet("font-size: 14px; font-weight: 600; margin-top: 8px;")
        layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; "
            "font-family: 'Consolas', 'Courier New', monospace; "
            "font-size: 13px; padding: 8px; border: 1px solid #3c3c3c; "
            "border-radius: 4px; }"
        )
        self.log_text.setPlaceholderText(
            "点击「运行 Agent」开始执行...\n\n"
            "Agent 执行流程：\n"
            "1. 抓取指定品类的商品数据\n"
            "2. 调用 LLM 分析商品数据\n"
            "3. 保存结果到飞书多维表格\n"
            "4. 推送报告到飞书群"
        )
        layout.addWidget(self.log_text, stretch=1)

        # 结果表格（显示 top picks）
        self.result_table = QTableWidget()
        self.result_table.setColumnCount(4)
        self.result_table.setHorizontalHeaderLabels(
            ["ASIN", "商品名称", "推荐理由", "利润空间"]
        )
        self.result_table.horizontalHeader().setSectionResizeMode(
            QHeaderView.ResizeMode.Stretch
        )
        self.result_table.setStyleSheet(
            "QTableWidget { border: 1px solid #ebeef5; border-radius: 4px; }"
            "QHeaderView::section { background-color: #f5f7fa; font-weight: 600; }"
        )
        self.result_table.setVisible(False)
        layout.addWidget(self.result_table)

    def _on_run_agent(self) -> None:
        """点击「运行 Agent」按钮。"""
        category = self.category_combo.currentText().strip()
        if not category:
            self.log_text.append("❌ 请输入品类名称")
            return

        # 检查 API Key
        if not settings.anthropic_api_key and not settings.openai_api_key:
            self.log_text.append(
                "❌ 未配置 API Key，请先到「系统配置」页填写 "
                "ANTHROPIC_API_KEY 或 OPENAI_API_KEY"
            )
            return

        # 禁用按钮，防止重复点击
        self.run_btn.setEnabled(False)
        self.run_btn.setText("⏳ Agent 运行中...")
        self.log_text.clear()
        self.result_table.setVisible(False)

        # 启动后台线程
        self._worker_thread = _AgentWorkerThread(category)
        self._worker_thread.log_message.connect(self._on_log_message)
        self._worker_thread.finished_result.connect(self._on_agent_finished)
        self._worker_thread.start()

    def _on_log_message(self, message: str) -> None:
        """收到日志消息，追加到日志框。"""
        self.log_text.append(message)

    def _on_agent_finished(self, result: dict) -> None:
        """Agent 执行完成。"""
        self.run_btn.setEnabled(True)
        self.run_btn.setText("🚀 运行 Agent")

        # 如果成功，尝试解析 top_picks 显示到表格
        if result.get("success"):
            self._try_display_top_picks(result.get("agent_output", ""))

    def _try_display_top_picks(self, agent_output: str) -> None:
        """尝试从 Agent 输出中提取 top_picks 显示到表格。

        Agent 输出可能包含 JSON，尝试解析。如果解析失败就隐藏表格。
        """
        import json
        import re

        # 尝试从输出中提取 JSON
        json_match = re.search(r"\{[\s\S]*\}", agent_output)
        if not json_match:
            return

        try:
            analysis = json.loads(json_match.group())
            top_picks = analysis.get("top_picks", [])
            if not top_picks:
                return

            self.result_table.setRowCount(len(top_picks))
            for i, pick in enumerate(top_picks):
                self.result_table.setItem(i, 0, QTableWidgetItem(pick.get("asin", "")))
                self.result_table.setItem(i, 1, QTableWidgetItem(pick.get("name", "")))
                self.result_table.setItem(i, 2, QTableWidgetItem(pick.get("reason", "")))
                self.result_table.setItem(
                    i, 3, QTableWidgetItem(pick.get("estimated_margin", ""))
                )

            self.result_table.setVisible(True)
        except (json.JSONDecodeError, KeyError):
            # 解析失败，隐藏表格（Agent 输出可能不是 JSON 格式）
            self.result_table.setVisible(False)


# ============================================================
# Tab2：数据洞察
# ============================================================


class _InsightAgentTab(QWidget):
    """数据洞察 Agent Tab 页。

    业务用户可在此手动触发数据洞察 Agent（重跑/补跑）。
    每日 18:00 由定时任务自动执行，无需人工干预。
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker_thread: _InsightWorkerThread | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(12)

        # 说明
        hint = QLabel(
            "数据洞察 Agent 会自动完成：拉取昨日销售+库存数据 → LLM 三维度分析"
            "（销量/广告/库存）→ 写回表格 AI 洞察字段 + 推送日报卡片到飞书群。\n"
            "默认每日 18:00 由定时任务自动执行，本页面用于手动重跑或补跑指定日期。\n"
            "运行前请确保已配置 ANTHROPIC_API_KEY 或 OPENAI_API_KEY。"
        )
        hint.setStyleSheet(
            "color: #606266; font-size: 13px; background: #f4f4f5; "
            "padding: 12px; border-radius: 6px; border-left: 3px solid #67c23a;"
        )
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 输入区
        input_layout = QHBoxLayout()
        input_layout.setSpacing(8)

        date_label = QLabel("分析日期：")
        date_label.setStyleSheet("font-size: 14px; font-weight: 600;")
        input_layout.addWidget(date_label)

        self.date_edit = QDateEdit()
        yesterday = datetime.now().date() - timedelta(days=1)
        self.date_edit.setDate(yesterday)
        self.date_edit.setCalendarPopup(True)
        self.date_edit.setDisplayFormat("yyyy-MM-dd")
        self.date_edit.setStyleSheet(
            "QDateEdit { padding: 6px 12px; border: 1px solid #dcdfe6; border-radius: 4px; }"
            "QDateEdit:hover { border-color: #67c23a; }"
        )
        input_layout.addWidget(self.date_edit)

        self.use_yesterday_btn = QPushButton("📋 设为昨天")
        self.use_yesterday_btn.setStyleSheet(
            "QPushButton { background-color: #909399; color: white; "
            "padding: 6px 12px; border: none; border-radius: 4px; "
            "font-size: 13px; }"
            "QPushButton:hover { background-color: #a6a9ad; }"
        )
        self.use_yesterday_btn.clicked.connect(self._on_set_yesterday)
        input_layout.addWidget(self.use_yesterday_btn)

        input_layout.addStretch()

        self.run_btn = QPushButton("🚀 立即运行")
        self.run_btn.setStyleSheet(
            "QPushButton { background-color: #67c23a; color: white; "
            "padding: 8px 20px; border: none; border-radius: 4px; "
            "font-size: 14px; font-weight: 600; }"
            "QPushButton:hover { background-color: #85ce61; }"
            "QPushButton:disabled { background-color: #b3e19d; }"
        )
        self.run_btn.clicked.connect(self._on_run_agent)
        input_layout.addWidget(self.run_btn)

        layout.addLayout(input_layout)

        # 执行日志
        log_label = QLabel("📋 执行日志：")
        log_label.setStyleSheet("font-size: 14px; font-weight: 600; margin-top: 8px;")
        layout.addWidget(log_label)

        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setStyleSheet(
            "QTextEdit { background-color: #1e1e1e; color: #d4d4d4; "
            "font-family: 'Consolas', 'Courier New', monospace; "
            "font-size: 13px; padding: 8px; border: 1px solid #3c3c3c; "
            "border-radius: 4px; }"
        )
        self.log_text.setPlaceholderText(
            "点击「立即运行」开始执行...\n\n"
            "Agent 执行流程：\n"
            "1. 拉取销售日报表 + 库存预警表数据\n"
            "2. 调用 LLM 从销量/广告/库存三维度分析\n"
            "3. 把 AI 洞察写回销售日报表\n"
            "4. 推送日报卡片到飞书群\n\n"
            "提示：每日 18:00 会自动执行，无需手动触发。"
        )
        layout.addWidget(self.log_text, stretch=1)

    def _on_set_yesterday(self) -> None:
        """点击「设为昨天」按钮。"""
        yesterday = datetime.now().date() - timedelta(days=1)
        self.date_edit.setDate(yesterday)

    def _on_run_agent(self) -> None:
        """点击「立即运行」按钮。"""
        # 获取日期
        target_date = self.date_edit.date().toString("yyyy-MM-dd")

        # 检查 API Key
        if not settings.anthropic_api_key and not settings.openai_api_key:
            self.log_text.append(
                "❌ 未配置 API Key，请先到「系统配置」页填写 "
                "ANTHROPIC_API_KEY 或 OPENAI_API_KEY"
            )
            return

        # 禁用按钮，防止重复点击
        self.run_btn.setEnabled(False)
        self.run_btn.setText("⏳ Agent 运行中...")
        self.log_text.clear()

        # 启动后台线程
        self._worker_thread = _InsightWorkerThread(target_date)
        self._worker_thread.log_message.connect(self._on_log_message)
        self._worker_thread.finished_result.connect(self._on_agent_finished)
        self._worker_thread.start()

    def _on_log_message(self, message: str) -> None:
        """收到日志消息，追加到日志框。"""
        self.log_text.append(message)

    def _on_agent_finished(self, result: dict) -> None:
        """Agent 执行完成。"""
        self.run_btn.setEnabled(True)
        self.run_btn.setText("🚀 立即运行")


# ============================================================
# 主页面：Tab 容器
# ============================================================


class AiAgentPage(QWidget):
    """AI Agent 页面：选品分析 + 数据洞察 + 双 Agent 联动 三 Tab。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 顶部标题区
        title_bar = QWidget()
        title_bar.setFixedHeight(56)
        title_bar.setStyleSheet("background-color: #ffffff;")
        title_layout = QHBoxLayout(title_bar)
        title_layout.setContentsMargins(24, 0, 24, 0)

        title = QLabel("🤖 AI Agent")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #303133;"
        )
        title_layout.addWidget(title)
        title_layout.addStretch()

        # API Key 状态指示（顶部右侧）
        self.api_status_label = QLabel()
        self.api_status_label.setStyleSheet("font-size: 12px;")
        title_layout.addWidget(self.api_status_label)

        layout.addWidget(title_bar)

        # Tab 切换区
        self.tabs = QTabWidget()
        self.tabs.setStyleSheet(
            "QTabBar::tab { padding: 10px 20px; font-size: 14px; font-weight: 600; }"
            "QTabBar::tab:selected { color: #409eff; border-bottom: 2px solid #409eff; }"
            "QTabBar::tab:!selected { color: #606266; }"
            "QTabWidget::pane { border: none; }"
        )

        self.selection_tab = _SelectionAgentTab()
        self.insight_tab = _InsightAgentTab()
        self.orchestration_tab = _OrchestrationTab()

        self.tabs.addTab(self.selection_tab, "🎯 选品分析")
        self.tabs.addTab(self.insight_tab, "📊 数据洞察")
        self.tabs.addTab(self.orchestration_tab, "🔗 双 Agent 联动")

        layout.addWidget(self.tabs, stretch=1)

        # 初始化 API Key 状态
        self._update_api_status()

    def _update_api_status(self) -> None:
        """更新 API Key 配置状态提示。"""
        has_anthropic = bool(settings.anthropic_api_key)
        has_openai = bool(settings.openai_api_key)

        if has_anthropic:
            self.api_status_label.setText("✅ 已配置 Anthropic API Key")
            self.api_status_label.setStyleSheet(
                "color: #67c23a; font-size: 12px;"
            )
        elif has_openai:
            self.api_status_label.setText("✅ 已配置 OpenAI API Key")
            self.api_status_label.setStyleSheet(
                "color: #67c23a; font-size: 12px;"
            )
        else:
            self.api_status_label.setText(
                "⚠️ 未配置 API Key，请到「系统配置」页填写"
            )
            self.api_status_label.setStyleSheet(
                "color: #e67e22; font-size: 12px;"
            )
