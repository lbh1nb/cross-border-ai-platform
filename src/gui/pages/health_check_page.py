"""健康检查页面：业务用户一键检测系统配置是否正确。

业务用户点"开始检查"按钮，系统会自动检测所有配置是否正确。
绿色 ✓ 表示正常，红色 ✗ 表示需要修复。
完全可视化，不接触任何技术日志。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
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

from src.gui.services.health_check_service import CheckResult, run_all_checks


# 检查项中文名称映射：服务层返回的 name → 表格展示用名称
_DISPLAY_NAME_MAP = {
    "飞书凭证": "凭证有效性",
    "多维表格访问": "多维表格访问",
    "业务表配置": "业务表配置",
    "表格权限": "表格权限",
    "回调服务": "回调服务",
    "Cloudflare 隧道": "公网隧道",
}


class CheckThread(QThread):
    """后台执行健康检查的线程。

    避免阻塞 UI 主线程，检查完成后通过信号通知结果列表。
    """

    result_ready = Signal(list)

    def run(self) -> None:
        """执行所有健康检查并发送结果。"""
        try:
            results = run_all_checks()
        except Exception:
            # 服务层已捕获所有异常，此处兜底防御
            results = []
        self.result_ready.emit(results)


class HealthCheckPage(QWidget):
    """系统健康检查页面：一键检测所有配置是否正确。"""

    def __init__(self) -> None:
        super().__init__()
        self._check_thread: CheckThread | None = None
        self._init_ui()

    # ============ UI 初始化 ============

    def _init_ui(self) -> None:
        """初始化 UI。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题
        title = QLabel("系统健康检查")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1a1a1a;")
        layout.addWidget(title)

        # 说明文字
        hint = QLabel(
            '点"开始检查"按钮，系统会自动检测所有配置是否正确。'
            '绿色的 ✓ 表示正常，红色的 ✗ 表示需要修复。'
        )
        hint.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 检查按钮
        btn_layout = QHBoxLayout()
        self.check_btn = QPushButton("🔍 开始检查")
        self.check_btn.setStyleSheet(self._button_style())
        self.check_btn.clicked.connect(self._on_start_check)
        btn_layout.addStretch()
        btn_layout.addWidget(self.check_btn)
        btn_layout.addStretch()
        layout.addLayout(btn_layout)

        # 结果展示区：表格（检查项 / 状态 / 详情）
        self.result_table = QTableWidget(0, 3)
        self.result_table.setHorizontalHeaderLabels(["检查项", "状态", "详情"])
        self.result_table.setStyleSheet(self._table_style())
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.verticalHeader().setVisible(False)
        # 详情列文字可换行
        self.result_table.setWordWrap(True)

        header = self.result_table.horizontalHeader()
        header.setSectionResizeMode(0, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(1, QHeaderView.ResizeMode.ResizeToContents)
        header.setSectionResizeMode(2, QHeaderView.ResizeMode.Stretch)
        layout.addWidget(self.result_table, 1)

        # 底部统计
        self.stats_label = QLabel("通过 0 / 共 0 项")
        self.stats_label.setStyleSheet(
            "font-size: 14px; color: #7f8c8d; font-weight: bold; padding: 8px 0;"
        )
        self.stats_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.stats_label)

    # ============ 行为 ============

    def _on_start_check(self) -> None:
        """点击"开始检查"按钮：禁用按钮并启动后台线程。"""
        # 按钮变禁用 + 文字变"检查中..."
        self.check_btn.setEnabled(False)
        self.check_btn.setText("检查中...")

        # 清空旧结果
        self.result_table.setRowCount(0)
        self.stats_label.setText("正在检查，请稍候...")

        # 启动后台线程执行 run_all_checks
        self._check_thread = CheckThread()
        self._check_thread.result_ready.connect(self._on_check_done)
        self._check_thread.start()

    def _on_check_done(self, results: list) -> None:
        """检查完成：填充表格、更新统计、恢复按钮。

        Args:
            results: CheckResult 列表，由 CheckThread 信号返回
        """
        self.result_table.setRowCount(len(results))

        success_count = 0
        for row, result in enumerate(results):
            assert isinstance(result, CheckResult)
            if result.success:
                success_count += 1

            # 检查项名称（使用中文映射）
            display_name = _DISPLAY_NAME_MAP.get(result.name, result.name)
            name_item = QTableWidgetItem(display_name)
            name_item.setForeground(Qt.GlobalColor.black)
            self.result_table.setItem(row, 0, name_item)

            # 状态列：✅ 绿色 / ❌ 红色
            status_text = "✅" if result.success else "❌"
            status_item = QTableWidgetItem(status_text)
            if result.success:
                status_item.setForeground(Qt.GlobalColor.darkGreen)
            else:
                status_item.setForeground(Qt.GlobalColor.red)
            status_item.setTextAlignment(Qt.AlignmentFlag.AlignCenter)
            self.result_table.setItem(row, 1, status_item)

            # 详情列：message + detail
            detail_parts = [result.message]
            if result.detail:
                detail_parts.append(result.detail)
            detail_text = "\n".join(detail_parts)
            detail_item = QTableWidgetItem(detail_text)
            detail_item.setForeground(
                Qt.GlobalColor.darkGray if result.success else Qt.GlobalColor.red
            )
            self.result_table.setItem(row, 2, detail_item)

        # 行高自适应（配合 setWordWrap 让详情列自动换行）
        self.result_table.resizeRowsToContents()

        # 更新统计
        total = len(results)
        self.stats_label.setText(f"通过 {success_count} / 共 {total} 项")
        if total > 0 and success_count == total:
            # 全部通过：绿色
            self.stats_label.setStyleSheet(
                "font-size: 14px; color: #27ae60; font-weight: bold; padding: 8px 0;"
            )
        elif total > 0 and success_count < total:
            # 有失败项：红色
            self.stats_label.setStyleSheet(
                "font-size: 14px; color: #e74c3c; font-weight: bold; padding: 8px 0;"
            )
        else:
            # 无结果：灰色
            self.stats_label.setStyleSheet(
                "font-size: 14px; color: #7f8c8d; font-weight: bold; padding: 8px 0;"
            )

        # 按钮恢复
        self.check_btn.setEnabled(True)
        self.check_btn.setText("🔍 开始检查")

    # ============ 样式 ============

    @staticmethod
    def _button_style() -> str:
        """按钮样式：蓝色圆角。"""
        return (
            "QPushButton { background: #3498db; color: white; border: none; "
            "padding: 10px 32px; border-radius: 6px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #2980b9; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )

    @staticmethod
    def _table_style() -> str:
        """表格样式：白底圆角，灰色边框。"""
        return (
            "QTableWidget { background: white; border: 1px solid #e0e0e0; "
            "border-radius: 8px; gridline-color: #f0f0f0; }"
            "QHeaderView::section { background: #fafafa; color: #2c3e50; "
            "padding: 8px; border: none; border-bottom: 1px solid #e0e0e0; "
            "font-weight: bold; }"
            "QTableWidget::item { padding: 8px; }"
        )
