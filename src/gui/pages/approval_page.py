"""审批流管理面板（08-07 重构版）。

支持多审批流规则管理：
1. 显示所有已配置的审批规则列表（表格形式）
2. 新建规则向导：扫描飞书审批定义 → 选择 → 配触发条件 → 保存
3. 启用/禁用/删除规则
4. 触发方式：事件驱动（选品采集完成/库存预警触发时自动匹配）

业务用户全程不接触代码。
"""

from __future__ import annotations

import json

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QComboBox,
    QDialog,
    QDialogButtonBox,
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QSplitter,
    QTableWidget,
    QTableWidgetItem,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.gui.services.approval_rules_service import (
    EVENT_LABELS,
    EVENT_PRODUCT_COLLECTED,
    INVENTORY_CONDITION_FIELDS,
    OPERATOR_LABELS,
    PRODUCT_CONDITION_FIELDS,
    add_rule,
    delete_rule,
    list_rules,
    toggle_rule,
)
from src.gui.services.approval_service import (
    extract_approval_config,
    list_approval_definitions,
    query_approval_detail,
)
from src.gui.services.env_service import get_config_value


# ============ 使用前必读说明（业务用户引导）============
_GUIDE_HTML = """
<h2>📋 审批流管理使用说明</h2>

<p>这个页面用来配置<b>"什么情况下自动发审批卡片给主管"</b>。比如：选品采集时金额超过 5000 美金，自动发一张审批卡片到飞书群，主管点按钮就能通过/拒绝。</p>

<h3>🔴 使用前必读：先在飞书创建"审批定义"</h3>

<p>"审批定义"就是飞书审批中心里的审批表单模板。在用本页面前，必须先在飞书审批后台创建好审批定义，否则本页面扫不到东西。</p>

<h4>第 1 步：在飞书审批后台创建审批定义</h4>
<ol>
    <li>打开 <a href="https://www.feishu.cn/approval">飞书审批后台</a>（用企业管理员账号登录）。</li>
    <li>点"<b>创建审批</b>" → 选"<b>从空白创建</b>"。</li>
    <li>填审批名称（如"高金额选品审批"）和说明。</li>
    <li>设计表单，<b>必须包含以下字段</b>（字段名要完全一致，方便系统自动填值）：
        <table border="1" cellpadding="6">
            <tr><th>字段名</th><th>控件类型</th><th>说明</th></tr>
            <tr><td><b>ASIN</b></td><td>单行文本</td><td>商品 ASIN 编号</td></tr>
            <tr><td><b>商品名称</b></td><td>单行文本</td><td>商品标题</td></tr>
            <tr><td><b>采购金额</b></td><td>数字</td><td>单位：美金</td></tr>
            <tr><td><b>业务类型</b></td><td>单行文本</td><td>如"选品"/"采购"</td></tr>
            <tr><td><b>说明</b></td><td>多行文本</td><td>备注信息</td></tr>
        </table>
    </li>
    <li>配置审批流程：
        <ul>
            <li>添加一个"<b>审批人</b>"节点</li>
            <li>审批人建议先选"<b>自己</b>"（方便测试），上线后再改成真实主管</li>
        </ul>
    </li>
    <li>点"<b>发布</b>" → 审批定义发布成功。</li>
</ol>

<h4>🔍 扫描原理（系统怎么自动找到你在飞书创建的审批）</h4>

<p>你点"➕ 新建审批规则"时，系统会<b>自动调用飞书审批 API</b>，把你企业飞书里所有<b>已发布</b>的审批定义拉过来，列成一张表给你选。整个过程不用手动复制 approval_code。</p>

<p><b>扫描流程</b>（系统自动完成，你只做第 1、6 步）：</p>
<table border="1" cellpadding="6">
    <tr>
        <th>步骤</th>
        <th>谁在做</th>
        <th>做什么</th>
    </tr>
    <tr><td>1</td><td>你</td><td>在飞书审批后台创建审批定义并<b>点"发布"</b>（草稿扫不到）</td></tr>
    <tr><td>2</td><td>你</td><td>回到本页面点"➕ 新建审批规则"</td></tr>
    <tr><td>3</td><td>系统</td><td>用 App ID / App Secret 换取 <code>tenant_access_token</code>（飞书 API 通行证）</td></tr>
    <tr><td>4</td><td>系统</td><td>调用飞书 API <code>POST /approval/v4/approvals</code>，拉取企业内所有已发布的审批定义</td></tr>
    <tr><td>5</td><td>系统</td><td>把审批定义列表显示在弹窗里（含名称和 Code）</td></tr>
    <tr><td>6</td><td>你</td><td>在列表里点选一个审批定义</td></tr>
    <tr><td>7</td><td>系统</td><td>自动查询该审批的<b>表单字段 ID</b> 和<b>审批节点 ID</b>（用于后续自动填表单）</td></tr>
    <tr><td>8</td><td>系统</td><td>把配置写入 .env，规则保存生效</td></tr>
</table>

<p><b>扫不到审批定义的 3 个常见原因</b>（弹窗会自动提示）：</p>
<ol>
    <li><b>审批定义还没发布</b>：飞书审批后台创建后只是草稿，<b>必须点"发布"</b>才能被 API 扫到</li>
    <li><b>应用缺少审批权限</b>：飞书应用没开通 <code>approval:approval</code> 权限（去飞书开放平台 → 你的应用 → 权限管理 → 搜索 <code>approval:approval</code> → 点"开通权限"）</li>
    <li><b>凭证没保存</b>：系统配置页的 App ID / App Secret 没点"💾 保存配置"（系统拿不到 token 就调不了 API）</li>
</ol>

<p style="color:#3498db;">💡 扫不到时不要慌，弹窗会显示这 3 个原因的排查提示。修复后点"🔄 重新扫描"按钮即可再试一次。</p>

<h4>第 2 步：回到本页面创建审批规则</h4>
<ol>
    <li>点上方"<b>➕ 新建审批规则</b>"按钮。</li>
    <li>在弹窗里：
        <ul>
            <li>系统会<b>自动扫描</b>你刚在飞书创建的审批定义，列表里选一个即可（无需手动填 approval_code）</li>
            <li>选触发事件（选品采集完成 / 库存预警触发）</li>
            <li>配触发条件（如：采购金额 &gt; 5000）</li>
            <li>填规则名称和审批人</li>
        </ul>
    </li>
    <li>点"<b>保存规则</b>"。</li>
</ol>

<h4>第 3 步：规则自动生效</h4>
<p>规则保存后默认是"已启用"状态。之后<b>符合条件的事件发生时自动触发审批</b>，不需要人工干预。</p>

<p style="color:#3498db;">💡 可以创建多个规则，比如：选品金额 &gt; 5000 用审批定义 A，库存预警等级 = 紧急用审批定义 B。</p>

<hr style="margin: 20px 0;">
"""


class ScanApprovalsThread(QThread):
    """后台扫描审批定义。"""
    result_ready = Signal(list)
    error_occurred = Signal(str)

    def run(self) -> None:
        try:
            items = list_approval_definitions()
            self.result_ready.emit(items)
        except Exception as e:
            # 关键：异常时也要发信号，否则 GUI 永远卡在"正在扫描..."
            self.error_occurred.emit(f"扫描审批定义失败：{e}")
            self.result_ready.emit([])


class QueryDetailThread(QThread):
    """后台查审批定义详情。"""
    result_ready = Signal(dict)
    error_occurred = Signal(str)

    def __init__(self, approval_code: str) -> None:
        super().__init__()
        self._code = approval_code

    def run(self) -> None:
        try:
            detail = query_approval_detail(self._code)
            self.result_ready.emit(detail)
        except Exception as e:
            self.error_occurred.emit(f"查询审批定义详情失败：{e}")
            self.result_ready.emit({})


class NewRuleDialog(QDialog):
    """新建审批规则对话框（向导式）。

    步骤：
    1. 扫描飞书审批定义 → 列表选一个
    2. 自动查出字段ID和节点ID
    3. 选触发事件（选品采集完成/库存预警触发）
    4. 配触发条件（字段 + 操作符 + 阈值）
    5. 填规则名称 + 审批人 → 保存
    """

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("新建审批规则")
        self.resize(700, 600)
        self._scan_thread: ScanApprovalsThread | None = None
        self._query_thread: QueryDetailThread | None = None
        self._current_detail: dict = {}
        self._init_ui()
        self._auto_scan()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # 标题
        title = QLabel("新建审批规则")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a1a1a;")
        layout.addWidget(title)

        # 步骤1：选审批定义
        step1_label = QLabel("步骤 1：选择飞书审批定义")
        step1_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        layout.addWidget(step1_label)

        btn_row = QHBoxLayout()
        self.rescan_btn = QPushButton("🔄 重新扫描")
        self.rescan_btn.clicked.connect(self._auto_scan)
        btn_row.addWidget(self.rescan_btn)
        btn_row.addStretch()
        layout.addLayout(btn_row)

        self.approval_list = QListWidget()
        self.approval_list.setMaximumHeight(150)
        self.approval_list.itemClicked.connect(self._on_select_approval)
        layout.addWidget(self.approval_list)

        # 步骤2：审批详情
        step2_label = QLabel("步骤 2：审批定义详情（自动填充）")
        step2_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        layout.addWidget(step2_label)
        self.detail_text = QTextEdit()
        self.detail_text.setReadOnly(True)
        self.detail_text.setMaximumHeight(100)
        layout.addWidget(self.detail_text)

        # 步骤3：配规则
        step3_label = QLabel("步骤 3：配置规则")
        step3_label.setStyleSheet("font-weight: bold; color: #2c3e50;")
        layout.addWidget(step3_label)

        form = QFormLayout()
        self.name_input = QLineEdit()
        self.name_input.setPlaceholderText("如：高金额选品审批")
        form.addRow("规则名称：", self.name_input)

        self.event_combo = QComboBox()
        for event_id, label in EVENT_LABELS.items():
            self.event_combo.addItem(label, event_id)
        self.event_combo.currentIndexChanged.connect(self._on_event_change)
        form.addRow("触发事件：", self.event_combo)

        self.field_combo = QComboBox()
        form.addRow("条件字段：", self.field_combo)

        self.operator_combo = QComboBox()
        for op, label in OPERATOR_LABELS.items():
            self.operator_combo.addItem(label, op)
        form.addRow("比较方式：", self.operator_combo)

        self.value_input = QSpinBox()
        self.value_input.setRange(0, 1000000)
        self.value_input.setValue(5000)
        form.addRow("阈值：", self.value_input)

        self.approver_input = QLineEdit()
        self.approver_input.setPlaceholderText("ou_xxxxxxxx（不填则用配置页的默认审批人）")
        form.addRow("审批人 Open ID：", self.approver_input)

        layout.addLayout(form)

        # 按钮
        btns = QDialogButtonBox(
            QDialogButtonBox.StandardButton.Ok | QDialogButtonBox.StandardButton.Cancel
        )
        btns.button(QDialogButtonBox.StandardButton.Ok).setText("保存规则")
        btns.button(QDialogButtonBox.StandardButton.Cancel).setText("取消")
        btns.accepted.connect(self._on_save)
        btns.rejected.connect(self.reject)
        layout.addWidget(btns)

    def _auto_scan(self) -> None:
        """自动扫描审批定义。"""
        self.rescan_btn.setEnabled(False)
        self.rescan_btn.setText("🔄 扫描中...")
        self.approval_list.clear()
        self.approval_list.addItem(QListWidgetItem("正在扫描企业内审批定义..."))
        self._scan_thread = ScanApprovalsThread()
        self._scan_thread.result_ready.connect(self._on_scan_done)
        self._scan_thread.error_occurred.connect(self._on_scan_error)
        self._scan_thread.start()

    def _on_scan_error(self, msg: str) -> None:
        """扫描出错时显示友好提示。"""
        from src.observability.logger import get_logger
        get_logger().error(msg)
        # 在详情区显示错误信息，方便用户排查
        self.detail_text.setPlainText(f"❌ {msg}\n\n请检查：\n1. 系统配置页的飞书凭证是否正确\n2. 是否已点『保存配置』\n3. 应用是否有 approval:approval 权限")

    def _on_scan_done(self, items: list) -> None:
        self.rescan_btn.setEnabled(True)
        self.rescan_btn.setText("🔄 重新扫描")
        self.approval_list.clear()
        if not items:
            self.approval_list.addItem(QListWidgetItem(
                "❌ 未扫描到审批定义\n\n"
                "可能原因：\n"
                "1. 还没在飞书审批后台创建审批定义\n"
                "2. 凭证未配置或无效（去系统配置页检查）\n"
                "3. 应用缺少 approval:approval 权限\n\n"
                "👉 请先按上方『使用前必读』在飞书创建审批定义"
            ))
            return
        for item in items:
            code = item.get("approval_code", "")
            name = item.get("approval_name", "未命名")
            display = f"{name}  （Code: {code[:20]}...）"
            list_item = QListWidgetItem(display)
            list_item.setData(Qt.ItemDataRole.UserRole, code)
            self.approval_list.addItem(list_item)

    def _on_select_approval(self, item: QListWidgetItem) -> None:
        code = item.data(Qt.ItemDataRole.UserRole)
        if not code:
            return
        self.detail_text.setPlainText("正在查询审批定义详情...")
        self._query_thread = QueryDetailThread(code)
        self._query_thread.result_ready.connect(self._on_detail_done)
        self._query_thread.start()

    def _on_detail_done(self, detail: dict) -> None:
        self._current_detail = detail
        if not detail:
            self.detail_text.setPlainText("查询失败")
            return
        config = extract_approval_config(detail)
        text = (
            f"审批名称：{config['approval_name']}\n"
            f"审批 Code：{config['approval_code']}\n"
            f"审批节点 ID：{config['node_id']}\n"
            f"表单字段数：{config['field_count']}"
        )
        self.detail_text.setPlainText(text)

    def _on_event_change(self) -> None:
        """触发事件变化时，更新条件字段选项。"""
        event_id = self.event_combo.currentData()
        self.field_combo.clear()
        fields = (
            PRODUCT_CONDITION_FIELDS
            if event_id == EVENT_PRODUCT_COLLECTED
            else INVENTORY_CONDITION_FIELDS
        )
        for f in fields:
            self.field_combo.addItem(f, f)

    def _on_save(self) -> None:
        """保存规则。"""
        if not self._current_detail:
            QMessageBox.warning(self, "提示", "请先选择一个审批定义。")
            return
        name = self.name_input.text().strip()
        if not name:
            QMessageBox.warning(self, "提示", "请填写规则名称。")
            return

        config = extract_approval_config(self._current_detail)
        approver = self.approver_input.text().strip()
        if not approver:
            approver = get_config_value("FEISHU_APPROVAL_APPROVER_OPEN_ID", "")

        if not approver:
            QMessageBox.warning(
                self, "缺少审批人",
                '请填写审批人 Open ID，或先到"配置"页填默认审批人。',
            )
            return

        if not config["node_id"]:
            QMessageBox.warning(
                self, "提示", "未找到审批节点，请检查审批定义是否配置了审批人节点。"
            )
            return

        rule = {
            "name": name,
            "approval_code": config["approval_code"],
            "approval_name": config["approval_name"],
            "node_id": config["node_id"],
            "approver_open_id": approver,
            "field_ids": config.get("field_ids", {}),
            "trigger_event": self.event_combo.currentData(),
            "condition_field": self.field_combo.currentData(),
            "condition_operator": self.operator_combo.currentData(),
            "condition_value": self.value_input.value(),
            "enabled": True,
        }
        rule_id = add_rule(rule)
        if rule_id:
            QMessageBox.information(self, "成功", f"规则已保存：{name}")
            self.accept()
        else:
            QMessageBox.critical(self, "失败", "保存规则失败，请查看日志。")


class ApprovalPage(QWidget):
    """审批流管理面板（多规则版）。"""

    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        self._load_rules()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题
        title = QLabel("审批流管理")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1a1a1a;")
        layout.addWidget(title)

        # ============ 使用前必读（可折叠的引导区）============
        guide_group = QGroupBox("📖 使用前必读（首次使用请先看这里）")
        guide_group.setStyleSheet(
            "QGroupBox { font-size: 14px; font-weight: 600; color: #303133; "
            "border: 1px solid #ebeef5; border-radius: 8px; "
            "margin-top: 12px; padding-top: 16px; background: #ffffff; }"
            "QGroupBox::title { subcontrol-origin: margin; left: 12px; padding: 0 6px; }"
        )
        guide_layout = QVBoxLayout(guide_group)

        # 引导内容（用 QTextBrowser 渲染 HTML，支持超链接和表格）
        self.guide_browser = QTextBrowser()
        self.guide_browser.setOpenExternalLinks(True)
        self.guide_browser.setHtml(_BASE_STYLE + _GUIDE_HTML)
        self.guide_browser.setMinimumHeight(280)
        self.guide_browser.setStyleSheet(
            "QTextBrowser { background: #fafbfc; border: none; }"
        )
        guide_layout.addWidget(self.guide_browser)

        # 折叠/展开按钮
        self.toggle_guide_btn = QPushButton("🔽 收起说明")
        self.toggle_guide_btn.setStyleSheet(
            "QPushButton { background: #f5f7fa; color: #606266; "
            "border: 1px solid #dcdfe6; padding: 4px 12px; "
            "border-radius: 4px; font-size: 12px; }"
            "QPushButton:hover { background: #ecf5ff; }"
        )
        self.toggle_guide_btn.clicked.connect(self._toggle_guide)
        guide_layout.addWidget(self.toggle_guide_btn, alignment=Qt.AlignmentFlag.AlignRight)

        self.guide_group = guide_group
        layout.addWidget(guide_group)

        # ============ 已配置规则区 ============
        rules_title = QLabel("已配置的审批规则")
        rules_title.setStyleSheet(
            "font-size: 16px; font-weight: bold; color: #303133; margin-top: 8px;"
        )
        layout.addWidget(rules_title)

        # 按钮区
        btn_layout = QHBoxLayout()
        self.new_btn = QPushButton("➕ 新建审批规则")
        self.new_btn.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; border: none; "
            "padding: 8px 20px; border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background: #229954; }"
        )
        self.new_btn.clicked.connect(self._on_new_rule)
        btn_layout.addWidget(self.new_btn)

        self.refresh_btn = QPushButton("🔄 刷新列表")
        self.refresh_btn.clicked.connect(self._load_rules)
        btn_layout.addWidget(self.refresh_btn)

        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 规则列表表格
        self.table = QTableWidget(0, 7)
        self.table.setHorizontalHeaderLabels(
            ["规则名称", "审批定义", "触发事件", "触发条件", "审批人", "状态", "操作"]
        )
        self.table.horizontalHeader().stretchLastSection()
        self.table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.table, stretch=1)

        # 空状态提示（业务用户一看就懂）
        self.empty_label = QLabel(
            "📭 暂无审批规则\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "按以下 3 步操作：\n\n"
            "1️⃣  先在飞书审批后台创建审批定义\n"
            "    （含 ASIN、商品名称、采购金额、业务类型、说明 5 个字段）\n"
            "    👆 详细步骤看上方『使用前必读』\n\n"
            "2️⃣  点上方『➕ 新建审批规则』按钮\n\n"
            "3️⃣  在弹窗里选审批定义 → 配触发条件 → 保存\n"
            "    （如：采购金额 > 5000 时触发审批）\n\n"
            "━━━━━━━━━━━━━━━━━━━━━━━━━━━━\n"
            "规则保存后自动生效，符合条件的事件发生时自动发审批卡片。"
        )
        self.empty_label.setStyleSheet(
            "color: #606266; font-size: 14px; padding: 30px; "
            "background: #f8f9fa; border-radius: 8px; "
            "border: 2px dashed #dcdfe6;"
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        self.empty_label.setWordWrap(True)
        layout.addWidget(self.empty_label)

    def _toggle_guide(self) -> None:
        """折叠/展开使用前必读说明。"""
        self.guide_browser.setVisible(not self.guide_browser.isVisible())
        if self.guide_browser.isVisible():
            self.toggle_guide_btn.setText("🔽 收起说明")
            self.guide_group.setMinimumHeight(0)
        else:
            self.toggle_guide_btn.setText("🔼 展开说明")

    def _load_rules(self) -> None:
        """加载规则列表。"""
        rules = list_rules()
        self.table.setRowCount(len(rules))

        if rules:
            self.empty_label.hide()
            self.table.show()
        else:
            self.empty_label.show()
            self.table.hide()
            return

        for i, rule in enumerate(rules):
            name = rule.get("name", "")
            approval_name = rule.get("approval_name", "")
            event_label = EVENT_LABELS.get(rule.get("trigger_event", ""), "未知")
            condition = (
                f"{rule.get('condition_field', '')} "
                f"{rule.get('condition_operator', '')} "
                f"{rule.get('condition_value', '')}"
            )
            approver = rule.get("approver_open_id", "")[:12] + "..."
            enabled = "已启用" if rule.get("enabled") else "已禁用"

            self.table.setItem(i, 0, QTableWidgetItem(name))
            self.table.setItem(i, 1, QTableWidgetItem(approval_name))
            self.table.setItem(i, 2, QTableWidgetItem(event_label))
            self.table.setItem(i, 3, QTableWidgetItem(condition))
            self.table.setItem(i, 4, QTableWidgetItem(approver))

            status_item = QTableWidgetItem(enabled)
            status_item.setForeground(
                Qt.GlobalColor.green if rule.get("enabled") else Qt.GlobalColor.gray
            )
            self.table.setItem(i, 5, status_item)

            # 操作按钮
            ops_widget = QWidget()
            ops_layout = QHBoxLayout(ops_widget)
            ops_layout.setContentsMargins(4, 4, 4, 4)
            ops_layout.setSpacing(4)

            toggle_btn = QPushButton("禁用" if rule.get("enabled") else "启用")
            toggle_btn.setStyleSheet(
                "QPushButton { padding: 4px 12px; border-radius: 4px; }"
            )
            rule_id = rule.get("id", "")
            toggle_btn.clicked.connect(
                lambda _, rid=rule_id, en=not rule.get("enabled"): self._on_toggle(rid, en)
            )
            ops_layout.addWidget(toggle_btn)

            del_btn = QPushButton("删除")
            del_btn.setStyleSheet(
                "QPushButton { padding: 4px 12px; border-radius: 4px; color: #e74c3c; }"
            )
            del_btn.clicked.connect(lambda _, rid=rule_id: self._on_delete(rid))
            ops_layout.addWidget(del_btn)

            self.table.setCellWidget(i, 6, ops_widget)

    def _on_new_rule(self) -> None:
        """打开新建规则对话框。"""
        dialog = NewRuleDialog(self)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            self._load_rules()

    def _on_toggle(self, rule_id: str, enabled: bool) -> None:
        """启用/禁用规则。"""
        if toggle_rule(rule_id, enabled):
            self._load_rules()

    def _on_delete(self, rule_id: str) -> None:
        """删除规则。"""
        reply = QMessageBox.question(
            self, "确认删除", "确定要删除这个审批规则吗？",
            QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No,
        )
        if reply == QMessageBox.StandardButton.Yes:
            if delete_rule(rule_id):
                self._load_rules()


# ============ HTML 基础样式（与部署向导保持一致）============
_BASE_STYLE = """
<style>
    body {
        font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
        font-size: 13px;
        line-height: 1.7;
        color: #2c3e50;
        background: #fafbfc;
        padding: 8px 12px;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #2563eb;
        margin: 14px 0 6px 0;
        line-height: 1.3;
    }
    h2 { font-size: 17px; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }
    h3 { font-size: 15px; color: #e74c3c; }
    h4 { font-size: 14px; color: #303133; }
    p { margin: 6px 0; }
    ul, ol { margin: 6px 0; padding-left: 22px; }
    li { margin: 3px 0; }
    code {
        font-family: "Consolas", "Courier New", monospace;
        background: #f3f4f6;
        color: #c7254e;
        padding: 2px 5px;
        border-radius: 3px;
        font-size: 12px;
    }
    table {
        border-collapse: collapse;
        width: 100%;
        margin: 8px 0;
        font-size: 12px;
    }
    th, td {
        border: 1px solid #d1d5db;
        padding: 5px 8px;
        text-align: left;
        vertical-align: top;
    }
    th {
        background: #f9fafb;
        color: #1f2937;
        font-weight: bold;
    }
    tr:nth-child(even) td {
        background: #fafbfc;
    }
    a { color: #2563eb; text-decoration: none; }
    a:hover { text-decoration: underline; }
    strong { color: #1f2937; }
    hr { border: none; border-top: 1px solid #e5e7eb; margin: 12px 0; }
</style>
"""
