"""首次启动向导页：业务用户跟着步骤走，零基础完成部署。

设计思想：
- 把"配置 → 初始化 → 启动服务 → 健康检查"这条线串成一个流程
- 每一步只做一件事，说人话，给操作按钮
- 步骤之间用"上一步/下一步"切换，业务用户不会迷失
- 关键步骤（建表、健康检查）一键执行，后台线程跑，不卡 UI

7 个步骤：
1. 欢迎页：介绍系统能干啥
2. 飞书应用创建指引：图文告诉用户怎么在飞书后台创建应用
3. 填写凭证：跳转到"系统配置"页填 App ID / Secret / 多维表格 Token
4. 一键初始化数据：建业务表 + 采集配置 + 视图 + 权限，一步到位
5. 启动回调服务：把回调服务跑起来，飞书才能推送按钮点击事件
6. 启动公网隧道：Cloudflare Tunnel 把本地服务暴露到公网，飞书才能访问
7. 健康检查：检测所有配置是否就绪，全部 ✓ 就可以正式使用了
"""

from __future__ import annotations

from PySide6.QtCore import Qt, QThread, Signal
from PySide6.QtWidgets import (
    QFrame,
    QHBoxLayout,
    QLabel,
    QListWidget,
    QListWidgetItem,
    QPushButton,
    QStackedWidget,
    QTextBrowser,
    QVBoxLayout,
    QWidget,
)

from src.gui.services.health_check_service import (
    CheckResult,
    run_all_checks,
)
from src.gui.services.init_data_service import InitStepResult, initialize_all_data


# ============ 步骤定义 ============
# 每个步骤：(导航栏显示文字, 详细说明 HTML)
_STEPS: list[tuple[str, str]] = [
    (
        "① 欢迎使用",
        """
        <h2>欢迎使用跨境电商 AI 运营中台</h2>
        <p>这个系统帮你自动干三件事：</p>
        <ul>
            <li><b>自动采集商品</b>：每天早上 9 点抓取亚马逊/沃尔玛/Wayfair 的热卖商品，写入飞书多维表格。</li>
            <li><b>自动库存预警</b>：库存快卖完时自动告警，并触发审批流。</li>
            <li><b>自动审批流</b>：高金额选品/采购自动发飞书审批卡片，主管点按钮就能通过/拒绝，结果回写多维表格。</li>
        </ul>
        <p>跟着向导走完下面 7 步，5 分钟内就能上线使用。完全不用写代码。</p>
        <p style="color:#27ae60;font-weight:bold;">👉 点右下角"下一步"开始</p>
        """,
    ),
    (
        "② 创建飞书应用",
        """
        <h2>第 1 步：在飞书创建企业自建应用</h2>
        <p>系统需要通过飞书应用读写多维表格、发送审批卡片。请按以下步骤操作（一次性工作，做完就不用再管）：</p>
        <ol>
            <li>打开 <a href="https://open.feishu.cn/">飞书开放平台</a>，用<b>企业管理员账号</b>登录。</li>
            <li>点"<b>开发者后台</b>" → "<b>创建企业自建应用</b>"。</li>
            <li>填应用名称（如"AI 运营中台"）和描述，上传一个图标，点创建。</li>
            <li>进入应用后，左侧菜单点"<b>凭证与基础信息</b>"，记下两个关键凭证：
                <ul>
                    <li><b>App ID</b>（应用编号，cli_ 开头）</li>
                    <li><b>App Secret</b>（应用密钥，点"显示"后复制）</li>
                </ul>
                <p style="color:#e67e22;">⚠️ App Secret 是保密的，不要泄露给他人。</p>
            </li>
            <li>左侧菜单点"<b>权限管理</b>"，逐一开通以下权限（操作方法：在页面里的搜索框输入权限名 → 找到后点"<b>开通权限</b>"按钮）：
                <table border="1" cellpadding="6">
                    <tr><th>分类</th><th>权限名（在搜索框输入这个）</th></tr>
                    <tr><td>多维表格</td><td><code>base:app</code>、<code>base:table</code>、<code>base:record</code>、<code>base:collaborator:create</code></td></tr>
                    <tr><td>通讯录</td><td><code>contact:user.id:readonly</code></td></tr>
                    <tr><td>审批</td><td><code>approval:approval</code>、<code>approval:instance:readonly</code></td></tr>
                    <tr><td>消息</td><td><code>im:message</code>、<code>im:chat:readonly</code></td></tr>
                </table>
            </li>
            <li>左侧菜单点"<b>机器人</b>"，启用机器人能力（点"启用机器人"按钮）。</li>
            <li>左侧菜单点"<b>事件与回调</b>"，分两处配置：
                <ul>
                    <li><b>① 事件配置</b>（订阅审批状态变更事件）：
                        <ul>
                            <li>点"事件配置" → "添加事件"</li>
                            <li>搜索并订阅 <code>approval_instance</code>（审批状态变更）</li>
                            <li><b>请求地址先空着</b>，等第 5 步启动公网隧道拿到网址后再回来填</li>
                        </ul>
                    </li>
                    <li><b>② 回调设置 → 卡片回传交互</b>（接收审批卡片按钮点击）：
                        <ul>
                            <li>点"回调设置" → 找到"<b>卡片回传交互</b>"</li>
                            <li>启用它，<b>回调地址同样先空着</b>，等第 5 步拿到公网网址后再填</li>
                        </ul>
                    </li>
                </ul>
                <p style="color:#3498db;">💡 两处填的是<b>同一个网址</b>（公网隧道网址 + <code>/callback</code>），第 5 步会教你复制。</p>
            </li>
            <li>左上角点"<b>创建版本</b>" → 提交审核（企业自建应用通常秒过）。</li>
        </ol>
        <p style="color:#27ae60;font-weight:bold;">👉 完成后点"下一步"</p>
        """,
    ),
    (
        "③ 填写凭证",
        """
        <h2>第 2 步：在系统配置页填入凭证</h2>
        <p>上一步你拿到了 App ID 和 App Secret，现在需要把它们填到系统里。</p>
        <p>操作方法：</p>
        <ol>
            <li>点击下方"<b>打开系统配置页</b>"按钮。</li>
            <li>在配置页填入以下信息（每个字段下方都有灰色小字说明，告诉你从哪获取）：
                <ul>
                    <li><b>App ID</b>（应用编号）：上一步记下的 <code>cli_</code> 开头字符串</li>
                    <li><b>App Secret</b>（应用密钥）：上一步点"显示"后复制的密钥</li>
                    <li><b>企业租户域名</b>：从你的飞书多维表格网址里提取
                        <ul>
                            <li>例如网址是 <code>https://ocndodd7lmyr.feishu.cn/base/xxx</code></li>
                            <li>就填 <code>ocndodd7lmyr</code>（<code>.feishu.cn</code> 前面那一段）</li>
                        </ul>
                    </li>
                    <li><b>多维表格 App Token</b>（表格凭证）：从多维表格网址里提取
                        <ul>
                            <li>例如网址是 <code>.../base/appXXXtokenYYY</code></li>
                            <li>就填 <code>appXXXtokenYYY</code>（<code>/base/</code> 后面那一段）</li>
                        </ul>
                    </li>
                </ul>
            </li>
            <li>点页面底部的"<b>💾 保存配置</b>"按钮。</li>
        </ol>
        <p style="color:#3498db;">💡 <b>审批人 Open ID</b> 字段旁边有个"🔍 搜索"按钮，输入姓名就能搜索飞书用户，自动填入，不用手动复制 <code>ou_</code> 字符串。</p>
        <p style="color:#27ae60;font-weight:bold;">👉 保存成功后回来点"下一步"</p>
        """,
    ),
    (
        "④ 一键初始化数据",
        """
        <h2>第 3 步：一键初始化业务数据</h2>
        <p>系统会在你的飞书多维表格里自动创建：</p>
        <ul>
            <li><b>4 张业务表</b>：选品池 / Listing 库 / 销售日报 / 库存预警</li>
            <li><b>1 张采集配置表</b>：含 15 条默认家具品类配置（5 品类 × 3 平台）</li>
            <li><b>3 个业务视图</b>：销售总览 / 预警看板 / 选品决策（隐藏无关字段）</li>
            <li><b>表格权限</b>：自动设置为"组织内可编辑"</li>
        </ul>
        <p>所有 table_id 会自动写入 .env，不用手动复制。</p>
        <p style="color:#e67e22;">⚠️ 注意：这步会调用飞书 API，请确认上一步凭证已保存。</p>
        <p style="color:#27ae60;font-weight:bold;">👉 点下方"开始初始化"按钮</p>
        """,
    ),
    (
        "⑤ 启动回调服务",
        """
        <h2>第 4 步：启动飞书回调服务</h2>

        <h3>为什么要启动这个服务？（用快递类比）</h3>
        <p>想象飞书是一家快递公司，要给你家送包裹（审批消息）：</p>
        <ul>
            <li>📦 <b>回调服务</b> = 你家门口的<b>快递接收员</b>，负责签收飞书发来的包裹</li>
            <li>🏠 <b>公网隧道</b>（下一步）= 你家的<b>门牌号</b>，让快递员能找到你家</li>
            <li>📍 <b>飞书后台请求地址</b>（下一步）= 你告诉快递公司的<b>收件地址</b></li>
        </ul>
        <p>这一步是<b>安排快递接收员上岗</b>。没有接收员，包裹送到了也没人签收。</p>

        <h3>这个服务会处理什么事？</h3>
        <ul>
            <li><b>首次验证</b>：飞书确认地址有效（会发一个验证码，我们自动返回）</li>
            <li><b>审批卡片按钮点击</b>：用户在飞书点"通过/拒绝"按钮时接收</li>
            <li><b>审批状态变更</b>：主管在飞书审批中心处理完后接收，自动回写多维表格</li>
        </ul>

        <h3>怎么做？</h3>
        <ol>
            <li>点下方"<b>📂 打开任务控制页</b>"按钮。</li>
            <li>在任务控制页找到"<b>服务控制（飞书回调 + 公网隧道）</b>"区块。</li>
            <li>点"<b>▶ 启动回调服务</b>"按钮。</li>
            <li>看到状态变成绿色"<b>● 运行中</b>"即可。</li>
        </ol>

        <p style="color:#3498db;">💡 <b>这个服务不需要你填任何参数</b>，会自动读取上一步保存的配置。</p>
        <p style="color:#e67e22;">⚠️ 这个服务<b>必须一直开着</b>，关掉就收不到飞书消息了（快递员下班了，包裹就送不到）。</p>
        <p style="color:#27ae60;font-weight:bold;">👉 启动后回向导页点"下一步"</p>
        """,
    ),
    (
        "⑥ 启动公网隧道",
        """
        <h2>第 5 步：启动公网隧道 + 填飞书请求地址</h2>

        <h3>为什么要启动公网隧道？（继续用快递类比）</h3>
        <p>上一步安排了快递接收员（回调服务），但飞书快递员还<b>不知道你家在哪</b>。
        公网隧道就是给你家挂一个<b>门牌号</b>，让飞书能找到你电脑。</p>
        <p>启动隧道后会得到一个公网网址（形如 <code>xxx.trycloudflare.com</code>），
        这就是你的"门牌号"。把这个门牌号告诉飞书，飞书才能把消息发过来。</p>

        <h3>怎么做？（分 3 小步）</h3>

        <h4>① 启动公网隧道，拿到"门牌号"</h4>
        <ol>
            <li>在任务控制页"服务控制"区块，点"<b>▶ 启动公网隧道</b>"按钮。</li>
            <li>首次会显示"<b>⏬ 下载中...</b>"（自动下载 cloudflared 约 50MB，无需手动安装），等下载完成。</li>
            <li>等 5-10 秒，看到"<b>✅ 公网网址已就绪</b>"提示。</li>
            <li>点"<b>📋 复制公网网址</b>"按钮，复制网址（这就是你的"门牌号"）。</li>
        </ol>

        <h4>② 拼接完整的"收件地址"</h4>
        <p>飞书要求的地址格式是：<b>公网网址 + /callback</b></p>
        <p>例如你复制的网址是 <code>https://abc-123.trycloudflare.com</code>，<br>
        那么完整的收件地址就是：<code>https://abc-123.trycloudflare.com/callback</code></p>
        <p style="color:#e67e22;">⚠️ <b>一定要加 <code>/callback</code></b>，不加的话飞书找不到接收员。</p>

        <h4>③ 把"收件地址"告诉飞书（两处都要填）</h4>
        <p>回到飞书开放平台 → 你的应用 → 左侧菜单"<b>事件与回调</b>"，有<b>两个地方</b>要填这个地址：</p>
        <table border="1" cellpadding="6">
            <tr>
                <th>位置</th>
                <th>路径</th>
                <th>填什么</th>
            </tr>
            <tr>
                <td><b>① 事件配置</b></td>
                <td>事件与回调 → 事件配置 → 请求地址</td>
                <td><code>公网网址 + /callback</code></td>
            </tr>
            <tr>
                <td><b>② 卡片回传交互</b></td>
                <td>事件与回调 → 回调设置 → 卡片回传交互 → 回调地址</td>
                <td><b>同一个地址</b>（也是 <code>公网网址 + /callback</code>）</td>
            </tr>
        </table>

        <h4>④ 验证地址是否有效</h4>
        <p>两处都点"<b>验证</b>"或"<b>保存</b>"按钮，飞书会自动发一个验证码到你的回调服务，
        本地服务自动返回后验证通过（说明快递员能签收了）。</p>

        <p style="color:#e67e22;">⚠️ <b>临时隧道每次重启网址会变</b>（门牌号换了），需要重新填到飞书后台。生产环境建议用固定隧道。</p>
        <p style="color:#27ae60;font-weight:bold;">👉 验证通过后回向导页点"下一步"</p>
        """,
    ),
    (
        "⑦ 健康检查",
        """
        <h2>第 6 步：健康检查（确认所有配置就绪）</h2>
        <p>系统会自动检测以下 6 项：</p>
        <ul>
            <li>飞书凭证是否有效</li>
            <li>多维表格是否可访问</li>
            <li>5 张业务表是否都已配置</li>
            <li>表格权限是否设置为"组织内可编辑"</li>
            <li>回调服务是否在运行</li>
            <li>公网隧道是否可达</li>
        </ul>
        <p>全绿 ✓ 就说明系统可以正式使用了。</p>
        <p style="color:#27ae60;font-weight:bold;">👉 点下方"开始检查"按钮</p>
        """,
    ),
]


# ============ 后台线程 ============
class _InitDataThread(QThread):
    """后台执行一键初始化数据的线程。"""

    result_ready = Signal(list)

    def run(self) -> None:
        try:
            results = initialize_all_data()
        except Exception:
            results = []
        self.result_ready.emit(results)


class _HealthCheckThread(QThread):
    """后台执行健康检查的线程。"""

    result_ready = Signal(list)

    def run(self) -> None:
        try:
            results = run_all_checks()
        except Exception:
            results = []
        self.result_ready.emit(results)


# ============ 向导页面 ============
class SetupWizardPage(QWidget):
    """首次启动向导页：7 步引导业务用户完成部署。"""

    # 通知主窗口切换页面（参数：目标页标识，如 "config" / "task"）
    _goto_page = Signal(str)

    def __init__(self, parent=None) -> None:
        super().__init__(parent)
        self._init_data_thread: _InitDataThread | None = None
        self._health_check_thread: _HealthCheckThread | None = None
        self._init_ui()

    # ------------------------------------------------------------------
    # UI 初始化
    # ------------------------------------------------------------------
    def _init_ui(self) -> None:
        layout = QHBoxLayout(self)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 左侧步骤导航
        sidebar = self._build_sidebar()
        layout.addWidget(sidebar)

        # 右侧步骤内容
        content = self._build_content()
        layout.addWidget(content, stretch=1)

    def _build_sidebar(self) -> QWidget:
        """构建左侧步骤导航栏。"""
        sidebar = QFrame()
        sidebar.setFixedWidth(200)
        sidebar.setStyleSheet(
            "QFrame { background: #ffffff; border-right: 1px solid #ebeef5; }"
        )
        layout = QVBoxLayout(sidebar)
        layout.setContentsMargins(0, 0, 0, 0)
        layout.setSpacing(0)

        # 标题
        title = QLabel("部署向导")
        title.setAlignment(Qt.AlignmentFlag.AlignCenter)
        title.setStyleSheet(
            "font-size: 16px; font-weight: 700; color: #303133; "
            "padding: 22px 16px; border-bottom: 1px solid #ebeef5;"
        )
        layout.addWidget(title)

        # 步骤列表
        self.step_list = QListWidget()
        self.step_list.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        for step_title, _ in _STEPS:
            self.step_list.addItem(QListWidgetItem(step_title))
        self.step_list.setCurrentRow(0)
        self.step_list.currentRowChanged.connect(self._on_step_changed)
        layout.addWidget(self.step_list, stretch=1)

        return sidebar

    def _build_content(self) -> QWidget:
        """构建右侧内容区：步骤说明 + 操作按钮 + 上一步/下一步。"""
        container = QWidget()
        layout = QVBoxLayout(container)
        layout.setContentsMargins(24, 24, 24, 24)
        layout.setSpacing(16)

        # 内容堆栈：每步一个 QTextBrowser
        self.stack = QStackedWidget()
        self._content_browsers: list[QTextBrowser] = []
        for _, html_body in _STEPS:
            browser = QTextBrowser()
            browser.setOpenExternalLinks(True)
            browser.setHtml(_BASE_STYLE + html_body)
            self._content_browsers.append(browser)
            self.stack.addWidget(browser)
        layout.addWidget(self.stack, stretch=1)

        # 操作区：根据当前步骤显示不同按钮
        self.action_layout = QHBoxLayout()
        self.action_layout.setSpacing(8)
        self._build_action_buttons()
        layout.addLayout(self.action_layout)

        # 底部：上一步 / 下一步
        nav_layout = QHBoxLayout()
        self.prev_btn = QPushButton("← 上一步")
        self.prev_btn.setStyleSheet(self._nav_button_style(secondary=True))
        self.prev_btn.clicked.connect(self._go_prev)
        self.prev_btn.setEnabled(False)
        nav_layout.addWidget(self.prev_btn)

        nav_layout.addStretch()

        self.next_btn = QPushButton("下一步 →")
        self.next_btn.setStyleSheet(self._nav_button_style())
        self.next_btn.clicked.connect(self._go_next)
        nav_layout.addWidget(self.next_btn)

        layout.addLayout(nav_layout)

        return container

    def _build_action_buttons(self) -> None:
        """构建各步骤的操作按钮（步骤 4/5/6/7 才有）。"""
        # 步骤 3：跳转到系统配置页
        self.goto_config_btn = QPushButton("📂 打开系统配置页")
        self.goto_config_btn.setStyleSheet(self._action_button_style())
        # 实际跳转逻辑由 main_window 处理，这里只发信号
        self.goto_config_btn.clicked.connect(lambda: self._goto_page.emit("config"))
        self.goto_config_btn.hide()
        self.action_layout.addWidget(self.goto_config_btn)

        # 步骤 4：一键初始化数据
        self.init_data_btn = QPushButton("🚀 开始初始化")
        self.init_data_btn.setStyleSheet(self._action_button_style(primary=True))
        self.init_data_btn.clicked.connect(self._on_init_data)
        self.init_data_btn.hide()
        self.action_layout.addWidget(self.init_data_btn)

        # 步骤 5/6：跳转到任务控制页
        self.goto_task_btn = QPushButton("📂 打开任务控制页")
        self.goto_task_btn.setStyleSheet(self._action_button_style())
        self.goto_task_btn.clicked.connect(lambda: self._goto_page.emit("task"))
        self.goto_task_btn.hide()
        self.action_layout.addWidget(self.goto_task_btn)

        # 步骤 7：健康检查
        self.health_check_btn = QPushButton("🔍 开始检查")
        self.health_check_btn.setStyleSheet(self._action_button_style(primary=True))
        self.health_check_btn.clicked.connect(self._on_health_check)
        self.health_check_btn.hide()
        self.action_layout.addWidget(self.health_check_btn)

        self.action_layout.addStretch()

        # 状态标签（显示操作结果）
        self.status_label = QLabel("")
        self.status_label.setStyleSheet("font-size: 13px; color: #7f8c8d;")
        self.action_layout.addWidget(self.status_label)

    # ------------------------------------------------------------------
    # 步骤切换
    # ------------------------------------------------------------------
    def _on_step_changed(self, row: int) -> None:
        """切换步骤时更新内容、按钮、上下一步状态。"""
        self.stack.setCurrentIndex(row)
        self._update_action_buttons(row)
        self.prev_btn.setEnabled(row > 0)
        if row == len(_STEPS) - 1:
            self.next_btn.setText("完成 ✓")
        else:
            self.next_btn.setText("下一步 →")
        self.status_label.setText("")

    def _update_action_buttons(self, row: int) -> None:
        """根据当前步骤显示对应的操作按钮。"""
        self.goto_config_btn.setVisible(row == 2)
        self.init_data_btn.setVisible(row == 3)
        self.goto_task_btn.setVisible(row in (4, 5))
        self.health_check_btn.setVisible(row == 6)

    def _go_prev(self) -> None:
        row = self.step_list.currentRow()
        if row > 0:
            self.step_list.setCurrentRow(row - 1)

    def _go_next(self) -> None:
        row = self.step_list.currentRow()
        if row < len(_STEPS) - 1:
            self.step_list.setCurrentRow(row + 1)
        else:
            # 最后一步的"完成"按钮
            self.status_label.setText("🎉 部署完成！可以开始使用了。")
            self.status_label.setStyleSheet(
                "font-size: 14px; color: #27ae60; font-weight: bold;"
            )

    # ------------------------------------------------------------------
    # 一键初始化数据
    # ------------------------------------------------------------------
    def _on_init_data(self) -> None:
        """启动后台线程执行一键初始化。"""
        if self._init_data_thread and self._init_data_thread.isRunning():
            return

        self.init_data_btn.setEnabled(False)
        self.init_data_btn.setText("🚀 初始化中...")
        self.status_label.setText("正在初始化，请稍候（约 10-30 秒）...")
        self.status_label.setStyleSheet("font-size: 13px; color: #3498db;")

        self._init_data_thread = _InitDataThread()
        self._init_data_thread.result_ready.connect(self._on_init_data_done)
        self._init_data_thread.start()

    def _on_init_data_done(self, results: list) -> None:
        """初始化完成：显示结果，恢复按钮。"""
        self.init_data_btn.setEnabled(True)
        self.init_data_btn.setText("🚀 开始初始化")

        if not results:
            self.status_label.setText("❌ 初始化失败，请查看日志")
            self.status_label.setStyleSheet("font-size: 13px; color: #e74c3c;")
            return

        success_count = sum(1 for r in results if r.success)
        total = len(results)
        details = "\n".join(str(r) for r in results)

        if success_count == total:
            self.status_label.setText(f"✅ 全部完成：{success_count}/{total} 步成功")
            self.status_label.setStyleSheet(
                "font-size: 13px; color: #27ae60; font-weight: bold;"
            )
        else:
            self.status_label.setText(
                f"⚠️ 部分成功：{success_count}/{total}，详情看技术日志"
            )
            self.status_label.setStyleSheet(
                "font-size: 13px; color: #e67e22; font-weight: bold;"
            )

        # 在当前页面追加详细结果
        browser = self._content_browsers[3]
        browser.setHtml(_BASE_STYLE + _STEPS[3][1] + _format_init_results(results))

    # ------------------------------------------------------------------
    # 健康检查
    # ------------------------------------------------------------------
    def _on_health_check(self) -> None:
        """启动后台线程执行健康检查。"""
        if self._health_check_thread and self._health_check_thread.isRunning():
            return

        self.health_check_btn.setEnabled(False)
        self.health_check_btn.setText("🔍 检查中...")
        self.status_label.setText("正在检查，请稍候...")
        self.status_label.setStyleSheet("font-size: 13px; color: #3498db;")

        self._health_check_thread = _HealthCheckThread()
        self._health_check_thread.result_ready.connect(self._on_health_check_done)
        self._health_check_thread.start()

    def _on_health_check_done(self, results: list) -> None:
        """检查完成：在页面里追加结果。"""
        self.health_check_btn.setEnabled(True)
        self.health_check_btn.setText("🔍 开始检查")

        if not results:
            self.status_label.setText("❌ 检查失败")
            self.status_label.setStyleSheet("font-size: 13px; color: #e74c3c;")
            return

        success_count = sum(1 for r in results if r.success)
        total = len(results)

        if success_count == total:
            self.status_label.setText(f"🎉 全部通过：{success_count}/{total}")
            self.status_label.setStyleSheet(
                "font-size: 14px; color: #27ae60; font-weight: bold;"
            )
        else:
            self.status_label.setText(
                f"⚠️ 有 {total - success_count} 项未通过，请按提示修复"
            )
            self.status_label.setStyleSheet(
                "font-size: 13px; color: #e67e22; font-weight: bold;"
            )

        browser = self._content_browsers[6]
        browser.setHtml(_BASE_STYLE + _STEPS[6][1] + _format_check_results(results))

    # ------------------------------------------------------------------
    # 样式
    # ------------------------------------------------------------------
    @staticmethod
    def _nav_button_style(secondary: bool = False) -> str:
        """上一步/下一步按钮样式。"""
        if secondary:
            return (
                "QPushButton { background: #f5f7fa; color: #606266; "
                "border: 1px solid #dcdfe6; padding: 8px 20px; "
                "border-radius: 6px; font-size: 14px; }"
                "QPushButton:hover { background: #ecf5ff; border-color: #c6e2ff; }"
                "QPushButton:disabled { background: #fafafa; color: #c0c4cc; }"
            )
        return (
            "QPushButton { background: #3498db; color: white; border: none; "
            "padding: 8px 24px; border-radius: 6px; font-size: 14px; font-weight: bold; }"
            "QPushButton:hover { background: #2980b9; }"
            "QPushButton:disabled { background: #c0c4cc; }"
        )

    @staticmethod
    def _action_button_style(primary: bool = False) -> str:
        """操作按钮样式。"""
        if primary:
            return (
                "QPushButton { background: #27ae60; color: white; border: none; "
                "padding: 10px 24px; border-radius: 6px; "
                "font-size: 14px; font-weight: bold; }"
                "QPushButton:hover { background: #229954; }"
                "QPushButton:disabled { background: #bdc3c7; }"
            )
        return (
            "QPushButton { background: #ffffff; color: #3498db; "
            "border: 1px solid #3498db; padding: 10px 20px; "
            "border-radius: 6px; font-size: 14px; }"
            "QPushButton:hover { background: #ecf5ff; }"
        )


# ============ 辅助函数 ============
def _format_init_results(results: list) -> str:
    """把初始化结果格式化成 HTML。"""
    if not results:
        return "<p style='color:#e74c3c;'>初始化失败，无返回结果</p>"

    rows = []
    for r in results:
        assert isinstance(r, InitStepResult)
        icon = "✅" if r.success else "❌"
        color = "#27ae60" if r.success else "#e74c3c"
        rows.append(
            f"<tr><td>{icon}</td><td><b>{r.name}</b></td>"
            f"<td style='color:{color};'>{r.message}</td></tr>"
        )

    return (
        "<h3>初始化结果</h3>"
        "<table><tr><th>状态</th><th>步骤</th><th>详情</th></tr>"
        + "".join(rows)
        + "</table>"
    )


def _format_check_results(results: list) -> str:
    """把健康检查结果格式化成 HTML。"""
    if not results:
        return "<p style='color:#e74c3c;'>检查失败，无返回结果</p>"

    rows = []
    for r in results:
        assert isinstance(r, CheckResult)
        icon = "✅" if r.success else "❌"
        color = "#27ae60" if r.success else "#e74c3c"
        detail = r.detail or ""
        rows.append(
            f"<tr><td>{icon}</td><td><b>{r.name}</b></td>"
            f"<td style='color:{color};'>{r.message}</td>"
            f"<td><code>{detail}</code></td></tr>"
        )

    return (
        "<h3>检查结果</h3>"
        "<table><tr><th>状态</th><th>检查项</th><th>结果</th><th>详情</th></tr>"
        + "".join(rows)
        + "</table>"
    )


# ============ HTML 基础样式（与 manual_page 保持一致）============
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
    h2 { font-size: 19px; border-bottom: 1px solid #e5e7eb; padding-bottom: 4px; }
    h3 { font-size: 16px; }
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
        vertical-align: top;
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
