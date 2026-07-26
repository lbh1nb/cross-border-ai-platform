"""数据看板：选品池 + 库存预警。

从飞书多维表格读取数据，在 GUI 里以表格形式展示。
业务用户无需打开飞书，直接在 GUI 查看数据。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTabWidget,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
    QWidget,
)

from src.config import settings
from src.feishu.bitable import bitable_client


class FetchRecordsThread(QThread):
    """后台读取飞书表格数据的线程。"""

    result_ready = Signal(list)

    def __init__(self, table_id: str) -> None:
        super().__init__()
        self._table_id = table_id

    def run(self) -> None:
        if not self._table_id:
            self.result_ready.emit([])
            return
        try:
            records = bitable_client.query_records(self._table_id)
            self.result_ready.emit(records or [])
        except Exception:
            self.result_ready.emit([])


class DashboardPage(QWidget):
    """数据看板页面。"""

    def __init__(self) -> None:
        super().__init__()
        self._selection_thread: FetchRecordsThread | None = None
        self._inventory_thread: FetchRecordsThread | None = None
        self._init_ui()

    def _init_ui(self) -> None:
        """初始化 UI。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题
        title = QLabel("数据看板")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        hint = QLabel('直接在 GUI 查看飞书多维表格数据，无需打开飞书。点"刷新"更新数据。')
        hint.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        layout.addWidget(hint)

        # 刷新按钮
        btn_layout = QHBoxLayout()
        self.refresh_btn = QPushButton("🔄 刷新数据")
        self.refresh_btn.clicked.connect(self.refresh_data)
        btn_layout.addWidget(self.refresh_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 选项卡
        self.tabs = QTabWidget()
        self.tabs.addTab(self._build_selection_tab(), "选品池")
        self.tabs.addTab(self._build_inventory_tab(), "库存预警")
        layout.addWidget(self.tabs, stretch=1)

    def _build_selection_tab(self) -> QWidget:
        """选品池选项卡。"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.selection_table = QTableWidget(0, 8)
        self.selection_table.setHorizontalHeaderLabels(
            ["商品名称", "ASIN", "品类", "来源平台", "价格", "评分", "评论数", "推荐指数"]
        )
        self.selection_table.horizontalHeader().stretchLastSection()
        self.selection_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.selection_table)
        return tab

    def _build_inventory_tab(self) -> QWidget:
        """库存预警选项卡。"""
        tab = QWidget()
        layout = QVBoxLayout(tab)
        self.inventory_table = QTableWidget(0, 7)
        self.inventory_table.setHorizontalHeaderLabels(
            ["ASIN", "商品名称", "SKU", "平台", "可售天数", "预警等级", "审批状态"]
        )
        self.inventory_table.horizontalHeader().stretchLastSection()
        self.inventory_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        layout.addWidget(self.inventory_table)
        return tab

    def refresh_data(self) -> None:
        """刷新数据（后台线程读取飞书表格）。"""
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("🔄 刷新中...")

        # 读取选品池
        selection_id = settings.feishu_table_id_selection
        self._selection_thread = FetchRecordsThread(selection_id)
        self._selection_thread.result_ready.connect(self._on_selection_ready)
        self._selection_thread.start()

        # 读取库存预警
        inventory_id = settings.feishu_table_id_inventory
        self._inventory_thread = FetchRecordsThread(inventory_id)
        self._inventory_thread.result_ready.connect(self._on_inventory_ready)
        self._inventory_thread.start()

    def _on_selection_ready(self, records: list) -> None:
        """选品池数据就绪。"""
        self._fill_table(
            self.selection_table,
            records,
            ["商品名称", "ASIN", "品类", "来源平台", "价格", "评分", "评论数", "推荐指数"],
        )
        self._check_refresh_done()

    def _on_inventory_ready(self, records: list) -> None:
        """库存预警数据就绪。"""
        self._fill_table(
            self.inventory_table,
            records,
            ["ASIN", "商品名称", "SKU", "平台", "可售天数", "预警等级", "审批状态"],
        )
        self._check_refresh_done()

    def _check_refresh_done(self) -> None:
        """检查两个表格是否都加载完。"""
        # 简单方案：两个线程都 finished 后恢复按钮
        if (
            self._selection_thread is None or not self._selection_thread.isRunning()
        ) and (
            self._inventory_thread is None or not self._inventory_thread.isRunning()
        ):
            self.refresh_btn.setEnabled(True)
            self.refresh_btn.setText("🔄 刷新数据")

    def _fill_table(
        self,
        table: QTableWidget,
        records: list,
        columns: list,
    ) -> None:
        """填充表格数据。

        Args:
            table: QTableWidget 实例
            records: 飞书返回的记录列表
            columns: 要显示的字段名列表
        """
        table.setRowCount(len(records))
        for row, record in enumerate(records):
            fields = record.get("fields", {})
            for col, field_name in enumerate(columns):
                value = self._extract_field_value(fields.get(field_name))
                item = QTableWidgetItem(str(value))
                # 预警等级着色
                if field_name == "预警等级":
                    level = str(value)
                    if level == "紧急":
                        item.setForeground(Qt.GlobalColor.red)
                    elif level == "预警":
                        item.setForeground(Qt.GlobalColor.darkYellow)
                    elif level == "关注":
                        item.setForeground(Qt.GlobalColor.blue)
                table.setItem(row, col, item)

    @staticmethod
    def _extract_field_value(field_value) -> str:
        """从飞书字段值中提取显示文本（兼容文本/数字/列表/单选格式）。"""
        if field_value is None:
            return ""
        if isinstance(field_value, (int, float)):
            return str(field_value)
        if isinstance(field_value, str):
            return field_value
        if isinstance(field_value, list):
            if not field_value:
                return ""
            first = field_value[0]
            if isinstance(first, dict):
                return str(first.get("text") or first.get("name") or "")
            return str(first)
        if isinstance(field_value, dict):
            return str(field_value.get("text") or field_value.get("name") or "")
        return str(field_value)
