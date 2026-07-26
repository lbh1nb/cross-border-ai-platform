"""群聊搜索对话框。

业务用户点"搜索群聊"按钮后弹出此对话框，
自动列出机器人已加入的所有群聊，
用户点选一个即可自动填入 chat_id。

用法：
    result = ChatSearchDialog.pick_chat(parent)
    if result:
        chat_id, chat_name = result
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QMessageBox,
    QPushButton,
    QVBoxLayout,
)

from src.gui.services.chat_search_service import list_bot_chats


class _ListChatsThread(QThread):
    """后台列出群聊，避免阻塞 UI。"""
    result_ready = Signal(list)
    error_occurred = Signal(str)

    def run(self) -> None:
        try:
            items = list_bot_chats()
            self.result_ready.emit(items)
        except Exception as e:
            self.error_occurred.emit(str(e))
            self.result_ready.emit([])


class ChatSearchDialog(QDialog):
    """群聊搜索对话框：列出机器人所在群聊，用户点选一个。"""

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("选择群聊")
        self.resize(500, 400)
        self._list_thread: _ListChatsThread | None = None
        self._selected_chat_id: str = ""
        self._selected_chat_name: str = ""
        self._init_ui()
        self._auto_load()

    def _init_ui(self) -> None:
        layout = QVBoxLayout(self)
        layout.setContentsMargins(16, 16, 16, 16)
        layout.setSpacing(10)

        # 标题
        title = QLabel("📋 应用机器人已加入的群聊")
        title.setStyleSheet("font-size: 15px; font-weight: bold; color: #1a1a1a;")
        layout.addWidget(title)

        # 说明
        hint = QLabel(
            "下方列表自动显示机器人所在的所有群聊，点选一个群聊后点『确定』。\n"
            "如果列表为空，请先把应用机器人加入到目标群聊。"
        )
        hint.setStyleSheet("color: #7f8c8d; font-size: 12px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 群聊列表
        self.chat_list = QListWidget()
        self.chat_list.setStyleSheet(
            "QListWidget { border: 1px solid #dcdfe6; border-radius: 4px; "
            "background: #ffffff; }"
            "QListWidget::item { padding: 8px 12px; border-bottom: 1px solid #f0f0f0; }"
            "QListWidget::item:selected { background: #ecf5ff; color: #409eff; }"
        )
        self.chat_list.itemDoubleClicked.connect(self._on_item_double_click)
        layout.addWidget(self.chat_list)

        # 按钮区
        btn_layout = QHBoxLayout()

        self.refresh_btn = QPushButton("🔄 重新加载")
        self.refresh_btn.setStyleSheet(
            "QPushButton { background: #f5f7fa; color: #606266; "
            "border: 1px solid #dcdfe6; padding: 6px 14px; border-radius: 4px; }"
            "QPushButton:hover { background: #ecf5ff; }"
        )
        self.refresh_btn.clicked.connect(self._auto_load)
        btn_layout.addWidget(self.refresh_btn)

        btn_layout.addStretch()

        self.ok_btn = QPushButton("✓ 确定")
        self.ok_btn.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; border: none; "
            "padding: 6px 20px; border-radius: 4px; font-weight: bold; }"
            "QPushButton:hover { background: #229954; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        self.ok_btn.setEnabled(False)
        self.ok_btn.clicked.connect(self._on_accept)
        btn_layout.addWidget(self.ok_btn)

        cancel_btn = QPushButton("取消")
        cancel_btn.setStyleSheet(
            "QPushButton { background: #f5f7fa; color: #606266; "
            "border: 1px solid #dcdfe6; padding: 6px 20px; border-radius: 4px; }"
            "QPushButton:hover { background: #f0f0f0; }"
        )
        cancel_btn.clicked.connect(self.reject)
        btn_layout.addWidget(cancel_btn)

        layout.addLayout(btn_layout)

        # 群聊列表选择变化时启用确定按钮
        self.chat_list.itemClicked.connect(self._on_item_clicked)

    def _auto_load(self) -> None:
        """自动加载群聊列表。"""
        self.chat_list.clear()
        self.chat_list.addItem("正在加载群聊列表...")
        self.refresh_btn.setEnabled(False)
        self.refresh_btn.setText("🔄 加载中...")
        self.ok_btn.setEnabled(False)

        self._list_thread = _ListChatsThread()
        self._list_thread.result_ready.connect(self._on_loaded)
        self._list_thread.error_occurred.connect(self._on_error)
        self._list_thread.start()

    def _on_error(self, msg: str) -> None:
        """加载出错。"""
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("🔄 重新加载")
        self.chat_list.clear()
        self.chat_list.addItem(f"❌ 加载失败：{msg}")

    def _on_loaded(self, items: list) -> None:
        """加载完成。"""
        self.refresh_btn.setEnabled(True)
        self.refresh_btn.setText("🔄 重新加载")
        self.chat_list.clear()

        if not items:
            self.chat_list.addItem(
                "❌ 未找到群聊\n\n"
                "可能原因：\n"
                "1. 凭证未配置或无效（去系统配置页检查）\n"
                "2. 应用缺少 im:chat:readonly 权限\n"
                "3. 机器人还没加入任何群聊\n\n"
                "👉 请先把应用机器人加入到目标群聊"
            )
            return

        for item in items:
            chat_id = item.get("chat_id", "")
            name = item.get("name", "未命名群聊")
            desc = item.get("description", "")
            display = f"💬 {name}"
            if desc:
                display += f"  （{desc[:30]}）"
            display += f"\n   chat_id: {chat_id}"

            list_item = QListWidgetItem(display)
            list_item.setData(Qt.ItemDataRole.UserRole, (chat_id, name))
            self.chat_list.addItem(list_item)

    def _on_item_clicked(self, item: QListWidgetItem) -> None:
        """点击列表项时启用确定按钮。"""
        data = item.data(Qt.ItemDataRole.UserRole)
        self.ok_btn.setEnabled(bool(data))

    def _on_item_double_click(self, item: QListWidgetItem) -> None:
        """双击直接确定。"""
        if item.data(Qt.ItemDataRole.UserRole):
            self._on_accept()

    def _on_accept(self) -> None:
        """确定选择。"""
        current = self.chat_list.currentItem()
        if not current:
            return
        data = current.data(Qt.ItemDataRole.UserRole)
        if not data:
            return
        self._selected_chat_id, self._selected_chat_name = data
        self.accept()

    @staticmethod
    def pick_chat(parent=None) -> tuple[str, str] | None:
        """弹出对话框让用户选择群聊。

        Args:
            parent: 父窗口

        Returns:
            (chat_id, chat_name) 元组，用户取消返回 None
        """
        dialog = ChatSearchDialog(parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog._selected_chat_id:
                return (dialog._selected_chat_id, dialog._selected_chat_name)
        return None
