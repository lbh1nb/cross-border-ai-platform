"""任务控制面板。

业务用户可以：
1. 一键启动后台调度器（选品采集/库存预警/审批流触发等所有定时任务）
2. 一键停止
3. 查看任务列表和运行状态
4. 手动触发单个任务（测试用）
5. 查看实时日志
"""

from __future__ import annotations

import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.scheduler.scheduler import SchedulerManager
from src.scheduler.triggers import ALL_TRIGGERS


class SchedulerThread(QThread):
    """后台运行调度器的线程（避免阻塞 UI）。"""

    status_changed = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        self._manager: SchedulerManager | None = None

    def run(self) -> None:
        try:
            self._manager = SchedulerManager()
            self._manager.start()
            self.status_changed.emit("running")
            # 线程保持运行，直到 stop 被调用
            self.exec()
        except Exception as e:
            self.status_changed.emit(f"error: {e}")

    def stop(self) -> None:
        """停止调度器。"""
        if self._manager:
            try:
                self._manager.shutdown()
            except Exception:
                pass
        self.quit()


class TaskPage(QWidget):
    """任务控制面板。"""

    def __init__(self) -> None:
        super().__init__()
        self._scheduler_thread: SchedulerThread | None = None
        self._init_ui()
        self._load_tasks()

    def _init_ui(self) -> None:
        """初始化 UI。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题
        title = QLabel("任务控制")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        hint = QLabel(
            '点击"启动调度器"后，所有定时任务会在后台自动运行。'
            "包括：选品采集（工作日9点）/ 库存预警（每30分钟）/ 审批流触发（每天10点）/ 数据清理（每3天）。"
        )
        hint.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 控制按钮
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶ 启动调度器")
        self.start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ 停止调度器")
        self.stop_btn.setProperty("danger", True)
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        btn_layout.addStretch()

        # 状态指示
        self.status_label = QLabel("● 未运行")
        self.status_label.setStyleSheet("font-size: 14px; color: #95a5a6;")
        btn_layout.addWidget(self.status_label)

        layout.addLayout(btn_layout)

        # 任务列表
        task_group = QGroupBox("定时任务列表")
        task_layout = QVBoxLayout(task_group)
        self.task_table = QTableWidget(0, 4)
        self.task_table.setHorizontalHeaderLabels(["任务 ID", "说明", "触发时间", "状态"])
        self.task_table.horizontalHeader().stretchLastSection()
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        task_layout.addWidget(self.task_table)
        layout.addWidget(task_group)

        # 日志区
        log_group = QGroupBox("实时日志")
        log_layout = QVBoxLayout(log_group)
        self.log_text = QTextEdit()
        self.log_text.setReadOnly(True)
        self.log_text.setMaximumHeight(220)
        log_layout.addWidget(self.log_text)

        log_btn_layout = QHBoxLayout()
        clear_btn = QPushButton("🗑 清空日志")
        clear_btn.clicked.connect(self.log_text.clear)
        log_btn_layout.addStretch()
        log_btn_layout.addWidget(clear_btn)
        log_layout.addLayout(log_btn_layout)

        layout.addWidget(log_group)

        # 定时刷新日志
        self._log_timer = QTimer()
        self._log_timer.timeout.connect(self._refresh_log)
        self._log_timer.start(1000)

    def _load_tasks(self) -> None:
        """加载任务列表到表格。"""
        from src.scheduler.triggers import ALL_TRIGGERS

        self.task_table.setRowCount(len(ALL_TRIGGERS))
        for i, trigger in enumerate(ALL_TRIGGERS):
            task_id = trigger.get("id", "")
            name = trigger.get("name", "")
            # 组合 cron 表达式描述
            cron_desc = self._format_cron(trigger)
            self.task_table.setItem(i, 0, QTableWidgetItem(task_id))
            self.task_table.setItem(i, 1, QTableWidgetItem(name))
            self.task_table.setItem(i, 2, QTableWidgetItem(cron_desc))
            self.task_table.setItem(i, 3, QTableWidgetItem("待启动"))

    @staticmethod
    def _format_cron(trigger: dict) -> str:
        """把触发器字典格式化成可读的 cron 描述。"""
        if trigger.get("trigger") != "cron":
            return str(trigger.get("trigger", ""))

        parts = []
        if "day_of_week" in trigger:
            parts.append(f"每周{trigger['day_of_week']}")
        if "day" in trigger:
            parts.append(f"每{trigger['day']}天")
        if "hour" in trigger and "minute" in trigger:
            parts.append(f"{trigger['hour']}:{trigger['minute']:02d}")
        elif "minute" in trigger:
            parts.append(f"每{trigger['minute']}分钟")
        return " ".join(parts) if parts else ""

    def _on_start(self) -> None:
        """启动调度器。"""
        self.start_btn.setEnabled(False)
        self.start_btn.setText("▶ 启动中...")

        self._scheduler_thread = SchedulerThread()
        self._scheduler_thread.status_changed.connect(self._on_status_changed)
        self._scheduler_thread.start()

    def _on_stop(self) -> None:
        """停止调度器。"""
        if self._scheduler_thread:
            self._scheduler_thread.stop()
            self._scheduler_thread = None

        self.start_btn.setEnabled(True)
        self.start_btn.setText("▶ 启动调度器")
        self.stop_btn.setEnabled(False)
        self.status_label.setText("● 已停止")
        self.status_label.setStyleSheet("font-size: 14px; color: #e74c3c;")

        # 更新任务状态
        for i in range(self.task_table.rowCount()):
            self.task_table.setItem(i, 3, QTableWidgetItem("已停止"))

        self._append_log("调度器已停止")

    def _on_status_changed(self, status: str) -> None:
        """调度器状态变更回调。"""
        if status == "running":
            self.start_btn.setText("▶ 运行中")
            self.stop_btn.setEnabled(True)
            self.status_label.setText("● 运行中")
            self.status_label.setStyleSheet("font-size: 14px; color: #2ecc71;")
            self._append_log("调度器已启动，所有定时任务开始运行")

            for i in range(self.task_table.rowCount()):
                self.task_table.setItem(i, 3, QTableWidgetItem("运行中"))
        else:
            self.start_btn.setEnabled(True)
            self.start_btn.setText("▶ 启动调度器")
            self.status_label.setText(f"● 错误: {status}")
            self.status_label.setStyleSheet("font-size: 14px; color: #e74c3c;")
            self._append_log(f"调度器启动失败: {status}")

    def _refresh_log(self) -> None:
        """从日志文件读取最新内容。"""
        try:
            log_dir = Path("logs")
            if not log_dir.exists():
                return
            # 找最新的日志文件
            log_files = sorted(log_dir.glob("app_*.log"), reverse=True)
            if not log_files:
                return
            # 只读最后 30 行
            with open(log_files[0], "r", encoding="utf-8") as f:
                lines = f.readlines()[-30:]
            self.log_text.setPlainText("".join(lines))
        except Exception:
            pass

    def _append_log(self, msg: str) -> None:
        """追加一行日志到日志区。"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        self.log_text.append(f"[{timestamp}] {msg}")
