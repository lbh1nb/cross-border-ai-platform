"""审批流管理面板。

业务用户在飞书审批后台创建审批定义后，在 GUI 里：
1. 点"扫描审批定义" → 自动列出企业内所有审批定义
2. 选中一个 → 自动查询字段 ID 和节点 ID
3. 选择审批人 → 点"启用" → 自动写入 .env

全程不接触任何代码。
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QSplitter,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.gui.services.approval_service import (
    enable_approval,
    extract_approval_config,
    list_approval_definitions,
    query_approval_detail,
)
from src.gui.services.env_service import get_config_value


class ScanApprovalsThread(QThread):
    """后台扫描审批定义的线程（避免阻塞 UI）。"""

    result_ready = Signal(list)

    def run(self) -> None:
        items = list_approval_definitions()
        self.result_ready.emit(items)


class QueryApprovalDetailThread(QThread):
    """后台查询单个审批定义详情的线程。"""

    result_ready = Signal(dict)

    def __init__(self, approval_code: str) -> None:
        super().__init__()
        self._code = approval_code

    def run(self) -> None:
        detail = query_approval_detail(self._code)
        self.result_ready.emit(detail)


class ApprovalPage(QWidget):
    """审批流管理面板。"""

    def __init__(self) -> None:
        super().__init__()
        self._scan_thread: ScanApprovalsThread | None = None
        self._query_thread: QueryApprovalDetailThread | None = None
        self._current_detail: dict = {}
        self._init_ui()

    def _init_ui(self) -> None:
        """初始化 UI。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题
        title = QLabel("审批流管理")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        hint = QLabel(
            '操作流程：1. 在飞书审批后台创建审批 → '
            '2. 点"扫描审批定义" → '
            '3. 选中审批 → '
            '4. 点"启用此审批流"\n'
            "启用后，每天 10:00 自动扫描选品池，金额超阈值时创建审批实例。"
        )
        hint.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 按钮区
        btn_layout = QHBoxLayout()
        self.scan_btn = QPushButton("🔍 扫描审批定义")
        self.scan_btn.clicked.connect(self._on_scan)
        btn_layout.addWidget(self.scan_btn)

        self.enable_btn = QPushButton("✅ 启用此审批流")
        self.enable_btn.clicked.connect(self._on_enable)
        self.enable_btn.setEnabled(False)
        btn_layout.addWidget(self.enable_btn)

        btn_layout.addStretch()

        # 当前状态
        self.status_label = QLabel("当前状态：未配置")
        self.status_label.setStyleSheet("font-size: 14px; color: #e74c3c;")
        btn_layout.addWidget(self.status_label)

        layout.addLayout(btn_layout)

        # 主内容区：左侧列表 + 右侧详情
        splitter = QSplitter(Qt.Orientation.Horizontal)

        # 左侧审批定义列表
        left = QWidget()
        left_layout = QVBoxLayout(left)
        left_layout.setContentsMargins(0, 0, 0, 0)
        left_label = QLabel("审批定义列表")
        left_label.setStyleSheet("font-weight: bold; padding: 4px;")
        left_layout.addWidget(left_label)
        self.approval_list = QListWidget()
        self.approval_list.itemClicked.connect(self._on_select)
        left_layout.addWidget(self.approval_list)
        splitter.addWidget(left)

        # 右侧详情
        right = QWidget()
        right_layout = QVBoxLayout(right)
        right_layout.setContentsMargins(0, 0, 0, 0)
        right_label = QLabel("审批定义详情")
        right_label.setStyleSheet("font-weight: bold; padding: 4px;")
        right_layout.addWidget(right_label)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        right_layout.addWidget(self.detail_text)
        splitter.addWidget(right)

        splitter.setSizes([400, 600])
        layout.addWidget(splitter, stretch=1)

        self._refresh_status()

    def _refresh_status(self) -> None:
        """刷新当前审批流配置状态。"""
        code = get_config_value("FEISHU_APPROVAL_CODE", "")
        approver = get_config_value("FEISHU_APPROVAL_APPROVER_OPEN_ID", "")
        node = get_config_value("FEISHU_APPROVAL_NODE_ID", "")
        if code and approver and node:
            self.status_label.setText("当前状态：已启用 ✓")
            self.status_label.setStyleSheet("font-size: 14px; color: #2ecc71;")
        else:
            self.status_label.setText("当前状态：未配置")
            self.status_label.setStyleSheet("font-size: 14px; color: #e74c3c;")

    def _on_scan(self) -> None:
        """扫描审批定义。"""
        self.scan_btn.setEnabled(False)
        self.scan_btn.setText("🔍 扫描中...")
        self.approval_list.clear()
        self.approval_list.addItem(QListWidgetItem("正在扫描企业内审批定义..."))

        self._scan_thread = ScanApprovalsThread()
        self._scan_thread.result_ready.connect(self._on_scan_done)
        self._scan_thread.start()

    def _on_scan_done(self, items: list) -> None:
        """扫描完成回调。"""
        self.scan_btn.setEnabled(True)
        self.scan_btn.setText("🔍 扫描审批定义")
        self.approval_list.clear()

        if not items:
            self.approval_list.addItem(QListWidgetItem("（未扫描到任何审批定义）"))
            return

        for item in items:
            code = item.get("approval_code", "")
            name = item.get("approval_name", "未命名")
            status = "启用" if str(item.get("status", "")) == "1" else "停用"
            display = f"{name}\n  Code: {code}\n  状态: {status}"
            list_item = QListWidgetItem(display)
            list_item.setData(Qt.ItemDataRole.UserRole, code)
            self.approval_list.addItem(list_item)

    def _on_select(self, item: QListWidgetItem) -> None:
        """选中审批定义，查询详情。"""
        code = item.data(Qt.ItemDataRole.UserRole)
        if not code:
            return

        self.enable_btn.setEnabled(False)
        self.detail_text.setPlainText("正在查询审批定义详情...")

        self._query_thread = QueryApprovalDetailThread(code)
        self._query_thread.result_ready.connect(self._on_detail_done)
        self._query_thread.start()

    def _on_detail_done(self, detail: dict) -> None:
        """详情查询完成回调。"""
        self._current_detail = detail
        if not detail:
            self.detail_text.setPlainText("查询失败")
            return

        config = extract_approval_config(detail)
        text = (
            f"审批名称: {config['approval_name']}\n"
            f"审批 Code: {config['approval_code']}\n"
            f"审批节点 ID: {config['node_id']}\n"
            f"表单字段数: {config['field_count']}\n"
            f"\n--- 原始详情 ---\n"
            f"{json.dumps(detail, ensure_ascii=False, indent=2)[:2000]}"
        )
        self.detail_text.setPlainText(text)

        if config["node_id"]:
            self.enable_btn.setEnabled(True)
        else:
            QMessageBox.warning(
                self, "提示", "未找到审批节点，请检查审批定义是否配置了审批人节点。"
            )

    def _on_enable(self) -> None:
        """启用选中的审批流。"""
        if not self._current_detail:
            return

        config = extract_approval_config(self._current_detail)
        approval_code = config["approval_code"]
        node_id = config["node_id"]

        # 审批人优先用 .env 已有的，没有则提示去配置页填
        approver_open_id = get_config_value("FEISHU_APPROVAL_APPROVER_OPEN_ID", "")
        if not approver_open_id:
            QMessageBox.warning(
                self,
                "缺少审批人",
                '请先到"配置"页面填写"审批人 Open ID"，'
                "或通过手机号查询（在配置页审批人栏填写 ou_ 开头的 open_id）。",
            )
            return

        confirm = QMessageBox.question(
            self,
            "确认启用",
            f"确认启用审批流？\n\n"
            f"审批名称: {config['approval_name']}\n"
            f"审批 Code: {approval_code}\n"
            f"审批节点: {node_id}\n"
            f"审批人: {approver_open_id}\n\n"
            f"启用后，每天 10:00 自动扫描选品池，金额超阈值时创建审批实例。",
        )
        if confirm != QMessageBox.StandardButton.Yes:
            return

        success = enable_approval(approval_code, node_id, approver_open_id)
        if success:
            QMessageBox.information(self, "成功", "审批流已启用！配置已写入 .env。")
            self._refresh_status()
        else:
            QMessageBox.critical(self, "失败", "启用失败，请查看日志。")
