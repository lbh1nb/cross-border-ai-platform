"""Cloudflare Tunnel 内网穿透线程。

把 cloudflared（Cloudflare Tunnel）封装到 QThread 里，
让 GUI 点按钮就能启动内网穿透，把本地 8000 端口暴露到公网。

特点：
- 无需登录、无需 token，免费临时隧道（trycloudflare.com 域名）
- 启动后从 stdout 解析公网 URL
- 通过信号通知 GUI 状态变化和 URL 就绪
- 未安装 cloudflared 时自动下载到 exe 同目录

前置条件：
    首次使用时会自动下载 cloudflared（约 50MB），
    业务用户无需去 GitHub 下载、无需配置环境变量。
"""

from __future__ import annotations

import re
import subprocess
import threading

from PySide6.QtCore import QThread, Signal

from src.gui.services.cloudflared_downloader import (
    ensure_cloudflared,
    get_cloudflared_executable,
    is_cloudflared_available,
)


# 匹配 trycloudflare.com 临时隧道的公网 URL
_URL_PATTERN = re.compile(r"https://[a-z0-9-]+\.trycloudflare\.com")

# 本地服务地址（FastAPI 回调服务监听的端口）
_LOCAL_URL = "http://127.0.0.1:8000"

# Windows 下避免弹出控制台窗口的标志（非 Windows 平台为 0）
_NO_WINDOW_FLAGS = getattr(subprocess, "CREATE_NO_WINDOW", 0)


class CloudflareTunnelThread(QThread):
    """Cloudflare Tunnel 内网穿透线程。

    在后台线程启动 cloudflared 进程，把本地 8000 端口暴露到公网。
    通过信号通知 GUI 当前状态、公网 URL 和日志消息。

    信号:
        status_changed: 状态变化（starting/running/stopped/error/not_installed/downloading）
        public_url_ready: 公网 URL 就绪
        message: 日志消息
    """

    # 状态信号：starting/running/stopped/error/not_installed/downloading
    status_changed = Signal(str)
    # 公网 URL 就绪信号
    public_url_ready = Signal(str)
    # 日志消息信号
    message = Signal(str)

    def __init__(self, parent=None) -> None:
        """初始化线程。

        Args:
            parent: 父 QObject
        """
        super().__init__(parent)
        # cloudflared 子进程
        self._process: subprocess.Popen | None = None
        # 读取 stdout 的辅助线程
        self._reader_thread: threading.Thread | None = None
        # 停止标志，用于通知 reader 线程退出
        self._stop_flag = threading.Event()

    def run(self) -> None:
        """线程入口：启动 cloudflared 并解析公网 URL。

        流程:
            1. 检查 cloudflared 是否可用，未安装则自动下载
            2. 启动 cloudflared 子进程
            3. 后台线程读取 stdout，正则匹配公网 URL
            4. 找到 URL 后 emit public_url_ready 和 running 状态
            5. 进程结束后 emit stopped
        """
        # 检查是否可用，未安装则自动下载
        if not is_cloudflared_available():
            self.message.emit("cloudflared 未安装，正在自动下载...")
            self.status_changed.emit("downloading")

            ok, msg = ensure_cloudflared()
            if not ok:
                self.message.emit(f"❌ {msg}")
                self.status_changed.emit("not_installed")
                return

            self.message.emit(f"✅ {msg}")

        # 获取 cloudflared 可执行文件路径（PATH 或本地目录）
        executable = get_cloudflared_executable()
        if not executable:
            self.message.emit("❌ 无法找到 cloudflared 可执行文件")
            self.status_changed.emit("not_installed")
            return

        self.message.emit(f"正在启动 cloudflared 隧道...\n使用：{executable}")
        self.status_changed.emit("starting")

        try:
            # 启动 cloudflared，把本地 8000 端口暴露到公网
            # --url 指定本地服务地址，使用临时隧道（无需 token）
            self._process = subprocess.Popen(
                [executable, "tunnel", "--url", _LOCAL_URL],
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
                encoding="utf-8",
                errors="replace",
                # 避免弹出控制台窗口（Windows）
                creationflags=_NO_WINDOW_FLAGS,
            )
        except Exception as exc:
            self.message.emit(f"启动 cloudflared 失败: {exc}")
            self.status_changed.emit("error")
            return

        # 重置停止标志
        self._stop_flag.clear()

        # 启动后台线程读取 stdout，解析公网 URL
        self._reader_thread = threading.Thread(
            target=self._read_output, daemon=True
        )
        self._reader_thread.start()

        # 等待 cloudflared 进程结束
        try:
            self._process.wait()
        except Exception as exc:
            self.message.emit(f"cloudflared 运行异常: {exc}")
            self.status_changed.emit("error")
            return

        # 通知 reader 线程退出
        self._stop_flag.set()
        if self._reader_thread is not None:
            self._reader_thread.join(timeout=2)

        self.message.emit("cloudflared 隧道已停止")
        self.status_changed.emit("stopped")

    def _read_output(self) -> None:
        """读取 cloudflared 的 stdout，解析公网 URL。

        逐行读取输出，正则匹配 trycloudflare.com 的 URL。
        找到后 emit public_url_ready 和 running 状态。
        """
        if self._process is None or self._process.stdout is None:
            return

        url_found = False

        try:
            for line in iter(self._process.stdout.readline, ""):
                if self._stop_flag.is_set():
                    break

                line = line.rstrip()
                if not line:
                    continue

                # 把 cloudflared 的日志转发给 GUI
                self.message.emit(line)

                # 还没找到 URL 时尝试匹配
                if not url_found:
                    match = _URL_PATTERN.search(line)
                    if match:
                        public_url = match.group(0)
                        url_found = True
                        self.message.emit(f"✅ 公网 URL 已就绪: {public_url}")
                        self.public_url_ready.emit(public_url)
                        self.status_changed.emit("running")
        except Exception as exc:
            self.message.emit(f"读取 cloudflared 输出失败: {exc}")
            self.status_changed.emit("error")

    def stop(self) -> None:
        """停止 cloudflared 进程。

        先设置停止标志通知 reader 线程退出，再 terminate() 终止子进程。
        """
        if self._process is None:
            return

        self.message.emit("正在停止 cloudflared 隧道...")

        # 通知 reader 线程退出
        self._stop_flag.set()

        try:
            self._process.terminate()
        except Exception as exc:
            self.message.emit(f"终止 cloudflared 失败: {exc}")
