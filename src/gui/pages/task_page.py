"""任务控制面板（08-07 重构版）。

修复点：
1. 改用 BackgroundScheduler（start() 立即返回，不阻塞 UI 线程）
2. 双选项卡日志：业务日志（大白话）+ 技术日志（完整）
3. 任务列表状态实时更新
4. 内置回调服务 + Cloudflare 隧道控制（业务用户不用开终端）

业务用户操作：
1. 点"启动调度器" → 所有定时任务后台运行
2. 点"启动回调服务" → 接收飞书卡片回调
3. 点"启动公网隧道" → 让飞书能访问本地服务
4. 看业务日志了解运行情况（如"采集了5个商品""触发2条审批"）
5. 切到技术日志看完整细节（排查问题用）
"""

from __future__ import annotations

import re
from pathlib import Path

from PySide6.QtCore import Qt, QThread, QTimer, Signal
from PySide6.QtGui import QGuiApplication
from PySide6.QtWidgets import (
    QGroupBox,
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QTabWidget,
    QTextBrowser,
    QTextEdit,
    QVBoxLayout,
    QWidget,
)

from src.gui.services.callback_server_thread import CallbackServerThread
from src.gui.services.cloudflare_tunnel_thread import CloudflareTunnelThread
from src.gui.services.env_service import write_env_config
from src.scheduler.scheduler import SchedulerManager
from src.scheduler.triggers import ALL_TRIGGERS


class SchedulerThread(QThread):
    """后台运行调度器的线程。

    用 BackgroundScheduler（start() 立即返回），
    线程保持 exec() 状态接收信号，stop() 时退出。
    """
    status_changed = Signal(str)
    jobs_ready = Signal(list)

    def __init__(self) -> None:
        super().__init__()
        self._manager: SchedulerManager | None = None

    def run(self) -> None:
        try:
            # 关键：用 BackgroundScheduler，start() 立即返回不阻塞
            self._manager = SchedulerManager(blocking=False)
            self._manager.start()
            self.status_changed.emit("running")
            # 发送任务列表（含下次执行时间）
            self.jobs_ready.emit(self._manager.get_jobs())
            # 线程保持运行，等待 stop() 信号
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


# ============ 业务日志过滤规则 ============
# 从技术日志里提取业务相关的大白话消息
# 匹配这些关键字的行会显示到业务日志
BUSINESS_KEYWORDS = [
    "采集", "清洗", "同步", "新增", "更新", "跳过", "失败",
    "库存预警", "告警", "审批", "触发",
    "定时任务", "兜底任务",
    "完成", "成功",
]

# 业务日志里要过滤掉的技术噪音
NOISE_PATTERNS = [
    r"^={5,}",       # ===== 分隔线
    r"^-\{5,}",      # ----- 分隔线
    r"register_job",
    r"Added job",
    r"Scheduler started",
    r"Removed job",
]


def _is_business_line(line: str) -> bool:
    """判断一行日志是否属于业务消息。"""
    if not line.strip():
        return False
    for pattern in NOISE_PATTERNS:
        if re.search(pattern, line):
            return False
    return any(kw in line for kw in BUSINESS_KEYWORDS)


class TaskPage(QWidget):
    """任务控制面板。"""

    def __init__(self) -> None:
        super().__init__()
        self._scheduler_thread: SchedulerThread | None = None
        self._callback_thread: CallbackServerThread | None = None
        self._tunnel_thread: CloudflareTunnelThread | None = None
        # 完整回调地址（公网 URL + /callback），供"一键复制"按钮使用
        self._callback_url: str = ""
        self._init_ui()
        self._load_tasks()

        # 定时刷新日志和任务状态
        self._timer = QTimer()
        self._timer.timeout.connect(self._refresh)
        self._timer.start(1500)

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题
        title = QLabel("任务控制")
        title.setStyleSheet("font-size: 22px; font-weight: bold; color: #1a1a1a;")
        layout.addWidget(title)

        hint = QLabel(
            '点"启动调度器"后，所有定时任务会在后台自动运行，不打扰你用其他功能。\n'
            '业务日志只显示大白话消息（如"采集了5个商品"），技术日志显示完整细节。'
        )
        hint.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # ============ 调度器控制 ============
        btn_layout = QHBoxLayout()
        self.start_btn = QPushButton("▶ 启动调度器")
        self.start_btn.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; border: none; "
            "padding: 8px 20px; border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background: #229954; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        self.start_btn.clicked.connect(self._on_start)
        btn_layout.addWidget(self.start_btn)

        self.stop_btn = QPushButton("⏹ 停止调度器")
        self.stop_btn.setStyleSheet(
            "QPushButton { background: #e74c3c; color: white; border: none; "
            "padding: 8px 20px; border-radius: 6px; font-weight: bold; }"
            "QPushButton:hover { background: #c0392b; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        self.stop_btn.clicked.connect(self._on_stop)
        self.stop_btn.setEnabled(False)
        btn_layout.addWidget(self.stop_btn)

        btn_layout.addStretch()

        # 状态指示
        self.status_label = QLabel("● 未运行")
        self.status_label.setStyleSheet("font-size: 14px; color: #95a5a6; font-weight: bold;")
        btn_layout.addWidget(self.status_label)

        layout.addLayout(btn_layout)

        # ============ 服务控制：回调服务 + Cloudflare 隧道 ============
        svc_group = QGroupBox("服务控制（飞书回调 + 公网隧道）")
        svc_group.setStyleSheet(self._group_style())
        svc_layout = QVBoxLayout(svc_group)

        svc_hint = QLabel(
            "📦 <b>回调服务</b> = 你家门口的快递接收员，签收飞书发来的审批消息（必须开着）\n"
            "🏠 <b>公网隧道</b> = 你家的门牌号，让飞书能找到你电脑（首次自动下载 cloudflared）\n"
            "📍 <b>飞书后台请求地址</b> = 公网网址 + /callback，填到飞书两处（事件配置 + 卡片回传交互）"
        )
        svc_hint.setStyleSheet(
            "color: #606266; font-size: 12px; background: #f4f4f5; "
            "padding: 8px; border-radius: 4px; border-left: 3px solid #409eff;"
        )
        svc_hint.setWordWrap(True)
        svc_layout.addWidget(svc_hint)

        # 回调服务控制
        callback_row = QHBoxLayout()
        self.callback_start_btn = QPushButton("▶ 启动回调服务")
        self.callback_start_btn.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; border: none; "
            "padding: 6px 16px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #229954; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        self.callback_start_btn.clicked.connect(self._on_callback_start)
        callback_row.addWidget(self.callback_start_btn)

        self.callback_stop_btn = QPushButton("⏹ 停止回调服务")
        self.callback_stop_btn.setStyleSheet(
            "QPushButton { background: #e74c3c; color: white; border: none; "
            "padding: 6px 16px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #c0392b; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        self.callback_stop_btn.clicked.connect(self._on_callback_stop)
        self.callback_stop_btn.setEnabled(False)
        callback_row.addWidget(self.callback_stop_btn)

        self.callback_status_label = QLabel("● 未运行")
        self.callback_status_label.setStyleSheet(
            "font-size: 13px; color: #95a5a6; font-weight: bold;"
        )
        callback_row.addWidget(self.callback_status_label)

        callback_row.addStretch()
        svc_layout.addLayout(callback_row)

        # 隧道控制
        tunnel_row = QHBoxLayout()
        self.tunnel_start_btn = QPushButton("▶ 启动公网隧道")
        self.tunnel_start_btn.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; border: none; "
            "padding: 6px 16px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #229954; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        self.tunnel_start_btn.clicked.connect(self._on_tunnel_start)
        tunnel_row.addWidget(self.tunnel_start_btn)

        self.tunnel_stop_btn = QPushButton("⏹ 停止隧道")
        self.tunnel_stop_btn.setStyleSheet(
            "QPushButton { background: #e74c3c; color: white; border: none; "
            "padding: 6px 16px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #c0392b; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        self.tunnel_stop_btn.clicked.connect(self._on_tunnel_stop)
        self.tunnel_stop_btn.setEnabled(False)
        tunnel_row.addWidget(self.tunnel_stop_btn)

        self.tunnel_status_label = QLabel("● 未运行")
        self.tunnel_status_label.setStyleSheet(
            "font-size: 13px; color: #95a5a6; font-weight: bold;"
        )
        tunnel_row.addWidget(self.tunnel_status_label)

        self.copy_url_btn = QPushButton("📋 复制公网 URL")
        self.copy_url_btn.setStyleSheet(
            "QPushButton { background: #3498db; color: white; border: none; "
            "padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #2980b9; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        self.copy_url_btn.setEnabled(False)
        self.copy_url_btn.clicked.connect(self._on_copy_tunnel_url)
        tunnel_row.addWidget(self.copy_url_btn)

        self.copy_callback_btn = QPushButton("📋 复制完整回调地址")
        self.copy_callback_btn.setStyleSheet(
            "QPushButton { background: #9b59b6; color: white; border: none; "
            "padding: 6px 14px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #8e44ad; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        self.copy_callback_btn.setEnabled(False)
        self.copy_callback_btn.setToolTip("直接复制『公网网址 + /callback』，粘贴到飞书后台即可")
        self.copy_callback_btn.clicked.connect(self._on_copy_callback_url)
        tunnel_row.addWidget(self.copy_callback_btn)

        tunnel_row.addStretch()
        svc_layout.addLayout(tunnel_row)

        # 公网 URL 显示
        self.tunnel_url_label = QLabel("公网 URL：—（启动隧道后自动显示）")
        self.tunnel_url_label.setStyleSheet(
            "font-size: 12px; color: #7f8c8d; padding: 4px 0;"
        )
        self.tunnel_url_label.setWordWrap(True)
        svc_layout.addWidget(self.tunnel_url_label)

        # 飞书后台填写指引卡片（HTML，隧道启动前隐藏）
        self.callback_guide = QTextBrowser()
        self.callback_guide.setOpenExternalLinks(True)
        self.callback_guide.setVisible(False)
        self.callback_guide.setMaximumHeight(280)
        self.callback_guide.setStyleSheet(
            "QTextBrowser { background: #f0f9ff; border: 1px solid #bae6fd; "
            "border-radius: 6px; padding: 4px; }"
        )
        svc_layout.addWidget(self.callback_guide)

        layout.addWidget(svc_group)

        # ============ 任务列表 ============
        task_group = QGroupBox("定时任务列表")
        task_group.setStyleSheet(self._group_style())
        task_layout = QVBoxLayout(task_group)
        self.task_table = QTableWidget(0, 4)
        self.task_table.setHorizontalHeaderLabels(["任务", "说明", "触发时间", "下次执行"])
        self.task_table.horizontalHeader().stretchLastSection()
        self.task_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        task_layout.addWidget(self.task_table)
        layout.addWidget(task_group)

        # 日志区（双选项卡）
        log_group = QGroupBox("运行日志")
        log_group.setStyleSheet(self._group_style())
        log_layout = QVBoxLayout(log_group)

        self.log_tabs = QTabWidget()
        # 业务日志 tab
        self.biz_log = QTextEdit()
        self.biz_log.setReadOnly(True)
        self.biz_log.setStyleSheet("QTextEdit { background: #fafafa; border: none; }")
        self.log_tabs.addTab(self.biz_log, "📋 业务日志（大白话）")

        # 技术日志 tab
        self.tech_log = QTextEdit()
        self.tech_log.setReadOnly(True)
        self.tech_log.setStyleSheet("QTextEdit { background: #fafafa; border: none; font-family: Consolas, monospace; font-size: 12px; }")
        self.log_tabs.addTab(self.tech_log, "⚙ 技术日志（完整）")

        log_layout.addWidget(self.log_tabs)

        log_btn_layout = QHBoxLayout()
        clear_btn = QPushButton("🗑 清空日志显示")
        clear_btn.clicked.connect(self._clear_logs)
        log_btn_layout.addStretch()
        log_btn_layout.addWidget(clear_btn)
        log_layout.addLayout(log_btn_layout)

        layout.addWidget(log_group)

    def _load_tasks(self) -> None:
        """加载任务列表到表格。"""
        self.task_table.setRowCount(len(ALL_TRIGGERS))
        for i, trigger in enumerate(ALL_TRIGGERS):
            task_id = trigger.get("id", "")
            name = trigger.get("name", "")
            cron_desc = self._format_cron(trigger)
            self.task_table.setItem(i, 0, QTableWidgetItem(name))
            self.task_table.setItem(i, 1, QTableWidgetItem(self._task_desc(task_id)))
            self.task_table.setItem(i, 2, QTableWidgetItem(cron_desc))
            self.task_table.setItem(i, 3, QTableWidgetItem("—"))

    @staticmethod
    def _task_desc(task_id: str) -> str:
        """任务的通俗说明。"""
        descs = {
            "product_collection": "采集亚马逊/沃尔玛/Wayfair 热卖商品",
            "inventory_check": "检查库存，快卖完时告警",
            "daily_report": "生成销售日报（预留）",
            "data_cleanup": "清理旧数据",
            "approval_trigger": "审批兜底扫描（主触发是事件驱动）",
        }
        return descs.get(task_id, "")

    @staticmethod
    def _format_cron(trigger: dict) -> str:
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
            m = trigger["minute"]
            if isinstance(m, str) and m.startswith("*/"):
                parts.append(f"每{m[2:]}分钟")
            else:
                parts.append(f"每{m}分钟")
        return " ".join(parts) if parts else ""

    def _on_start(self) -> None:
        """启动调度器。"""
        self.start_btn.setEnabled(False)
        self.start_btn.setText("▶ 启动中...")

        self._scheduler_thread = SchedulerThread()
        self._scheduler_thread.status_changed.connect(self._on_status_changed)
        self._scheduler_thread.jobs_ready.connect(self._on_jobs_ready)
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
        self.status_label.setStyleSheet("font-size: 14px; color: #e74c3c; font-weight: bold;")

        for i in range(self.task_table.rowCount()):
            self.task_table.setItem(i, 3, QTableWidgetItem("已停止"))

        self._append_biz_log("调度器已停止")

    def _on_status_changed(self, status: str) -> None:
        """调度器状态变更。"""
        if status == "running":
            self.start_btn.setText("▶ 运行中")
            self.stop_btn.setEnabled(True)
            self.status_label.setText("● 运行中")
            self.status_label.setStyleSheet("font-size: 14px; color: #27ae60; font-weight: bold;")
            self._append_biz_log("调度器已启动，所有定时任务开始运行")
        else:
            self.start_btn.setEnabled(True)
            self.start_btn.setText("▶ 启动调度器")
            self.status_label.setText(f"● 错误: {status}")
            self.status_label.setStyleSheet("font-size: 14px; color: #e74c3c; font-weight: bold;")
            self._append_biz_log(f"调度器启动失败: {status}")

    def _on_jobs_ready(self, jobs: list) -> None:
        """任务列表就绪，更新下次执行时间。"""
        for i in range(self.task_table.rowCount()):
            task_name = self.task_table.item(i, 0).text()
            next_run = "—"
            for job in jobs:
                if task_name in str(job.get("name", "")) or job.get("id") == task_name:
                    next_run = job.get("next_run_time", "—")
                    if next_run and next_run != "None":
                        next_run = str(next_run)[:19]
                    else:
                        next_run = "—"
                    break
            self.task_table.setItem(i, 3, QTableWidgetItem(next_run))

    def _refresh(self) -> None:
        """定时刷新日志和下次执行时间。"""
        self._refresh_logs()
        # 如果调度器在运行，刷新下次执行时间
        if self._scheduler_thread and self._scheduler_thread._manager:
            try:
                jobs = self._scheduler_thread._manager.get_jobs()
                self._on_jobs_ready(jobs)
            except Exception:
                pass

    def _refresh_logs(self) -> None:
        """从日志文件读取最新内容。"""
        try:
            log_dir = Path("logs")
            if not log_dir.exists():
                return
            log_files = sorted(log_dir.glob("app_*.log"), reverse=True)
            if not log_files:
                return
            with open(log_files[0], "r", encoding="utf-8") as f:
                lines = f.readlines()[-200:]

            # 技术日志：完整内容
            tech_text = "".join(lines[-50:])
            self.tech_log.setPlainText(tech_text)

            # 业务日志：只保留业务相关行
            biz_lines = [l.rstrip() for l in lines if _is_business_line(l)]
            self.biz_log.setPlainText("\n".join(biz_lines[-30:]))
        except Exception:
            pass

    def _append_biz_log(self, msg: str) -> None:
        """追加一行到业务日志。"""
        from datetime import datetime
        timestamp = datetime.now().strftime("%H:%M:%S")
        self.biz_log.append(f"[{timestamp}] {msg}")

    def _clear_logs(self) -> None:
        """清空日志显示（只清界面，不清文件）。"""
        self.biz_log.clear()
        self.tech_log.clear()

    # ============ 回调服务控制 ============

    def _on_callback_start(self) -> None:
        """启动飞书回调服务。"""
        if self._callback_thread and self._callback_thread.isRunning():
            return

        self.callback_start_btn.setEnabled(False)
        self.callback_start_btn.setText("▶ 启动中...")
        self.callback_status_label.setText("● 启动中...")
        self.callback_status_label.setStyleSheet(
            "font-size: 13px; color: #3498db; font-weight: bold;"
        )

        self._callback_thread = CallbackServerThread()
        self._callback_thread.status_changed.connect(self._on_callback_status)
        self._callback_thread.message.connect(self._on_callback_message)
        self._callback_thread.start()

    def _on_callback_stop(self) -> None:
        """停止飞书回调服务。"""
        if self._callback_thread:
            self._callback_thread.stop()
            self._callback_thread = None

        self.callback_start_btn.setEnabled(True)
        self.callback_start_btn.setText("▶ 启动回调服务")
        self.callback_stop_btn.setEnabled(False)
        self.callback_status_label.setText("● 已停止")
        self.callback_status_label.setStyleSheet(
            "font-size: 13px; color: #e74c3c; font-weight: bold;"
        )
        self._append_biz_log("回调服务已停止")

    def _on_callback_status(self, status: str) -> None:
        """回调服务状态变更。"""
        if status == "running":
            self.callback_start_btn.setText("▶ 运行中")
            self.callback_stop_btn.setEnabled(True)
            self.callback_status_label.setText("● 运行中 (http://127.0.0.1:8000)")
            self.callback_status_label.setStyleSheet(
                "font-size: 13px; color: #27ae60; font-weight: bold;"
            )
            self._append_biz_log("回调服务已启动，监听 8000 端口")
        elif status == "stopped":
            self.callback_start_btn.setEnabled(True)
            self.callback_start_btn.setText("▶ 启动回调服务")
            self.callback_stop_btn.setEnabled(False)
            self.callback_status_label.setText("● 已停止")
            self.callback_status_label.setStyleSheet(
                "font-size: 13px; color: #95a5a6; font-weight: bold;"
            )
        elif status == "error":
            self.callback_start_btn.setEnabled(True)
            self.callback_start_btn.setText("▶ 启动回调服务")
            self.callback_status_label.setText("● 错误")
            self.callback_status_label.setStyleSheet(
                "font-size: 13px; color: #e74c3c; font-weight: bold;"
            )

    def _on_callback_message(self, msg: str) -> None:
        """回调服务的日志消息。"""
        self._append_biz_log(f"[回调] {msg}")

    # ============ Cloudflare 隧道控制 ============

    def _on_tunnel_start(self) -> None:
        """启动 Cloudflare 隧道。

        注意：不在这里预检查 cloudflared 是否安装，因为线程内部
        （CloudflareTunnelThread.run()）已有完整的自动下载逻辑。
        之前在这里调用 CloudflareTunnelThread.is_cloudflared_installed()
        会因该方法不存在而抛 AttributeError，导致按钮点击无反应。
        """
        if self._tunnel_thread and self._tunnel_thread.isRunning():
            return

        self.tunnel_start_btn.setEnabled(False)
        self.tunnel_start_btn.setText("▶ 启动中...")
        self.tunnel_status_label.setText("● 启动中...")
        self.tunnel_status_label.setStyleSheet(
            "font-size: 13px; color: #3498db; font-weight: bold;"
        )
        self.tunnel_url_label.setText("正在启动隧道，等待公网 URL 分配（约 5-10 秒）...")

        self._tunnel_thread = CloudflareTunnelThread()
        self._tunnel_thread.status_changed.connect(self._on_tunnel_status)
        self._tunnel_thread.public_url_ready.connect(self._on_tunnel_url_ready)
        self._tunnel_thread.message.connect(self._on_tunnel_message)
        self._tunnel_thread.start()

    def _on_tunnel_stop(self) -> None:
        """停止 Cloudflare 隧道。"""
        if self._tunnel_thread:
            self._tunnel_thread.stop()
            self._tunnel_thread = None

        self.tunnel_start_btn.setEnabled(True)
        self.tunnel_start_btn.setText("▶ 启动公网隧道")
        self.tunnel_stop_btn.setEnabled(False)
        self.tunnel_status_label.setText("● 已停止")
        self.tunnel_status_label.setStyleSheet(
            "font-size: 13px; color: #e74c3c; font-weight: bold;"
        )
        self.copy_url_btn.setEnabled(False)
        self.copy_callback_btn.setEnabled(False)
        self._callback_url = ""
        self.callback_guide.setVisible(False)
        self.callback_guide.clear()
        self.tunnel_url_label.setText("公网 URL：—（隧道已停止）")
        self._append_biz_log("公网隧道已停止")

    def _on_tunnel_status(self, status: str) -> None:
        """隧道状态变更。"""
        if status == "running":
            self.tunnel_start_btn.setText("▶ 运行中")
            self.tunnel_stop_btn.setEnabled(True)
            self.tunnel_status_label.setText("● 运行中")
            self.tunnel_status_label.setStyleSheet(
                "font-size: 13px; color: #27ae60; font-weight: bold;"
            )
            self._append_biz_log("公网隧道已启动")
        elif status == "downloading":
            # 自动下载 cloudflared 中，按钮禁用
            self.tunnel_start_btn.setEnabled(False)
            self.tunnel_start_btn.setText("⏬ 下载中...")
            self.tunnel_status_label.setText("● 下载中")
            self.tunnel_status_label.setStyleSheet(
                "font-size: 13px; color: #f39c12; font-weight: bold;"
            )
            self._append_biz_log("正在自动下载 cloudflared（约50MB，首次使用需下载）")
        elif status == "stopped":
            self.tunnel_start_btn.setEnabled(True)
            self.tunnel_start_btn.setText("▶ 启动公网隧道")
            self.tunnel_stop_btn.setEnabled(False)
            self.tunnel_status_label.setText("● 已停止")
            self.tunnel_status_label.setStyleSheet(
                "font-size: 13px; color: #95a5a6; font-weight: bold;"
            )
            self.copy_url_btn.setEnabled(False)
        elif status == "error":
            self.tunnel_start_btn.setEnabled(True)
            self.tunnel_start_btn.setText("▶ 启动公网隧道")
            self.tunnel_status_label.setText("● 错误")
            self.tunnel_status_label.setStyleSheet(
                "font-size: 13px; color: #e74c3c; font-weight: bold;"
            )
        elif status == "not_installed":
            self.tunnel_start_btn.setEnabled(True)
            self.tunnel_start_btn.setText("▶ 启动公网隧道")
            self.tunnel_status_label.setText("● 未安装")
            self.tunnel_status_label.setStyleSheet(
                "font-size: 13px; color: #e74c3c; font-weight: bold;"
            )

    def _on_tunnel_url_ready(self, url: str) -> None:
        """公网 URL 就绪：保存回调地址 + 渲染飞书后台填写指引卡片。"""
        full_callback_url = f"{url}/callback"
        self._callback_url = full_callback_url

        # 公网 URL 简要显示
        self.tunnel_url_label.setText(
            f"✅ 公网 URL：{url}\n"
            f"📋 完整回调地址：{full_callback_url}"
        )
        self.copy_url_btn.setEnabled(True)
        self.copy_callback_btn.setEnabled(True)

        # 渲染飞书后台填写指引卡片
        self.callback_guide.setHtml(self._build_callback_guide_html(full_callback_url))
        self.callback_guide.setVisible(True)

        # 保存到 .env，供健康检查使用
        write_env_config({"CLOUDFLARE_TUNNEL_URL": url})
        self._append_biz_log(f"公网隧道 URL: {url}")
        self._append_biz_log(f"完整回调地址: {full_callback_url}（已自动复制到剪贴板）")

        # 自动复制完整回调地址到剪贴板（用户直接去飞书后台粘贴即可）
        QGuiApplication.clipboard().setText(full_callback_url)

    @staticmethod
    def _build_callback_guide_html(callback_url: str) -> str:
        """生成飞书后台填写指引的 HTML 卡片。

        含两处填写位置的完整路径、当前回调地址高亮显示、验证方法提示。
        """
        return f"""
        <style>
            body {{
                font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
                font-size: 12px;
                line-height: 1.6;
                color: #2c3e50;
                padding: 4px 8px;
            }}
            h3 {{
                color: #2563eb;
                font-size: 14px;
                margin: 4px 0 6px 0;
                border-bottom: 1px solid #bae6fd;
                padding-bottom: 3px;
            }}
            .url-box {{
                background: #fef3c7;
                padding: 6px 10px;
                border-radius: 4px;
                font-family: Consolas, monospace;
                font-size: 12px;
                word-break: break-all;
                border: 1px dashed #f59e0b;
                margin: 6px 0;
            }}
            table {{
                border-collapse: collapse;
                width: 100%;
                margin: 6px 0;
                font-size: 12px;
            }}
            th, td {{
                border: 1px solid #d1d5db;
                padding: 5px 8px;
                text-align: left;
                vertical-align: top;
            }}
            th {{
                background: #e0f2fe;
                color: #1f2937;
                font-weight: bold;
            }}
            code {{
                font-family: Consolas, monospace;
                background: #f3f4f6;
                color: #c7254e;
                padding: 1px 4px;
                border-radius: 2px;
            }}
            .ok {{ color: #27ae60; }}
            .warn {{ color: #e67e22; }}
        </style>
        <h3>📍 飞书后台填写指引（两处都要填同一个地址）</h3>
        <p>当前完整回调地址<b>已自动复制到剪贴板</b>，可直接去飞书后台粘贴：</p>
        <div class="url-box"><b>{callback_url}</b></div>
        <p>打开 <a href="https://open.feishu.cn/">飞书开放平台</a> → 你的应用 → 左侧菜单"<b>事件与回调</b>"，找到下面 <b>两处</b>，把上面的地址粘进去：</p>
        <table>
            <tr>
                <th>位置</th>
                <th>飞书后台路径</th>
                <th>填什么</th>
            </tr>
            <tr>
                <td><b>① 事件配置</b><br><span class="warn">（接收审批状态变更）</span></td>
                <td>事件与回调 → 事件配置 → 请求地址</td>
                <td rowspan="2" style="vertical-align:middle;">
                    <code>{callback_url}</code><br>
                    <span class="warn">（两处填 <b>同一个</b> 地址）</span>
                </td>
            </tr>
            <tr>
                <td><b>② 卡片回传交互</b><br><span class="warn">（接收审批卡片按钮点击）</span></td>
                <td>事件与回调 → 回调设置 → 卡片回传交互 → 回调地址</td>
            </tr>
        </table>
        <p class="ok">✅ 两处都点"保存"或"验证"按钮，飞书会自动发验证码到本地回调服务，验证通过说明配置成功。</p>
        <p class="warn">⚠️ 临时隧道每次重启网址会变，需要重新填到飞书后台。生产环境建议用固定隧道。</p>
        """

    def _on_copy_callback_url(self) -> None:
        """复制完整回调地址（公网 URL + /callback）到剪贴板。"""
        if not self._callback_url:
            return
        QGuiApplication.clipboard().setText(self._callback_url)
        self._append_biz_log(f"已复制完整回调地址: {self._callback_url}")

    def _on_tunnel_message(self, msg: str) -> None:
        """隧道的日志消息（追加到技术日志，不打扰业务日志）。"""
        # 隧道日志偏技术，放技术日志即可
        self.tech_log.append(f"[tunnel] {msg}")

    def _on_copy_tunnel_url(self) -> None:
        """复制公网 URL 到剪贴板。"""
        clipboard = QGuiApplication.clipboard()
        url = self.tunnel_url_label.text()
        # 提取公网 URL（第一行 "✅ 公网 URL：xxx" 中的 xxx）
        for line in url.split("\n"):
            if "公网 URL：" in line:
                url_only = line.split("公网 URL：", 1)[1].strip()
                clipboard.setText(url_only)
                self._append_biz_log(f"已复制公网 URL 到剪贴板: {url_only}")
                return
        # 兜底：复制全部文本
        clipboard.setText(url)

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
