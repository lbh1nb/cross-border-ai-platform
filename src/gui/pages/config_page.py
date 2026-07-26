"""配置面板：飞书凭证 + 表 ID + 审批人配置。

业务用户在表单里填配置，点"保存"后自动写入 .env。
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
    QVBoxLayout,
    QWidget,
)

from src.gui.services.env_service import read_env_config, write_env_config


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

        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 标题
        title = QLabel("系统配置")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        hint = QLabel("填写飞书凭证和表 ID，保存后立即生效。所有配置自动写入 .env 文件。")
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
        self.save_btn.setFixedWidth(160)
        self.save_btn.clicked.connect(self._on_save)
        btn_layout.addWidget(self.save_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        scroll.setWidget(container)
        outer = QVBoxLayout(self)
        outer.setContentsMargins(0, 0, 0, 0)
        outer.addWidget(scroll)

    def _build_credentials_group(self) -> QGroupBox:
        """飞书凭证组。"""
        group = QGroupBox("飞书应用凭证")
        layout = QFormLayout(group)
        self.app_id_input = QLineEdit()
        self.app_id_input.setPlaceholderText("cli_xxxxxxxxxxxxxxxx")
        layout.addRow("App ID:", self.app_id_input)

        self.app_secret_input = QLineEdit()
        self.app_secret_input.setEchoMode(QLineEdit.EchoMode.Password)
        self.app_secret_input.setPlaceholderText("应用密钥")
        layout.addRow("App Secret:", self.app_secret_input)

        self.tenant_domain_input = QLineEdit()
        self.tenant_domain_input.setPlaceholderText("如 ocndodd7lmyr")
        layout.addRow("企业租户域名:", self.tenant_domain_input)

        self.app_token_input = QLineEdit()
        self.app_token_input.setPlaceholderText("多维表格 App Token")
        layout.addRow("多维表格 App Token:", self.app_token_input)
        return group

    def _build_tables_group(self) -> QGroupBox:
        """多维表格 ID 组。"""
        group = QGroupBox("飞书多维表格 ID")
        layout = QFormLayout(group)
        self.table_selection = QLineEdit()
        layout.addRow("选品池表 ID:", self.table_selection)

        self.table_listing = QLineEdit()
        layout.addRow("Listing 库表 ID:", self.table_listing)

        self.table_daily_report = QLineEdit()
        layout.addRow("销售日报表 ID:", self.table_daily_report)

        self.table_inventory = QLineEdit()
        layout.addRow("库存预警表 ID:", self.table_inventory)

        self.table_config = QLineEdit()
        layout.addRow("采集配置表 ID:", self.table_config)
        return group

    def _build_bot_group(self) -> QGroupBox:
        """机器人配置组。"""
        group = QGroupBox("飞书机器人")
        layout = QFormLayout(group)
        self.webhook_url_input = QLineEdit()
        self.webhook_url_input.setPlaceholderText("https://open.feishu.cn/open-apis/bot/v2/hook/xxx")
        layout.addRow("Webhook URL:", self.webhook_url_input)

        self.chat_id_input = QLineEdit()
        self.chat_id_input.setPlaceholderText("oc_xxxxxxxx（应用机器人所在群）")
        layout.addRow("群聊 Chat ID:", self.chat_id_input)

        self.approver_open_id_input = QLineEdit()
        self.approver_open_id_input.setPlaceholderText("ou_xxxxxxxx（审批人）")
        layout.addRow("审批人 Open ID:", self.approver_open_id_input)
        return group

    def _build_biz_group(self) -> QGroupBox:
        """业务配置组。"""
        group = QGroupBox("业务参数")
        layout = QFormLayout(group)
        from PySide6.QtWidgets import QSpinBox

        self.alert_days = QSpinBox()
        self.alert_days.setRange(1, 60)
        self.alert_days.setValue(14)
        layout.addRow("库存预警阈值（天）:", self.alert_days)

        from PySide6.QtWidgets import QDoubleSpinBox

        self.approval_threshold = QDoubleSpinBox()
        self.approval_threshold.setRange(0, 100000)
        self.approval_threshold.setValue(5000)
        self.approval_threshold.setPrefix("$ ")
        layout.addRow("审批触发金额（美金）:", self.approval_threshold)

        self.retention_days = QSpinBox()
        self.retention_days.setRange(1, 30)
        self.retention_days.setValue(3)
        layout.addRow("数据保留天数:", self.retention_days)
        return group

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
            QMessageBox.information(self, "成功", "配置已保存到 .env，立即生效。")
        else:
            QMessageBox.critical(self, "失败", "保存配置失败，请查看日志。")
