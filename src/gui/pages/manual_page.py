"""操作手册查看页面。

让业务用户在 GUI 内直接查看《业务用户操作手册.md》，
不用离开程序去翻文件。手册是完整的使用指南，
覆盖从零开始配置到日常使用的全部流程。

设计要点：
- 自动定位手册文件（打包模式 / 开发模式）
- 简单的 Markdown → HTML 转换（不依赖外部库）
- 缺失文件时显示友好提示，不报错
- 支持"刷新"和"在浏览器中打开"
"""

from __future__ import annotations

import os
import re
import subprocess
import sys
from pathlib import Path

from PySide6.QtCore import Qt
from PySide6.QtWidgets import (
    QHBoxLayout,
    QLabel,
    QPushButton,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)


def _resolve_manual_path() -> Path:
    """获取操作手册文件路径。

    打包模式（PyInstaller frozen）：exe 同目录下的"业务用户操作手册.md"
    开发模式：项目根目录下的 docs/业务用户操作手册.md

    路径解析方式参考 env_service._resolve_env_path。
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / "业务用户操作手册.md"
    # 当前文件：src/gui/pages/manual_page.py
    # 项目根目录：parent.parent.parent
    return (
        Path(__file__).resolve().parent.parent.parent.parent
        / "docs"
        / "业务用户操作手册.md"
    )


def _escape_html(text: str) -> str:
    """转义 HTML 特殊字符，避免手册内容被当成 HTML 解析。"""
    return (
        text.replace("&", "&amp;")
        .replace("<", "&lt;")
        .replace(">", "&gt;")
    )


def _markdown_to_html(md: str) -> str:
    """把 Markdown 转成 HTML。

    支持的语法（够用即可，不做完美解析）：
    - 标题 # / ## / ### / ####
    - 加粗 **text**
    - 行内代码 `code`
    - 代码块 ```...```
    - 无序列表 - / *
    - 有序列表 1.
    - 表格 | a | b |
    - 段落（其余文本用 <p> 包裹）

    Args:
        md: Markdown 原文

    Returns:
        HTML 字符串（不含 <html><body> 包裹，留给 QTextBrowser 设置）
    """
    if not md.strip():
        return ""

    # 1. 先抽出代码块（避免被其他规则破坏）
    code_blocks: list[str] = []
    pattern_code_block = re.compile(r"```([^\n`]*)\n(.*?)```", re.DOTALL)
    # 用占位符替换代码块，等其它转换做完再放回去
    def _stash_code_block(match: re.Match) -> str:
        lang = (match.group(1) or "").strip()
        code = match.group(2)
        code_blocks.append(code)
        idx = len(code_blocks) - 1
        # 语言标识暂时不用，保留占位符即可
        _ = lang
        return f"\x00CODEBLOCK{idx}\x00"

    md = pattern_code_block.sub(_stash_code_block, md)

    # 2. 按行处理：标题、列表、表格、段落
    lines = md.split("\n")
    html_lines: list[str] = []
    in_ul = False  # 无序列表开关
    in_ol = False  # 有序列表开关
    in_table = False
    table_rows: list[list[str]] = []

    def _close_lists() -> None:
        nonlocal in_ul, in_ol
        if in_ul:
            html_lines.append("</ul>")
            in_ul = False
        if in_ol:
            html_lines.append("</ol>")
            in_ol = False

    def _close_table() -> None:
        nonlocal in_table, table_rows
        if in_table and table_rows:
            html_lines.append("<table>")
            for i, row in enumerate(table_rows):
                html_lines.append("<tr>")
                tag = "th" if i == 0 else "td"
                for cell in row:
                    html_lines.append(f"<{tag}>{cell.strip()}</{tag}>")
                html_lines.append("</tr>")
            html_lines.append("</table>")
        in_table = False
        table_rows = []

    for raw_line in lines:
        line = raw_line.rstrip()

        # 空行：结束当前块
        if not line.strip():
            _close_lists()
            _close_table()
            continue

        # 标题
        m_head = re.match(r"^(#{1,6})\s+(.*)$", line)
        if m_head:
            _close_lists()
            _close_table()
            level = len(m_head.group(1))
            text = _inline_format(m_head.group(2))
            html_lines.append(f"<h{level}>{text}</h{level}>")
            continue

        # 代码块占位符（独占一行）
        m_code_ph = re.match(r"^\x00CODEBLOCK(\d+)\x00$", line.strip())
        if m_code_ph:
            _close_lists()
            _close_table()
            idx = int(m_code_ph.group(1))
            code = code_blocks[idx]
            escaped = _escape_html(code)
            html_lines.append(
                f'<pre><code>{escaped}</code></pre>'
            )
            continue

        # 无序列表
        m_ul = re.match(r"^[\-\*]\s+(.*)$", line)
        if m_ul:
            _close_table()
            if in_ol:
                html_lines.append("</ol>")
                in_ol = False
            if not in_ul:
                html_lines.append("<ul>")
                in_ul = True
            text = _inline_format(m_ul.group(1))
            html_lines.append(f"<li>{text}</li>")
            continue

        # 有序列表
        m_ol = re.match(r"^\d+\.\s+(.*)$", line)
        if m_ol:
            _close_table()
            if in_ul:
                html_lines.append("</ul>")
                in_ul = False
            if not in_ol:
                html_lines.append("<ol>")
                in_ol = True
            text = _inline_format(m_ol.group(1))
            html_lines.append(f"<li>{text}</li>")
            continue

        # 表格行（包含 |）
        if "|" in line and line.strip().startswith("|"):
            _close_lists()
            # 跳过分隔行 | --- | --- |
            if re.match(r"^\|[\s\-:|]+\|$", line.strip()):
                in_table = True
                continue
            cells = [c for c in line.strip().strip("|").split("|")]
            table_rows.append(cells)
            in_table = True
            continue

        # 普通段落
        _close_lists()
        _close_table()
        text = _inline_format(line)
        html_lines.append(f"<p>{text}</p>")

    # 收尾
    _close_lists()
    _close_table()

    return "\n".join(html_lines)


def _inline_format(text: str) -> str:
    """处理行内格式：加粗、行内代码、链接。

    Args:
        text: 单行文本（不含块级标记）

    Returns:
        处理后的 HTML 片段
    """
    # 先转义，再做替换（避免把用户输入的 < > 当标签）
    text = _escape_html(text)
    # 加粗 **text**
    text = re.sub(r"\*\*([^\*]+?)\*\*", r"<strong>\1</strong>", text)
    # 斜体 *text*（避免和加粗冲突，要求两侧紧贴非 * 字符）
    text = re.sub(r"(?<!\*)\*([^\*]+?)\*(?!\*)", r"<em>\1</em>", text)
    # 行内代码 `code`
    text = re.sub(r"`([^`]+?)`", r"<code>\1</code>", text)
    # 链接 [text](url)
    text = re.sub(
        r"\[([^\]]+?)\]\(([^)\s]+)\)",
        r'<a href="\2">\1</a>',
        text,
    )
    return text


# ============ HTML 基础样式 ============
_BASE_STYLE = """
<style>
    body {
        font-family: "Microsoft YaHei", "Segoe UI", Arial, sans-serif;
        font-size: 14px;
        line-height: 1.7;
        color: #2c3e50;
        background: #ffffff;
        padding: 8px 12px;
    }
    h1, h2, h3, h4, h5, h6 {
        color: #2563eb;
        margin: 18px 0 8px 0;
        line-height: 1.3;
    }
    h1 { font-size: 22px; border-bottom: 2px solid #e5e7eb; padding-bottom: 6px; }
    h2 { font-size: 19px; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }
    h3 { font-size: 16px; }
    h4 { font-size: 14px; }
    p { margin: 8px 0; }
    ul, ol { margin: 8px 0; padding-left: 24px; }
    li { margin: 4px 0; }
    code {
        font-family: "Consolas", "Courier New", monospace;
        background: #f3f4f6;
        color: #c7254e;
        padding: 2px 5px;
        border-radius: 3px;
        font-size: 13px;
    }
    pre {
        background: #f3f4f6;
        border: 1px solid #e5e7eb;
        border-radius: 6px;
        padding: 12px 14px;
        overflow-x: auto;
        margin: 10px 0;
    }
    pre code {
        background: transparent;
        color: #1f2937;
        padding: 0;
        font-size: 13px;
    }
    table {
        border-collapse: collapse;
        width: 100%;
        margin: 10px 0;
        font-size: 13px;
    }
    th, td {
        border: 1px solid #d1d5db;
        padding: 6px 10px;
        text-align: left;
    }
    th {
        background: #f9fafb;
        color: #1f2937;
        font-weight: bold;
    }
    tr:nth-child(even) td {
        background: #fafbfc;
    }
    a { color: #2563eb; text-decoration: none; }
    a:hover { text-decoration: underline; }
    strong { color: #1f2937; }
</style>
"""


class ManualPage(QWidget):
    """操作手册查看页面。

    在 GUI 内嵌 QTextBrowser 渲染《业务用户操作手册.md》，
    业务用户无需离开程序即可阅读完整使用指南。
    """

    def __init__(self) -> None:
        super().__init__()
        self._manual_path: Path = _resolve_manual_path()
        self._init_ui()
        self._load_manual()

    def _init_ui(self) -> None:
        """初始化 UI 布局。"""
        layout = QVBoxLayout(self)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(12)

        # 标题
        title = QLabel("业务用户操作手册")
        title.setStyleSheet("font-size: 20px; font-weight: bold; color: #2c3e50;")
        layout.addWidget(title)

        # 说明文字
        hint = QLabel("这是完整的使用指南，教你从零开始配置和使用系统。")
        hint.setStyleSheet("color: #7f8c8d; font-size: 13px;")
        hint.setWordWrap(True)
        layout.addWidget(hint)

        # 工具栏
        toolbar = QHBoxLayout()
        toolbar.setSpacing(8)
        self.refresh_btn = QPushButton("🔄 刷新")
        self.refresh_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.refresh_btn.setStyleSheet(self._button_style())
        self.refresh_btn.clicked.connect(self._load_manual)
        toolbar.addWidget(self.refresh_btn)

        self.open_btn = QPushButton("📂 在浏览器中打开")
        self.open_btn.setCursor(Qt.CursorShape.PointingHandCursor)
        self.open_btn.setStyleSheet(self._button_style())
        self.open_btn.clicked.connect(self._open_in_browser)
        toolbar.addWidget(self.open_btn)

        toolbar.addStretch()
        layout.addLayout(toolbar)

        # 文件路径提示（小字）
        self.path_label = QLabel(f"手册路径：{self._manual_path}")
        self.path_label.setStyleSheet("color: #95a5a6; font-size: 12px;")
        self.path_label.setWordWrap(True)
        layout.addWidget(self.path_label)

        # 内容区
        self.browser = QTextBrowser()
        self.browser.setOpenExternalLinks(True)
        self.browser.setStyleSheet(
            "QTextBrowser { "
            "background: #ffffff; "
            "color: #2c3e50; "
            "border: 1px solid #e0e0e0; "
            "border-radius: 6px; "
            "padding: 8px; "
            "font-size: 14px; "
            "}"
        )
        layout.addWidget(self.browser, stretch=1)

    @staticmethod
    def _button_style() -> str:
        """工具栏按钮统一样式。"""
        return (
            "QPushButton { "
            "background: #ffffff; "
            "color: #34495e; "
            "border: 1px solid #d0d0d0; "
            "padding: 6px 14px; "
            "border-radius: 4px; "
            "font-size: 13px; "
            "} "
            "QPushButton:hover { "
            "background: #f5f7fa; "
            "border-color: #3498db; "
            "color: #3498db; "
            "} "
            "QPushButton:pressed { "
            "background: #eaf2fb; "
            "}"
        )

    def _load_manual(self) -> None:
        """读取并渲染手册文件。

        文件不存在时显示友好提示，不抛异常。
        """
        if not self._manual_path.exists():
            self._show_not_found()
            return

        try:
            text = self._manual_path.read_text(encoding="utf-8")
        except Exception as e:
            self.browser.setHtml(
                _BASE_STYLE
                + f"<p>读取手册文件失败：</p>"
                f"<pre><code>{_escape_html(str(e))}</code></pre>"
            )
            return

        html_body = _markdown_to_html(text)
        self.browser.setHtml(_BASE_STYLE + html_body)

    def _show_not_found(self) -> None:
        """手册文件不存在时的友好提示。"""
        html = (
            _BASE_STYLE
            + "<div style='text-align:center; padding:40px 20px;'>"
            "<h2>📋 暂未找到操作手册</h2>"
            "<p>手册文件尚未生成或未随程序一起分发。</p>"
            "<p>请联系管理员获取《业务用户操作手册.md》并放到以下位置：</p>"
            f"<pre><code>{_escape_html(str(self._manual_path))}</code></pre>"
            "</div>"
        )
        self.browser.setHtml(html)

    def _open_in_browser(self) -> None:
        """用系统默认浏览器打开手册 MD 文件。"""
        if not self._manual_path.exists():
            self._show_not_found()
            return

        url = self._manual_path.as_uri()
        try:
            if sys.platform.startswith("win"):
                # Windows 用 start 打开默认关联程序
                os.startfile(str(self._manual_path))  # type: ignore[attr-defined]
            elif sys.platform == "darwin":
                subprocess.run(["open", url], check=False)
            else:
                subprocess.run(["xdg-open", url], check=False)
        except Exception:
            # 兜底：用 webbrowser 模块
            import webbrowser

            webbrowser.open(url)
