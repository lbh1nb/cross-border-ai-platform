"""配置面板：飞书凭证 + 表 ID + 审批人配置。

业务用户在表单里填配置，点"保存"后自动写入 .env。
每个字段下方有灰色小字说明，告诉用户从哪获取、怎么填。
完全可视化，不接触任何代码或文本文件。
"""

from __future__ import annotations

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QFormLayout,
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QScrollArea,
    QSpinBox,
    QDoubleSpinBox,
    QVBoxLayout,
    QWidget,
)

from src.gui.services.env_service import read_env_config, write_env_config
from src.gui.widgets.approver_search_dialog import ApproverSearchDialog


# ============ 字段说明文案（业务用户看得懂的大白话） ============
HINTS = {
    "app_id": '获取方式：登录 飞书开放平台 → 创建企业自建应用 → 凭证与基础信息 → App ID。\n格式：cli_ 开头的一串字母数字。',
    "app_secret": '获取方式：和 App ID 在同一个页面，点"显示"即可复制。\n格式：一串字母数字（保密，不要泄露）。',
    "tenant_domain": '获取方式：打开你的飞书多维表格网页 URL，前面那段就是。\n例如 https://ocndodd7lmyr.feishu.cn/base/xxx，填 ocndodd7lmyr 即可。\n作用：让飞书桌面端能直接打开表格，不用跳浏览器。',
    "app_token": '获取方式：打开飞书多维表格，看浏览器地址栏 URL 里 /base/ 后面那串就是。\n例如 .../base/appXXXtokenYYY，填 appXXXtokenYYY。',
    "table_id": '获取方式：打开飞书多维表格的某张表，URL 里 table= 后面那串就是。\n格式：tbl 开头。',
    "webhook": '获取方式：飞书群聊 → 设置 → 群机器人 → 添加机器人 → 自定义机器人 → 复制 Webhook 地址。\n格式：https://open.feishu.cn/open-apis/bot/v2/hook/xxx',
    "chat_id": '获取方式：群机器人必须是"应用机器人"而非"自定义机器人"才能拿 Chat ID。\n用飞书开放平台的通讯录 API 查询群列表，oc_ 开头。\n作用：应用机器人发消息到这个群。',
    "approver": '获取方式：飞书开放平台 → 通讯录 → 搜索审批人姓名 → 复制 open_id。\n格式：ou_ 开头。\n作用：审批流默认审批人（多审批流时每个规则可单独指定）。',
}


def _make_hint(text: str) -> QLabel:
    """创建灰色小字说明标签。"""
    label = QLabel(text)
    label.setStyleSheet("color: #95a5a6; font-size: 12px; padding: 2px 0 6px 0;")
    label.setWordWrap(True)
    return label


def _make_field_row(
    layout: QVBoxLayout,
    label_text: str,
    input_widget: QLineEdit,
    hint_text: str = "",
) -> None:
    """构建一行：标签 + 输入框 + 灰色说明。"""
    row_layout = QVBoxLayout()
    row_layout.setSpacing(2)
    label = QLabel(label_text)
    label.setStyleSheet("font-weight: 500; color: #2c3e50;")
    row_layout.addWidget(label)
    row_layout.addWidget(input_widget)
    if hint_text:
        row_layout.addWidget(_make_hint(hint_text))
    layout.addLayout(row_layout)


class ConfigPage(QWidget):
    """配置面板：飞书凭证、表 ID、审批人配置。"""

    def __init__(self) -> None:
        super().__init__()
        self._init_ui()
        self._load_config()

    def _init_ui(self) -> None:
        """初始化 UI。"""
        scroll = QScrollArea()
        scroll.setWidgetResizable(True)
        scroll.setStyleSheet("QScrollArea { border: none; background: transparent; }")

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 标题
        title = QLabel("系统配置")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1a1a1a;")
        layout.addWidget(title)

        hint = QLabel(
            '按下方每个字段的说明填写，点"保存配置"后立即生效。'
            "所有配置自动写入 .env 文件，不用手动编辑。"
            "带 * 的字段必填，其他可选。"
        )
        hint.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 飞书凭证组
        cred_group = self._build_credentials_group()
        layout.addWidget(cred_group)

        # 多维表格组
        table_group = self._build_tables_group()
        layout.addWidget(table_group)

        # 机器人组
        bot_group = self._build_bot_group()
        layout.addWidget(bot_group)

        # 业务配置组
        biz_group = self._build_biz_group()
        layout.addWidget(biz_group)

        # 保存按钮
        btn_layout = QHBoxLayout()
        btn_layout.addStretch()
        self.save_btn = QPushButton("💾 保存配置")
        self.save_btn.setFixedWidth(180)
        self.save_btn.setStyleSheet(
            "QPushButton { background: #3498db; color: white; border: none; "
            "padding: 10px 24px; border-radius: 6px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #2980b9; }"
        )
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        layout.addStretch()

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _build_credentials_group(self) -> QGroupBox:
        """飞书凭证组。"""
        group = QGroupBox("① 飞书应用凭证（必填）")
        group.setStyleSheet(self._group_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self.app_id_input = QLineEdit()
        self.app_id_input.setPlaceholderText("cli_xxxxxxxxxxxxxxxx")
        _make_field_row(layout, "* App ID", self.app_id_input, HINTS["app_id"])

        self.app_secret_input = QLineEdit()
        self.app_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.app_secret_input.setPlaceholderText("应用密钥")
        _make_field_row(layout, "* App Secret", self.app_secret_input, HINTS["app_secret"])

        self.tenant_domain_input = QLineEdit()
        self.tenant_domain_input.setPlaceholderText("如 ocndodd7lmyr")
        _make_field_row(layout, "* 企业租户域名", self.tenant_domain_input, HINTS["tenant_domain"])

        self.app_token_input = QLineEdit()
        self.app_token_input.setPlaceholderText("多维表格 App Token")
        _make_field_row(layout, "* 多维表格 App Token", self.app_token_input, HINTS["app_token"])

        return group

    def _build_tables_group(self) -> QGroupBox:
        """多维表格 ID 组。"""
        group = QGroupBox("② 飞书多维表格 ID（必填）")
        group.setStyleSheet(self._group_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self.table_selection = QLineEdit()
        self.table_selection.setPlaceholderText("tblxxxxxxxxxxxx")
        _make_field_row(layout, "* 选品池表 ID", self.table_selection, HINTS["table_id"])

        self.table_listing = QLineEdit()
        self.table_listing.setPlaceholderText("tblxxxxxxxxxxxx")
        _make_field_row(layout, "Listing 库表 ID", self.table_listing, HINTS["table_id"])

        self.table_daily_report = QLineEdit()
        self.table_daily_report.setPlaceholderText("tblxxxxxxxxxxxx")
        _make_field_row(layout, "销售日报表 ID", self.table_daily_report, HINTS["table_id"])

        self.table_inventory = QLineEdit()
        self.table_inventory.setPlaceholderText("tblxxxxxxxxxxxx")
        _make_field_row(layout, "* 库存预警表 ID", self.table_inventory, HINTS["table_id"])

        self.table_config = QLineEdit()
        self.table_config.setPlaceholderText("tblxxxxxxxxxxxx")
        _make_field_row(layout, "* 采集配置表 ID", self.table_config, HINTS["table_id"])

        return group

    def _build_bot_group(self) -> QGroupBox:
        """机器人配置组。"""
        group = QGroupBox("③ 飞书机器人（可选，不填则不发告警）")
        group.setStyleSheet(self._group_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        self.webhook_url_input = QLineEdit()
        self.webhook_url_input.setPlaceholderText("https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
        _make_field_row(layout, "Webhook URL", self.webhook_url_input, HINTS["webhook"])

        # 群聊 Chat ID：输入框 + 搜索按钮（业务用户一键列出机器人所在群聊）
        chat_row = QVBoxLayout()
        chat_row.setSpacing(2)
        chat_label = QLabel("群聊 Chat ID")
        chat_label.setStyleSheet("font-weight: 500; color: #2c3e50;")
        chat_row.addWidget(chat_label)

        chat_input_layout = QHBoxLayout()
        chat_input_layout.setSpacing(6)
        self.chat_id_input = QLineEdit()
        self.chat_id_input.setPlaceholderText("oc_xxxxxxxx")
        chat_input_layout.addWidget(self.chat_id_input, stretch=1)

        self.search_chat_btn = QPushButton("🔍 搜索群聊")
        self.search_chat_btn.setToolTip("一键列出机器人已加入的所有群聊，点选即可")
        self.search_chat_btn.setStyleSheet(
            "QPushButton { background: #2980b9; color: white; "
            "border: none; padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #21618c; }"
        )
        self.search_chat_btn.clicked.connect(self._on_search_chat)
        chat_input_layout.addWidget(self.search_chat_btn)
        chat_row.addLayout(chat_input_layout)
        chat_row.addWidget(_make_hint(HINTS["chat_id"]))
        layout.addLayout(chat_row)

        # 审批人字段：输入框 + 搜索按钮（业务用户不用手动复制 ou_ 字符串）
        approver_row = QVBoxLayout()
        approver_row.setSpacing(2)
        approver_label = QLabel("审批人 Open ID")
        approver_label.setStyleSheet("font-weight: 500; color: #2c3e50;")
        approver_row.addWidget(approver_label)

        approver_input_layout = QHBoxLayout()
        approver_input_layout.setSpacing(6)
        self.approver_open_id_input = QLineEdit()
        self.approver_open_id_input.setPlaceholderText("ou_xxxxxxxx")
        approver_input_layout.addWidget(self.approver_open_id_input, stretch=1)

        self.search_approver_btn = QPushButton("🔍 搜索")
        self.search_approver_btn.setToolTip("输入姓名搜索飞书用户，自动填入 open_id")
        self.search_approver_btn.setStyleSheet(
            "QPushButton { background: #2980b9; color: white; "
            "border: none; padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #21618c; }"
        )
        self.search_approver_btn.clicked.connect(self._on_search_approver)
        approver_input_layout.addWidget(self.search_approver_btn)
        approver_row.addLayout(approver_input_layout)
        approver_row.addWidget(_make_hint(HINTS["approver"]))
        layout.addLayout(approver_row)

        return group

    def _on_search_approver(self) -> None:
        """点搜索按钮：打开审批人搜索对话框。"""
        result = ApproverSearchDialog.pick_approver(self)
        if result:
            open_id, name = result
            self.approver_open_id_input.setText(open_id)
            QMessageBox.information(
                self, "已选中",
                f"已选择审批人：{name}\nopen_id 已自动填入。\n\n"
                "记得点页面底部的『保存配置』按钮。"
            )

    def _on_search_chat(self) -> None:
        """点搜索群聊按钮：打开群聊选择对话框。"""
        from src.gui.widgets.chat_search_dialog import ChatSearchDialog

        result = ChatSearchDialog.pick_chat(self)
        if result:
            chat_id, chat_name = result
            self.chat_id_input.setText(chat_id)
            QMessageBox.information(
                self, "已选中",
                f"已选择群聊：{chat_name}\nchat_id 已自动填入。\n\n"
                "记得点页面底部的『保存配置』按钮。"
            )

    def _build_biz_group(self) -> QGroupBox:
        """业务配置组。"""
        group = QGroupBox("④ 业务参数")
        group.setStyleSheet(self._group_style())
        layout = QVBoxLayout(group)
        layout.setSpacing(8)

        # 库存预警阈值
        row1 = QVBoxLayout()
        row1.setSpacing(2)
        label1 = QLabel("库存预警阈值（天）")
        label1.setStyleSheet("font-weight: 500; color: #2c3e50;")
        row1.addWidget(label1)
        self.alert_days = QSpinBox()
        self.alert_days.setRange(1, 60)
        self.alert_days.setValue(14)
        self.alert_days.setStyleSheet(self._input_style())
        row1.addWidget(self.alert_days)
        row1.addWidget(_make_hint("可售天数低于此值触发预警。默认 14 天。"))
        layout.addLayout(row1)

        # 审批触发金额
        row2 = QVBoxLayout()
        row2.setSpacing(2)
        label2 = QLabel("审批触发金额（美金）")
        label2.setStyleSheet("font-weight: 500; color: #2c3e50;")
        row2.addWidget(label2)
        self.approval_threshold = QDoubleSpinBox()
        self.approval_threshold.setRange(0, 100000)
        self.approval_threshold.setValue(5000)
        self.approval_threshold.setPrefix("$ ")
        self.approval_threshold.setStyleSheet(self._input_style())
        row2.addWidget(self.approval_threshold)
        row2.addWidget(_make_hint('采购金额超过此值自动触发审批。默认 $5000。\n注意：这是兜底阈值，具体审批规则在"审批流管理"页配置。'))
        layout.addLayout(row2)

        # 数据保留天数
        row3 = QVBoxLayout()
        row3.setSpacing(2)
        label3 = QLabel("数据保留天数")
        label3.setStyleSheet("font-weight: 500; color: #2c3e50;")
        row3.addWidget(label3)
        self.retention_days = QSpinBox()
        self.retention_days.setRange(1, 30)
        self.retention_days.setValue(3)
        self.retention_days.setStyleSheet(self._input_style())
        row3.addWidget(self.retention_days)
        row3.addWidget(_make_hint("超过此天数的旧数据自动清理。默认 3 天。"))
        layout.addLayout(row3)

        return group

    @staticmethod
    def _group_style() -> str:
        return """
            QGroupBox {
                font-size: 15px;
                font-weight: bold;
                color: #2c3e50;
                border: 1px solid #e0e0e0;
                border-radius: 8px;
                margin-top: 12px;
                padding-top: 16px;
                background: white;
            }
            QGroupBox::title {
                subcontrol-origin: margin;
                left: 12px;
                padding: 0 6px;
            }
        """

    @staticmethod
    def _input_style() -> str:
        return (
            "QLineEdit, QSpinBox, QDoubleSpinBox { "
            "padding: 6px 8px; border: 1px solid #d0d0d0; border-radius: 4px; "
            "background: white; }"
            "QLineEdit:focus, QSpinBox:focus, QDoubleSpinBox:focus { "
            "border: 1px solid #3498db; }"
        )

    def _load_config(self) -> None:
        """从 .env 加载配置到表单。"""
        config = read_env_config()
        self.app_id_input.setText(config.get("FEISHU_APP_ID", ""))
        self.app_secret_input.setText(config.get("FEISHU_APP_SECRET", ""))
        self.tenant_domain_input.setText(config.get("FEISHU_TENANT_DOMAIN", ""))
        self.app_token_input.setText(config.get("FEISHU_BITABLE_APP_TOKEN", ""))
        self.table_selection.setText(config.get("FEISHU_TABLE_ID_SELECTION", ""))
        self.table_listing.setText(config.get("FEISHU_TABLE_ID_LISTING", ""))
        self.table_daily_report.setText(config.get("FEISHU_TABLE_ID_DAILY_REPORT", ""))
        self.table_inventory.setText(config.get("FEISHU_TABLE_ID_INVENTORY", ""))
        self.table_config.setText(config.get("FEISHU_TABLE_ID_COLLECTION_CONFIG", ""))
        self.webhook_url_input.setText(config.get("FEISHU_WEBHOOK_URL", ""))
        self.chat_id_input.setText(config.get("FEISHU_CHAT_ID", ""))
        self.approver_open_id_input.setText(
            config.get("FEISHU_APPROVAL_APPROVER_OPEN_ID", "")
        )
        self.alert_days.setValue(int(config.get("INVENTORY_ALERT_DAYS", "14")))
        self.approval_threshold.setValue(
            float(config.get("PURCHASE_APPROVAL_THRESHOLD", "5000"))
        )
        self.retention_days.setValue(int(config.get("DATA_RETENTION_DAYS", "3")))

    def _on_save(self) -> None:
        """保存配置到 .env。"""
        updates = {
            "FEISHU_APP_ID": self.app_id_input.text().strip(),
            "FEISHU_APP_SECRET": self.app_secret_input.text().strip(),
            "FEISHU_TENANT_DOMAIN": self.tenant_domain_input.text().strip(),
            "FEISHU_BITABLE_APP_TOKEN": self.app_token_input.text().strip(),
            "FEISHU_TABLE_ID_SELECTION": self.table_selection.text().strip(),
            "FEISHU_TABLE_ID_LISTING": self.table_listing.text().strip(),
            "FEISHU_TABLE_ID_DAILY_REPORT": self.table_daily_report.text().strip(),
            "FEISHU_TABLE_ID_INVENTORY": self.table_inventory.text().strip(),
            "FEISHU_TABLE_ID_COLLECTION_CONFIG": self.table_config.text().strip(),
            "FEISHU_WEBHOOK_URL": self.webhook_url_input.text().strip(),
            "FEISHU_CHAT_ID": self.chat_id_input.text().strip(),
            "FEISHU_APPROVAL_APPROVER_OPEN_ID": self.approver_open_id_input.text().strip(),
            "INVENTORY_ALERT_DAYS": str(self.alert_days.value()),
            "PURCHASE_APPROVAL_THRESHOLD": str(self.approval_threshold.value()),
            "DATA_RETENTION_DAYS": str(self.retention_days.value()),
        }
        success = write_env_config(updates)
        if success:
            # 关键：重新加载 settings 单例，让其他模块立即读到最新配置
            from src.config import reload_settings
            reload_settings()
            QMessageBox.information(
                self, "成功",
                "配置已保存到 .env，立即生效。\n\n"
                "现在可以去『健康检查』页验证配置是否正确，"
                "或去『审批流管理』页扫描审批定义。"
            )
        else:
            QMessageBox.critical(self, "失败", "保存配置失败，请查看日志。")
