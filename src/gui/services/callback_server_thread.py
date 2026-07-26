"""飞书卡片回调服务的 QThread 封装。

把 FastAPI 回调服务封装到 QThread 里，让 GUI 点按钮就能启动/停止回调服务，
不用开终端执行 `uvicorn src.feishu.card_callback:app`。

设计要点：
- 不用 `uvicorn.run()`（它内部创建 Server 并阻塞，无法外部停止）
- 改用 `uvicorn.Config` + `uvicorn.Server`，self._server.run() 阻塞运行，
  stop() 通过 `self._server.should_exit = True` 通知 uvicorn 优雅退出
- 状态变化通过 status_changed 信号通知 UI 切换按钮状态
- 运行日志通过 message 信号通知 UI 追加到日志框

信号说明：
    status_changed: 状态变化（"starting"/"running"/"stopped"/"error"）
    message:        日志消息（启动地址、停止提示、异常信息等）
"""

from __future__ import annotations

import uvicorn
from PySide6.QtCore import QThread, Signal

# 回调服务的 FastAPI app 导入路径（uvicorn 用字符串导入，避免提前 import 触发副作用）
_CALLBACK_APP = "src.feishu.card_callback:app"
# 监听地址和端口（与 start_callback_server.py 保持一致）
_HOST = "0.0.0.0"
_PORT = 8000
_LOG_LEVEL = "info"


class CallbackServerThread(QThread):
    """后台运行 uvicorn 回调服务的线程。

    用法（在 GUI 页面里）：
        self._thread = CallbackServerThread()
        self._thread.status_changed.connect(self._on_status_changed)
        self._thread.message.connect(self._on_log)
        self._thread.start()   # 启动服务
        ...
        self._thread.stop()    # 停止服务
    """

    # 状态变化信号：starting / running / stopped / error
    status_changed = Signal(str)
    # 日志消息信号（UI 追加到日志框）
    message = Signal(str)

    def __init__(self) -> None:
        super().__init__()
        # uvicorn.Server 实例，run() 中创建，stop() 中使用
        self._server: uvicorn.Server | None = None

    def run(self) -> None:
        """线程入口：启动 uvicorn 服务（阻塞，直到 stop() 或异常退出）。"""
        self.status_changed.emit("starting")
        self.message.emit(f"正在启动回调服务: http://{_HOST}:{_PORT}")

        try:
            # 用 Config + Server 方式，便于外部通过 should_exit 优雅停止
            config = uvicorn.Config(
                _CALLBACK_APP,
                host=_HOST,
                port=_PORT,
                log_level=_LOG_LEVEL,
            )
            self._server = uvicorn.Server(config)

            # 标记为已就绪（uvicorn 内部日志会输出 "Uvicorn running on ..."）
            self.status_changed.emit("running")
            self.message.emit("回调服务已启动，监听 /callback 和 /health 端点")

            # 阻塞运行，直到 should_exit=True 或收到中断信号
            self._server.run()
        except Exception as e:
            self.status_changed.emit("error")
            self.message.emit(f"回调服务异常: {e}")
        finally:
            # 走到这里说明服务已退出（无论正常停止还是异常）
            self._server = None
            self.status_changed.emit("stopped")
            self.message.emit("回调服务已停止")

    def stop(self) -> None:
        """停止 uvicorn 服务。

        通过设置 should_exit=True 通知 uvicorn Server 优雅退出，
        不强制 terminate 线程（避免 event loop 被强杀导致资源泄漏）。
        """
        if self._server is not None:
            self.message.emit("正在停止回调服务...")
            self._server.should_exit = True
