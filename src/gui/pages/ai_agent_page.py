"""AI Agent 页面：选品分析 Agent 的可视化操作入口。

功能：
1. 输入品类名，点击"运行 Agent"启动选品分析
2. 实时显示 Agent 执行日志（思考过程、工具调用、结果）
3. 运行完成后展示分析结果

设计思想：
- 业务用户无需写代码，点按钮就能运行 AI Agent
- Agent 在后台线程执行，不阻塞 UI
- 执行过程透明，用户能看到 Agent 的每一步操作
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
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


class AiAgentPage(QWidget):
    """AI Agent 页面：选品分析 Agent 的可视化操作。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._worker_thread: _AgentWorkerThread | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 标题
        title = QLabel("🤖 AI Agent · 选品分析")
        title.setStyleSheet(
            "font-size: 20px; font-weight: 700; color: #303133;"
        )
        layout.addWidget(title)

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

        # API Key 状态提示
        self.api_status_label = QLabel()
        self.api_status_label.setStyleSheet("font-size: 12px; padding: 4px;")
        layout.addWidget(self.api_status_label)
        self._update_api_status()

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

    def _update_api_status(self) -> None:
        """更新 API Key 配置状态提示。"""
        has_anthropic = bool(settings.anthropic_api_key)
        has_openai = bool(settings.openai_api_key)

        if has_anthropic:
            self.api_status_label.setText("✅ 已配置 Anthropic API Key")
            self.api_status_label.setStyleSheet(
                "color: #67c23a; font-size: 12px; padding: 4px;"
            )
        elif has_openai:
            self.api_status_label.setText("✅ 已配置 OpenAI API Key")
            self.api_status_label.setStyleSheet(
                "color: #67c23a; font-size: 12px; padding: 4px;"
            )
        else:
            self.api_status_label.setText(
                "⚠️ 未配置 API Key，请到「系统配置」页填写 ANTHROPIC_API_KEY 或 OPENAI_API_KEY"
            )
            self.api_status_label.setStyleSheet(
                "color: #e67e22; font-size: 12px; padding: 4px;"
            )

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
                ))

            self.result_table.setVisible(True)
        except (json.JSONDecodeError, KeyError):
            # 解析失败，隐藏表格（Agent 输出可能不是 JSON 格式）
            self.result_table.setVisible(False)
