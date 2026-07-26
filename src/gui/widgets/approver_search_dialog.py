"""审批人搜索对话框。

让业务用户在 GUI 里输入姓名就能查到 open_id，
不用手动到飞书开放平台复制 ou_ 字符串。

典型用法：
    result = ApproverSearchDialog.pick_approver(parent)
    if result:
        open_id, name = result
        # 写入 .env 或规则配置

UI 结构：
    ┌─────────────────────────────────────────┐
    │  [姓名输入框]            [搜索]         │
    ├─────────────────────────────────────────┤
    │  姓名 │ 部门 │ 职位 │ open_id          │
    │  ─────┼──────┼──────┼────────────────  │
    │  ...  │ ...  │ ...  │ ou_xxxxxxxx...   │
    ├─────────────────────────────────────────┤
    │            [选中此人]  [取消]           │
    └─────────────────────────────────────────┘

搜索在 QThread 后台执行，避免阻塞主线程。
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QDialog,
    QHBoxLayout,
    QHeaderView,
    QLabel,
    QLineEdit,
    QMessageBox,
    QPushButton,
    QTableWidget,
    QTableWidgetItem,
    QVBoxLayout,
)

from src.gui.services.approver_search_service import search_user


class SearchThread(QThread):
    """后台搜索飞书用户的线程。

    把 search_user 这个可能阻塞的网络请求放到子线程执行，
    避免搜索时 UI 卡死。结果通过 result_ready 信号回主线程。
    """

    # 搜索完成信号：参数为用户列表（每项含 open_id/name/department_name/job_title）
    result_ready = Signal(list)

    def __init__(self, keyword: str) -> None:
        super().__init__()
        self._keyword = keyword

    def run(self) -> None:
        """线程入口：执行搜索并发射结果。"""
        try:
            items = search_user(self._keyword)
        except Exception:
            # 服务层已吞异常返回空列表，这里兜底防止线程崩
            items = []
        self.result_ready.emit(items)


class ApproverSearchDialog(QDialog):
    """审批人搜索对话框。

    业务用户输入姓名 → 后台搜索飞书通讯录 → 表格展示候选 →
    双击或点"选中此人"确认 → 通过 selected_open_id / selected_name 暴露结果。

    Attributes:
        selected_open_id: 选中的用户 open_id（ou_ 开头）。
        selected_name: 选中的用户姓名。
    """

    # 表格列定义（顺序与表头一致）
    _COL_NAME = 0
    _COL_DEPT = 1
    _COL_TITLE = 2
    _COL_OPEN_ID = 3
    _COLUMN_HEADERS = ["姓名", "部门", "职位", "open_id"]

    # open_id 列显示前缀长度（前 10 位 + "..."）
    _OPEN_ID_DISPLAY_PREFIX_LEN = 10

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self.setWindowTitle("搜索审批人")
        self.resize(640, 480)

        # 选中的结果，accept 前会被填充
        self.selected_open_id: str = ""
        self.selected_name: str = ""

        # 后台线程引用，防止被 GC 提前回收
        self._search_thread: SearchThread | None = None

        self._init_ui()
        self._connect_signals()

    # ------------------------------------------------------------------
    # UI 构建
    # ------------------------------------------------------------------
    def _init_ui(self) -> None:
        """构建界面：顶部搜索栏 / 中间结果表格 / 底部操作按钮。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(20, 20, 20, 20)
        layout.setSpacing(12)

        # —— 顶部：标题 + 说明 ——
        title = QLabel("搜索审批人")
        title.setStyleSheet("font-size: 18px; font-weight: bold; color: #1a1a1a;")
        layout.addWidget(title)

        hint = QLabel("输入姓名点搜索，从飞书通讯录里找到对应的 open_id。")
        hint.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        layout.addWidget(hint)

        # —— 搜索栏：输入框 + 搜索按钮 ——
        search_row = QHBoxLayout()
        search_row.setSpacing(8)

        self.keyword_input = QLineEdit()
        self.keyword_input.setPlaceholderText("请输入审批人姓名，如：张三")
        self.keyword_input.setClearButtonEnabled(True)
        search_row.addWidget(self.keyword_input, stretch=1)

        self.search_btn = QPushButton("搜索")
        self.search_btn.setEnabled(False)  # 初始禁用，输入文字后才启用
        self.search_btn.setStyleSheet(
            "QPushButton { background: #2980b9; color: white; border: none; "
            "padding: 6px 18px; border-radius: 4px; font-weight: 500; }"
            "QPushButton:hover { background: #21618c; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        search_row.addWidget(self.search_btn)

        layout.addLayout(search_row)

        # —— 中间：结果表格 ——
        self.result_table = QTableWidget(0, len(self._COLUMN_HEADERS))
        self.result_table.setHorizontalHeaderLabels(self._COLUMN_HEADERS)
        self.result_table.setEditTriggers(QTableWidget.EditTrigger.NoEditTriggers)
        self.result_table.setSelectionBehavior(
            QTableWidget.SelectionBehavior.SelectRows
        )
        self.result_table.setSelectionMode(QTableWidget.SelectionMode.SingleSelection)
        self.result_table.horizontalHeader().stretchLastSection = True
        self.result_table.verticalHeader().setVisible(False)
        # 隔行变色，提升可读性
        self.result_table.setAlternatingRowColors(True)
        self.result_table.setSortingEnabled(False)
        layout.addWidget(self.result_table, stretch=1)

        # 空状态提示（无结果时显示）
        self.empty_label = QLabel("暂无搜索结果，请输入姓名后点搜索。")
        self.empty_label.setStyleSheet(
            "color: #95a5a6; font-size: 13px; padding: 30px; "
            "background: #f8f9fa; border-radius: 8px;"
        )
        self.empty_label.setAlignment(Qt.AlignmentFlag.AlignCenter)
        layout.addWidget(self.empty_label)

        # —— 底部：操作按钮 ——
        btn_row = QHBoxLayout()
        btn_row.addStretch()

        self.confirm_btn = QPushButton("选中此人")
        self.confirm_btn.setEnabled(False)  # 未选中行前禁用
        self.confirm_btn.setStyleSheet(
            "QPushButton { background: #27ae60; color: white; border: none; "
            "padding: 6px 18px; border-radius: 4px; font-weight: 500; }"
            "QPushButton:hover { background: #229954; }"
            "QPushButton:disabled { background: #bdc3c7; }"
        )
        btn_row.addWidget(self.confirm_btn)

        self.cancel_btn = QPushButton("取消")
        self.cancel_btn.setStyleSheet(
            "QPushButton { background: #ecf0f1; color: #2c3e50; border: none; "
            "padding: 6px 18px; border-radius: 4px; }"
            "QPushButton:hover { background: #d5dbdb; }"
        )
        btn_row.addWidget(self.cancel_btn)

        layout.addLayout(btn_row)

    # ------------------------------------------------------------------
    # 信号连接
    # ------------------------------------------------------------------
    def _connect_signals(self) -> None:
        """绑定按钮 / 输入框 / 表格的事件。"""
        self.keyword_input.textChanged.connect(self._on_keyword_changed)
        self.search_btn.clicked.connect(self._on_search_clicked)
        self.confirm_btn.clicked.connect(self._on_confirm_clicked)
        self.cancel_btn.clicked.connect(self.reject)

        # 回车直接搜索
        self.keyword_input.returnPressed.connect(self._on_search_clicked)

        # 选中行变化时启用/禁用"选中此人"
        self.result_table.itemSelectionChanged.connect(
            self._on_selection_changed
        )
        # 双击行直接确认
        self.result_table.doubleClicked.connect(self._on_confirm_clicked)

    # ------------------------------------------------------------------
    # 事件处理
    # ------------------------------------------------------------------
    def _on_keyword_changed(self, text: str) -> None:
        """输入框文字变化：空时禁用搜索按钮，非空时启用。"""
        self.search_btn.setEnabled(bool(text.strip()))

    def _on_search_clicked(self) -> None:
        """点击搜索：启动后台线程，禁用按钮防止重复点。"""
        keyword = self.keyword_input.text().strip()
        if not keyword:
            return

        # 上一次搜索还没结束，先停掉旧线程
        if self._search_thread is not None and self._search_thread.isRunning():
            self._search_thread.quit()
            self._search_thread.wait()

        self.search_btn.setEnabled(False)
        self.search_btn.setText("搜索中...")

        self._search_thread = SearchThread(keyword)
        self._search_thread.result_ready.connect(self._on_search_done)
        self._search_thread.start()

    def _on_search_done(self, items: list) -> None:
        """搜索结果回来：填表格，恢复按钮状态。"""
        self.search_btn.setEnabled(True)
        self.search_btn.setText("搜索")

        self.result_table.setRowCount(0)
        self.confirm_btn.setEnabled(False)

        if not items:
            self.empty_label.setText("未找到匹配的用户，换个姓名再试。")
            self.empty_label.show()
            self.result_table.hide()
            return

        self.empty_label.hide()
        self.result_table.show()
        self.result_table.setRowCount(len(items))

        for row, user in enumerate(items):
            name = user.get("name", "") or ""
            dept = user.get("department_name", "") or ""
            title = user.get("job_title", "") or ""
            open_id = user.get("open_id", "") or ""

            self._set_cell(row, self._COL_NAME, name)
            self._set_cell(row, self._COL_DEPT, dept)
            self._set_cell(row, self._COL_TITLE, title)
            # open_id 列：显示截断值，完整值挂在 UserRole 上
            display_id = self._truncate_open_id(open_id)
            id_item = QTableWidgetItem(display_id)
            id_item.setData(Qt.ItemDataRole.UserRole, open_id)
            id_item.setToolTip(open_id)  # 鼠标悬停看完整值
            self.result_table.setItem(row, self._COL_OPEN_ID, id_item)

    def _on_selection_changed(self) -> None:
        """表格选中行变化：是否启用"选中此人"。"""
        has_selection = bool(self.result_table.selectedItems())
        self.confirm_btn.setEnabled(has_selection)

    def _on_confirm_clicked(self) -> None:
        """确认选中：从当前行取 open_id 和姓名，accept 关闭对话框。"""
        current_row = self.result_table.currentRow()
        if current_row < 0:
            QMessageBox.information(self, "提示", "请先在表格里选中一位用户。")
            return

        name_item = self.result_table.item(current_row, self._COL_NAME)
        id_item = self.result_table.item(current_row, self._COL_OPEN_ID)
        if name_item is None or id_item is None:
            return

        name = name_item.text() or ""
        # 完整 open_id 存在 UserRole，取出来
        open_id = id_item.data(Qt.ItemDataRole.UserRole) or ""

        if not open_id:
            QMessageBox.warning(self, "提示", "该用户缺少 open_id，无法选中。")
            return

        self.selected_open_id = open_id
        self.selected_name = name
        self.accept()

    # ------------------------------------------------------------------
    # 工具方法
    # ------------------------------------------------------------------
    def _set_cell(self, row: int, col: int, text: str) -> None:
        """往表格指定单元格塞文本。"""
        item = QTableWidgetItem(text)
        # 文本类型的列对齐到左侧
        if col == self._COL_NAME:
            item.setTextAlignment(
                Qt.AlignmentFlag.AlignVCenter | Qt.AlignmentFlag.AlignLeft
            )
        self.result_table.setItem(row, col, item)

    @classmethod
    def _truncate_open_id(cls, open_id: str) -> str:
        """open_id 截断显示：前 10 位 + '...'，空值返回空串。"""
        if not open_id:
            return ""
        if len(open_id) <= cls._OPEN_ID_DISPLAY_PREFIX_LEN:
            return open_id
        return open_id[: cls._OPEN_ID_DISPLAY_PREFIX_LEN] + "..."

    # ------------------------------------------------------------------
    # 静态便捷入口
    # ------------------------------------------------------------------
    @staticmethod
    def pick_approver(parent=None) -> tuple[str, str] | None:
        """打开对话框选一个审批人。

        Args:
            parent: 父窗口。

        Returns:
            选中返回 (open_id, name)；用户取消返回 None。
        """
        dialog = ApproverSearchDialog(parent)
        if dialog.exec() == QDialog.DialogCode.Accepted:
            if dialog.selected_open_id:
                return dialog.selected_open_id, dialog.selected_name
        return None
