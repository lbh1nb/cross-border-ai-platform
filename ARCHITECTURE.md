# 项目架构文档

> 跨境电商 AI 运营中台 - 多平台多品类选品采集 + 增量同步 + 自动清理系统

## 一、整体架构

```mermaid
flowchart TB
    subgraph 配置层
        A1[飞书采集配置表<br/>5品类×3平台=15条配置]
        A2[field_mapping.py<br/>字段名+主键集中配置]
    end

    subgraph 调度层
        B1[APScheduler<br/>4个定时任务]
        B2[选品采集<br/>工作日9:00]
        B3[库存检查<br/>每30分钟]
        B4[数据清理<br/>每3天2:00]
        B1 --> B2
        B1 --> B3
        B1 --> B4
    end

    subgraph 采集层
        C1[MockMultiPlatformCollector<br/>多平台模拟采集器]
        C2[亚马逊采集]
        C3[沃尔玛采集]
        C4[Wayfair采集]
        C1 --> C2
        C1 --> C3
        C1 --> C4
    end

    subgraph 处理层
        D1[DataCleaner<br/>过滤低评分/离谱价]
        D2[SyncService<br/>增量同步: 查询现有→分类→批量新增/逐条更新]
    end

    subgraph 存储层
        E1[飞书多维表格<br/>5张业务表+3个业务视图]
        E2[SQLite<br/>调度器任务持久化]
    end

    A1 -->|读取启用配置| B2
    A2 -->|字段映射| D2
    B2 -->|循环15条配置| C1
    C2 --> D1
    C3 --> D1
    C4 --> D1
    D1 --> D2
    D2 -->|增量写入| E1
    B3 -->|更新预警等级| E1
    B4 -->|删除旧数据| E1
    B1 -.->|持久化任务| E2

    style A1 fill:#2d5a3d,color:#fff
    style A2 fill:#2d5a3d,color:#fff
    style B1 fill:#4a3d2d,color:#fff
    style C1 fill:#2d4a5a,color:#fff
    style D1 fill:#5a2d4a,color:#fff
    style D2 fill:#5a3d2d,color:#fff
    style E1 fill:#2d3a5a,color:#fff
```

## 二、核心模块说明

### 2.1 配置层（src/config.py + 飞书采集配置表）

**配置中心**：从 `.env` 读取飞书凭证、表 ID、业务参数。

**采集配置表**（飞书多维表格）：
- 字段：品类（文本）/ 平台（单选）/ 采集数量（数字）/ 优先级（数字）/ 启用状态（单选）/ 备注 / 更新时间
- 设计要点：品类字段使用文本类型而非单选，企业可自由填写经营范围（家具企业填"户外家具"，3C企业填"蓝牙耳机"），无需改代码

### 2.2 采集层（src/pipeline/collectors/）

**策略模式**：所有采集器实现 `BaseCollector` 接口，上层代码不关心数据源。

```mermaid
classDiagram
    class BaseCollector {
        <<abstract>>
        +collect(category, limit, platform) list~ProductInfo~
        +close()
    }
    class MockAmazonCollector {
        -_rng
        +collect(category, limit, platform) list~ProductInfo~
    }
    class MockMultiPlatformCollector {
        -_rng
        +collect(category, limit, platform) list~ProductInfo~
    }
    class RealAmazonCollector {
        +collect() *
    }

    BaseCollector <|-- MockAmazonCollector
    BaseCollector <|-- MockMultiPlatformCollector
    BaseCollector <|-- RealAmazonCollector
```

**多平台差异化设计**：

| 平台 | URL 格式 | ID 格式 | 价格系数 | 评论系数 | BSR |
|------|----------|---------|----------|----------|------|
| 亚马逊 | amazon.com/dp/{asin} | B0+8位 | 1.0 | 1.0 | 有 |
| 沃尔玛 | walmart.com/ip/{id} | 8-12位数字 | 0.85 | 0.6 | 无 |
| Wayfair | wayfair.com/.../pdp/{id} | 字母+数字 | 1.25 | 0.3 | 无 |

**品类开放设计**：
- 默认 5 个家具品类：家居收纳、厨房用品、户外家具、办公家具、卧室家具
- 未知品类自动回退到默认模板，保证企业自定义品类也能采集到合理数据

### 2.3 处理层（src/pipeline/ + src/feishu/sync_service.py）

**清洗器**（DataCleaner）：
- 过滤评分 < 3.8 的商品
- 过滤价格 < 10 美金 或 > 500 美金的商品
- 过滤 BSR 排名 > 30000 的商品

**同步服务**（SyncService）—— 增量同步核心：

```mermaid
flowchart LR
    A[输入: 新数据列表] --> B[查询飞书现有记录]
    B --> C[构建主键索引<br/>primary_value -> record_id]
    C --> D{遍历每条新数据}
    D -->|主键已存在| E[分类: 更新队列]
    D -->|主键不存在| F[分类: 新增队列]
    E --> G[逐条 update_record]
    F --> H[批量 batch_add_records]
    G --> I[统计 SyncResult]
    H --> I
    I --> J[返回: 新增/更新/跳过/失败]

    style A fill:#2d5a3d,color:#fff
    style C fill:#2d4a5a,color:#fff
    style E fill:#5a2d4a,color:#fff
    style F fill:#5a3d2d,color:#fff
    style I fill:#2d3a5a,color:#fff
```

**主键配置**（field_mapping.py 集中管理）：
| 表 | 主键 | 用途 |
|----|------|------|
| 选品池 | ASIN + 来源平台 | 同一商品在同一平台不重复 |
| 库存预警 | SKU | 同一 SKU 不重复 |
| 销售日报 | 日期 + 平台 | 同一天同平台只有一条日报 |

**字段映射**（field_mapping.py）：
- 集中管理所有表的字段名配置，避免硬编码散落
- 提供 `product_to_record()` 转换函数
- 提供 `extract_primary_values()` 主键提取函数（兼容多行文本/单选/数字/超链接等格式）

### 2.4 调度层（src/scheduler/）

```mermaid
sequenceDiagram
    participant S as SchedulerManager
    participant T as tasks.py
    participant C as 多平台采集器
    participant Sync as SyncService
    participant F as 飞书API

    S->>T: 工作日9:00 触发 product_collection_task
    T->>F: 读取"采集配置"表所有启用记录
    F-->>T: 返回15条配置
    loop 每条配置
        T->>C: collect(品类, 数量, 平台)
        C-->>T: 返回5个商品
        T->>T: 清洗过滤
        T->>Sync: sync_products(商品列表)
        Sync->>F: 查询现有记录构建主键索引
        F-->>Sync: 返回现有记录
        Sync->>Sync: 分类: 新增 vs 更新
        alt 新增
            Sync->>F: batch_add_records
        else 更新
            Sync->>F: update_record (逐条)
        end
        F-->>Sync: 返回结果
        Sync-->>T: 返回 SyncResult
    end
    T-->>S: 返回总新增+更新数
```

**任务列表**：
| 任务 ID | 触发时间 | 功能 |
|---------|----------|------|
| product_collection | 工作日 9:00 | 多平台多品类增量同步采集 |
| inventory_check | 每 30 分钟 | 库存预警等级更新 |
| daily_report | 每天 18:00 | 日报生成（预留） |
| data_cleanup | 每 3 天 2:00 | 删除旧数据防止堆积 |

**数据清理任务**（cleanup_task.py）：

```mermaid
flowchart TB
    A[每3天凌晨2:00触发] --> B[读取 DATA_RETENTION_DAYS 配置]
    B --> C{遍历 3 张业务表}
    C --> D[选品池: 按'分析时间'判断]
    C --> E[库存预警: 按'更新时间'判断]
    C --> F[销售日报: 按'日期'判断]
    D --> G[查询全部记录]
    E --> G
    F --> G
    G --> H{时间戳 < cutoff?}
    H -->|是| I[加入删除队列]
    H -->|否| J[保留]
    I --> K[batch_delete_records 批量删除]
    K --> L[返回清理统计]

    style A fill:#4a3d2d,color:#fff
    style B fill:#2d4a5a,color:#fff
    style K fill:#5a2d4a,color:#fff
    style L fill:#2d3a5a,color:#fff
```

**清理策略**：
- 保留最近 3 天数据（可通过 `DATA_RETENTION_DAYS` 环境变量配置）
- 没有时间字段的记录保留（安全策略，不删未知数据）
- 飞书 API 单次最多删除 500 条，自动分批
- **不清理**：采集配置表（企业长期配置）/ Listing 库表（保留优化历史）

### 2.5 飞书中台（src/feishu/）

**BitableClient** 提供完整的飞书多维表格 API 封装：
- 表管理：create_table / list_tables / list_fields / add_field
- 记录管理：add_record / batch_add_records / query_records / update_record / delete_record / batch_delete_records
- 视图管理：list_views / create_view / patch_view（含字段隐藏配置）
- 错误处理：3 次重试 + 指数退避

**业务视图**（通过 scripts/init_views.py 创建）：

| 视图名 | 所属表 | 显示字段 |
|--------|--------|----------|
| 销售总览 | 销售日报 | 日期/平台/销售额/订单数/ACoS/异常标记/AI洞察 |
| 预警看板 | 库存预警 | ASIN/商品名称/SKU/平台/可售天数/预警等级/建议采购量/预估采购金额/审批状态 |
| 选品决策 | 选品池 | 商品名称/ASIN/品类/来源平台/价格区间/评分/评论数/市场容量/竞争强度/利润空间/推荐指数/状态 |

**表结构**（5 张表）：
1. **选品池**：商品名/ASIN/品类/来源平台/价格/评分/评论数/BSR/市场容量/竞争强度/利润空间
2. **Listing 库**：商品 Listing 优化记录
3. **销售日报**：每日销售数据 + AI 洞察
4. **库存预警**：库存监控与自动审批
5. **采集配置**：企业经营品类与采集平台配置

**Webhook 机器人**（feishu_bot.py）：

```mermaid
flowchart LR
    A[业务事件触发] --> B{事件类型}
    B -->|库存紧急| C[build_inventory_alert_card]
    B -->|选品完成| D[build_selection_report_card]
    B -->|日报生成| E[build_daily_report_card]
    B -->|金额超阈值| F[build_approval_card]
    C --> G[FeishuBot.send_card]
    D --> G
    E --> G
    F --> G
    G --> H[POST Webhook URL]
    H --> I{飞书返回}
    I -->|code=0| J[发送成功]
    I -->|code!=0| K[记录错误日志]
    I -->|HTTP异常| K

    style A fill:#2d5a3d,color:#fff
    style F fill:#5a2d2d,color:#fff
    style G fill:#2d4a5a,color:#fff
    style J fill:#2d3a5a,color:#fff
```

**FeishuBot 类**提供三种消息发送方法：
- `send_text(text)`：纯文本消息，最简通知
- `send_rich_text(title, content)`：富文本消息，支持加粗/链接
- `send_card(card)`：交互卡片，支持按钮和分栏

**卡片模板库**（card_templates.py）—— 4 类业务卡片：

| 卡片模板 | 用途 | 标题颜色 | 按钮行为 |
|----------|------|----------|----------|
| `build_inventory_alert_card()` | 库存预警通知 | red/orange/yellow/green | url 跳转多维表格 |
| `build_selection_report_card()` | 选品采集日报 | blue | url 跳转选品池表 |
| `build_daily_report_card()` | 销售日报 | green/orange | url 跳转销售日报表 |
| `build_approval_card()` | 审批通知 | orange | value 触发回调（通过/拒绝） |

**链接跳转优化**（build_table_url）：
- 使用企业租户域名（如 `ocndodd7lmyr.feishu.cn`）生成链接
- 飞书桌面端拦截本企业租户域名，直接在飞书内打开多维表格
- 避免跳转浏览器需重新登录的体验问题

**告警触发策略**：
- 仅"紧急"和"预警"等级触发机器人告警（避免告警疲劳）
- 等级未变化时不重复告警
- 机器人未配置时静默跳过，不影响表格更新

**卡片按钮回调服务**（card_callback.py，08-05 新增）：

```mermaid
sequenceDiagram
    participant User as 飞书用户
    participant Feishu as 飞书服务器
    participant Ngrok as ngrok 公网隧道
    participant Local as 本地 FastAPI 服务
    participant Handler as 业务处理器

    User->>Feishu: 点击卡片按钮
    Feishu->>Ngrok: POST /callback (card.action.trigger)
    Ngrok->>Local: 转发到本地 8000 端口
    Local->>Local: 1. URL 验证? 返回 challenge
    Local->>Local: 2. 卡片回调? 路由到 handler
    Local->>Handler: 调用 _handle_approve / _handle_reject
    Handler-->>Local: 返回处理结果
    Local-->>Ngrok: JSON 响应（3秒内）
    Ngrok-->>Feishu: 转发响应
    Feishu-->>User: 显示处理结果
```

**FastAPI 回调服务架构**：
- 端点：`POST /callback`（接收飞书回调）
- 端点：`GET /health`（健康检查，用于监控）
- 端点：`GET /`（服务说明）
- 支持 URL 验证（飞书首次配置回调 URL 时发送 challenge）
- 支持 `card.action.trigger` 事件（卡片按钮点击）
- 支持 `approval_instance` 事件（飞书审批流状态变更，08-06 新增）
- **兼容两种回调格式**：老格式（schema 1.0，顶层 `type` 字段）和新格式（schema 2.0，`header.event_type` 字段）
- 内置 2 个 action 处理器：`approve`（审批通过）/ `reject`（审批拒绝）
- 内置审批状态变更处理器（08-06 新增）：异步回写多维表格"审批状态"字段，失败时通过应用机器人发告警消息到飞书群

**多审批流规则引擎**（approval_rules_service.py + approval_task.py）：

```mermaid
sequenceDiagram
    participant Task as 业务任务<br/>(选品采集/库存预警)
    participant Rules as 规则引擎<br/>(approval_rules_service)
    participant JSON as rules.json
    participant Approval as 飞书审批API
    participant Mgr as 主管
    participant Callback as 回调服务
    participant Bitable as 多维表格

    Task->>Rules: trigger_approval_for_records(event, records)
    Rules->>JSON: 加载所有规则
    Rules->>Rules: 逐条匹配: 事件类型 + 条件(字段+操作符+阈值)
    loop 命中规则
        Rules->>Approval: create_approval_instance(规则配置)
        Approval-->>Rules: 返回 instance_code
        Rules->>Bitable: 更新审批状态为"审批中"
    end
    Mgr->>Approval: 在飞书审批中心通过/拒绝
    Approval->>Callback: 推送 approval_instance 事件
    Callback->>Approval: 查询审批实例详情(提取ASIN)
    Callback->>Bitable: 异步回写"审批状态"字段
```

**触发方式**：
- **事件驱动**（主）：业务任务跑完后立即调用规则引擎，对本次记录匹配规则
- **每小时兜底**（辅）：补触发事件驱动遗漏的记录（手动新增的、规则新增后的历史记录）

**规则存储**：JSON 文件 `data/approval_rules.json`，每个规则独立配置：
- 审批定义（approval_code + 字段 ID + 节点 ID + 审批人）
- 触发事件（选品采集完成 / 库存预警触发）
- 触发条件（字段 + 操作符 + 阈值，如 `利润空间 > 5000`）

**审批流模块**：
- `src/feishu/approval.py` — 飞书审批流 API 客户端（支持动态传入 approval_code/node_id/字段ID）
- `src/scheduler/approval_task.py` — 事件驱动触发入口 + 每小时兜底扫描
- `src/gui/services/approval_rules_service.py` — 多审批流规则引擎（CRUD + 条件匹配 + 事件触发）
- `scripts/query_approval_definition.py` — 查询审批定义表单结构工具

**部署要求**：
- 飞书服务器需要公网可访问的 HTTPS 地址
- 本地开发用 ngrok 内网穿透（`scripts/start_ngrok.py`）
- 生产环境部署到云服务器（第4周 Docker 化）

### 2.6 桌面 GUI 层（src/gui/）

**PySide6 桌面应用**，业务用户无需接触代码即可完成所有操作。采用现代简约白底风格：卡片化布局、圆角阴影、蓝色主题、清晰视觉层次。

```mermaid
flowchart TB
    subgraph 主窗口[主窗口 - 现代简约白底]
        A[MainWindow<br/>白底侧边栏 + QStackedWidget]
    end

    subgraph 四大页面
        B[ConfigPage<br/>配置面板 + 字段说明]
        C[ApprovalPage<br/>向导式新建规则]
        D[TaskPage<br/>双选项卡日志]
        E[DashboardPage<br/>数据看板]
    end

    subgraph 服务层
        F[EnvService<br/>.env 读写]
        G[ApprovalService<br/>审批定义扫描]
        H[SchedulerThread<br/>BackgroundScheduler]
        I[ApprovalRulesService<br/>规则引擎 + JSON 存储]
        J[BitableClient<br/>飞书表格读取]
    end

    A --> B
    A --> C
    A --> D
    A --> E
    B --> F
    C --> G
    C --> I
    D --> H
    E --> J

    style A fill:#2d5a3d,color:#fff
    style C fill:#5a3d2d,color:#fff
    style F fill:#2d3a5a,color:#fff
    style G fill:#2d3a5a,color:#fff
    style I fill:#5a2d4a,color:#fff
```

**GUI 模块结构**：
- `src/gui/main.py` — GUI 入口（QApplication + 全局样式：现代简约白底）
- `src/gui/main_window.py` — 主窗口（白底侧边栏 + 7 页面切换）
- `src/gui/pages/setup_wizard_page.py` — 部署向导（7 步引导业务用户完成部署，v0.4.0 新增）
- `src/gui/pages/config_page.py` — 配置面板（每字段带说明和获取指引 → .env）
- `src/gui/pages/approval_page.py` — 审批流管理（向导式新建规则 + 规则列表 CRUD + 扫描原理说明）
- `src/gui/pages/task_page.py` — 任务控制（双选项卡日志 + BackgroundScheduler + 回调服务 + 公网隧道 + HTML 指引卡片）
- `src/gui/pages/dashboard_page.py` — 数据看板（选品池 + 库存预警表格）
- `src/gui/pages/health_check_page.py` — 健康检查页（6 项配置就绪检测，v0.4.0 新增）
- `src/gui/pages/manual_page.py` — 操作手册页（内置业务用户操作手册，v0.4.0 新增）
- `src/gui/services/env_service.py` — .env 配置读写服务
- `src/gui/services/approval_service.py` — 审批定义扫描/查询服务
- `src/gui/services/approval_rules_service.py` — 多审批流规则引擎（JSON 存储 + 事件触发）
- `src/gui/services/callback_server_thread.py` — 飞书回调服务线程封装（FastAPI + uvicorn，v0.4.0 新增）
- `src/gui/services/cloudflare_tunnel_thread.py` — Cloudflare 公网隧道线程封装（自动下载 cloudflared，v0.4.0 新增）
- `src/gui/services/cloudflared_downloader.py` — cloudflared 二进制下载器（v0.4.0 新增）
- `src/gui/services/health_check_service.py` — 健康检查服务（6 项检测，v0.4.0 新增）
- `src/gui/services/init_data_service.py` — 一键初始化数据服务（建表 + 采集配置 + 视图 + 权限，v0.4.0 新增）
- `src/gui/services/approver_search_service.py` — 审批人搜索服务（按姓名查 open_id，v0.4.0 新增）
- `src/gui/services/chat_search_service.py` — 群聊搜索服务（按名称查 chat_id，v0.4.0 新增）
- `src/gui/widgets/approver_search_dialog.py` — 审批人搜索对话框组件（v0.4.0 新增）
- `src/gui/widgets/chat_search_dialog.py` — 群聊搜索对话框组件（v0.4.0 新增）

**审批流规则向导式创建**：

```mermaid
sequenceDiagram
    participant User as 业务用户
    participant Dialog as 新建规则对话框
    participant ScanThread as 自动扫描线程
    participant Feishu as 飞书 API
    participant Rules as 规则引擎(JSON)

    User->>Dialog: 点"➕ 新建审批规则"
    Dialog->>ScanThread: 启动自动扫描
    ScanThread->>Feishu: POST /approvals（列出所有审批定义）
    Feishu-->>ScanThread: 返回审批定义列表
    ScanThread-->>Dialog: 自动填充下拉框

    User->>Dialog: 选审批定义 + 选触发事件 + 配条件(字段+操作符+阈值)
    Dialog->>Feishu: GET /approvals/{code}（查字段 ID 和节点 ID）
    Feishu-->>Dialog: 返回字段 ID + 节点 ID + 审批人

    User->>Dialog: 点"保存"
    Dialog->>Rules: add_rule(rule_dict)
    Rules->>Rules: 写入 data/approval_rules.json
    Rules-->>Dialog: 返回 rule_id
    Dialog-->>User: 显示"规则已保存"
```

**双选项卡日志系统**：

```mermaid
flowchart LR
    A[业务任务执行] --> B[logger 输出日志]
    B --> C[写入 logs/app.log]
    C --> D[QTimer 每秒读取]
    D --> E{选项卡路由}
    E -->|业务日志 tab| F[关键词过滤<br/>只保留: 采集了X个/触发X条/预警X条]
    E -->|技术日志 tab| G[完整日志<br/>含 DEBUG/INFO/WARNING/ERROR]

    style A fill:#2d5a3d,color:#fff
    style F fill:#2d3a5a,color:#fff
    style G fill:#5a2d2d,color:#fff
```

**多线程设计**：
- 所有飞书 API 调用都在 QThread 后台执行，避免阻塞 UI
- 调度器用 `BackgroundScheduler`（start() 立即返回）封装在 `SchedulerThread` 中，GUI 主线程保持响应
- 日志刷新用 QTimer 每秒读取日志文件
- 业务日志通过关键词过滤技术噪音，仅保留"采集了X个商品""触发X条审批"等大白话消息

### 2.7 AI 调度层 + 选品 Agent（src/ai/，v0.5.0 新增）

**AI 调度层**为 Agent 提供模型路由、Prompt 管理和工具注册三大基础能力，业务代码只关心"做什么任务"，不关心"用哪个模型"。

```mermaid
flowchart TB
    subgraph 调度层[AI 调度层]
        R[ModelRouter<br/>多模型路由]
        P[PromptManager<br/>Prompt 模板]
        T[ToolRegistry<br/>工具注册中心]
    end

    subgraph 选品Agent[选品分析 Agent - ReAct 模式]
        A1[create_agent<br/>LangChain v1.0]
        A2[fetch_products<br/>抓取商品]
        A3[analyze_products<br/>LLM 分析]
        A4[save_report<br/>保存+推送]
    end

    subgraph 外部依赖
        LLM[LLM 服务<br/>Anthropic/OpenAI]
        FS[飞书多维表格<br/>+ 应用机器人]
        COL[MockAmazonCollector<br/>商品采集]
    end

    R --> LLM
    A1 --> R
    A1 --> A2
    A1 --> A3
    A1 --> A4
    A2 --> COL
    A3 --> R
    A3 --> P
    A4 --> FS

    style R fill:#2d5a3d,color:#fff
    style P fill:#2d4a5a,color:#fff
    style T fill:#5a2d4a,color:#fff
    style A1 fill:#5a3d2d,color:#fff
    style LLM fill:#2d3a5a,color:#fff
```

**ModelRouter 多模型路由**（`src/ai/model_router.py`）：
- 按任务复杂度自动选择模型：simple（便宜）/ standard（中等）/ complex（强模型）
- 优先 Anthropic（Claude），凭证缺失时回退 OpenAI
- 创建 LLM 时自动挂载 `llm_monitor` 回调（可观测性）

| 任务类型 | Anthropic 模型 | OpenAI 模型 | 适用场景 |
|----------|----------------|-------------|----------|
| simple | claude-haiku-4-5 | gpt-4o-mini | 分类、提取、摘要 |
| standard | claude-sonnet-4-6 | gpt-4o | 分析、生成、翻译 |
| complex | claude-opus-4-8 | gpt-4o | 多步推理、Agent 决策 |

**PromptManager 模板管理**（`src/ai/prompt_manager.py`）：
- 集中管理选品 Agent 的 3 个 Prompt：selection_system / selection_analysis / selection_report
- 基于 LangChain ChatPromptTemplate，支持变量渲染
- 模板硬编码在模块中（v0.6.0 计划支持从文件加载）

**选品 Agent 工作流**（`src/ai/agents/selection_agent.py`）：

```mermaid
sequenceDiagram
    participant User as 业务用户
    participant GUI as AI Agent 页面
    participant Worker as 后台线程
    participant Agent as create_agent
    participant Tools as 3 个工具
    participant LLM as LLM 服务
    participant FS as 飞书

    User->>GUI: 选品类 + 点"运行 Agent"
    GUI->>Worker: 启动后台线程（避免阻塞 UI）
    Worker->>Agent: invoke(用户消息)
    Agent->>LLM: 决策调用哪个工具
    LLM-->>Agent: 调用 fetch_products
    Agent->>Tools: fetch_products(品类, 10)
    Tools->>Tools: MockAmazonCollector 采集
    Tools-->>Agent: 返回商品 JSON
    Agent->>LLM: 决策下一步
    LLM-->>Agent: 调用 analyze_products
    Agent->>Tools: analyze_products(品类, 商品JSON)
    Tools->>LLM: 用 selection_analysis Prompt 分析
    LLM-->>Tools: 返回结构化分析结果
    Tools-->>Agent: 返回分析 JSON
    Agent->>LLM: 决策下一步
    LLM-->>Agent: 调用 save_report
    Agent->>Tools: save_report(分析JSON)
    Tools->>FS: 写入多维表格 + 推送飞书群
    Tools-->>Agent: 返回保存结果
    Agent-->>Worker: 返回最终总结
    Worker-->>GUI: 显示结果 + 日志
```

**GUI 入口**（`src/gui/pages/ai_agent_page.py`）：
- 品类下拉框（5 个默认品类，可自定义）+ 运行按钮
- 后台线程执行 Agent（避免 30-60 秒的 LLM 调用阻塞 UI）
- 实时日志显示（黑色背景，终端风格）
- 结果表格（自动解析 Agent 输出中的 top_picks）
- API Key 状态提示（未配置时橙色警告）

### 2.8 可观测性模块（src/observability/，v0.5.0 新增）

**LLM 调用监控闭环**：自动记录每次 LLM 调用的耗时、Token、成本，失败率超阈值时飞书告警。

```mermaid
flowchart LR
    A[LLM.invoke 触发] --> B[on_llm_start<br/>记录开始时间+模型名+输入]
    B --> C[LLM 执行]
    C --> D{执行结果}
    D -->|成功| E[on_llm_end<br/>提取 token+计算成本]
    D -->|失败| F[on_llm_error<br/>记录错误]
    E --> G[metrics_store<br/>写入 SQLite]
    F --> G
    F --> H[alert_checker<br/>检查失败率]
    H --> I{失败率 > 10%<br/>且总数 >= 10?}
    I -->|是| J[发送飞书告警<br/>30 分钟冷却]
    I -->|否| K[静默]
    G --> L[统计查询<br/>成功率/耗时/成本]

    style A fill:#2d5a3d,color:#fff
    style E fill:#2d4a5a,color:#fff
    style F fill:#5a2d2d,color:#fff
    style G fill:#2d3a5a,color:#fff
    style J fill:#5a3d2d,color:#fff
```

**三大组件**：

| 组件 | 文件 | 职责 |
|------|------|------|
| LLMCallMonitor | llm_monitor.py | LangChain Callback，自动拦截 LLM 调用 |
| MetricsStore | metrics_store.py | SQLite 持久化调用日志，支持统计查询 |
| AlertChecker | alert.py | 失败率 >10% 触发飞书告警，30 分钟冷却 |

**LLMCallMonitor 工作原理**：
- 继承 LangChain `BaseCallbackHandler`
- 在 `ModelRouter._create_anthropic_llm` / `_create_openai_llm` 中通过 `callbacks=[llm_monitor]` 挂载
- 业务代码零侵入，所有 LLM 调用自动被监控

**MetricsStore SQLite 表结构**：
- 数据库位置：`data/llm_metrics.db`（开发模式）/ exe 同目录（打包模式）
- 字段：call_id / model_name / input_summary / output_summary / duration_ms / input_tokens / output_tokens / cost_usd / success / error_message / created_at
- 查询接口：`get_stats(hours)` 返回成功率/失败率/平均耗时/总成本；`get_recent_calls(limit)` 返回最近记录
- 自动清理：`cleanup(days=30)` 删除超过 30 天的旧记录

**AlertChecker 告警阈值**：
- 触发条件（全部满足）：近 1 小时调用数 >= 10 且失败率 > 10%
- 冷却时间：30 分钟内同一告警只发送一次
- 告警通道：优先应用机器人（application_bot），失败回退 Webhook 机器人（feishu_bot）
- 告警内容：时间 / 统计窗口 / 总调用数 / 成功失败数 / 失败率 / 平均耗时 / 总成本

**成本估算表**（每 1K token 价格，美元）：

| 模型 | 输入价格 | 输出价格 |
|------|----------|----------|
| claude-haiku-4-5 | $0.001 | $0.005 |
| claude-sonnet-4-6 | $0.003 | $0.015 |
| claude-opus-4-8 | $0.015 | $0.075 |
| gpt-4o-mini | $0.00015 | $0.0006 |
| gpt-4o | $0.005 | $0.015 |

---

## 七、部署向导 + 回调服务架构（v0.4.0 新增）

### 7.1 部署向导（7 步引导业务用户完成部署）

业务用户首次使用软件时，跟着向导走 7 步即可完成部署，全程不接触代码。

```mermaid
flowchart LR
    A[① 欢迎页] --> B[② 创建飞书应用]
    B --> C[③ 填写凭证]
    C --> D[④ 一键初始化数据]
    D --> E[⑤ 启动回调服务]
    E --> F[⑥ 启动公网隧道]
    F --> G[⑦ 健康检查]

    style A fill:#2d5a3d,color:#fff
    style D fill:#4a3d2d,color:#fff
    style E fill:#5a2d2d,color:#fff
    style F fill:#5a2d2d,color:#fff
    style G fill:#2d3a5a,color:#fff
```

**关键设计**：
- 每步只做一件事，说人话，给操作按钮
- 步骤⑤⑥用快递类比解释回调服务和公网隧道的作用（回调服务=快递接收员、公网隧道=门牌号、请求地址=收件地址）
- 步骤④一键初始化：建 4 张业务表 + 1 张采集配置表 + 3 个业务视图 + 表格权限，10-30 秒完成
- 步骤⑦健康检查：6 项配置就绪检测（凭证/表格/表配置/权限/回调服务/公网隧道）

### 7.2 回调服务 + 公网隧道（替代 ngrok，业务用户零配置）

```mermaid
flowchart LR
    A[飞书服务器] -->|推送事件| B[公网 URL<br/>xxx.trycloudflare.com]
    B -->|Cloudflare Tunnel| C[本地 8000 端口<br/>FastAPI 回调服务]
    C -->|解析事件| D{事件类型}
    D -->|URL 验证| E[返回 challenge]
    D -->|卡片按钮点击| F[异步回写多维表格]
    D -->|审批状态变更| G[异步回写审批状态]

    style A fill:#5a2d2d,color:#fff
    style B fill:#2d4a5a,color:#fff
    style C fill:#2d5a3d,color:#fff
    style F fill:#2d3a5a,color:#fff
    style G fill:#2d3a5a,color:#fff
```

**回调服务（`src/feishu/card_callback.py` + `src/gui/services/callback_server_thread.py`）**：
- 基于 FastAPI 实现，监听 `http://0.0.0.0:8000/callback`
- 封装为 `CallbackServerThread(QThread)`，GUI 点按钮即可启动/停止，无需开终端
- 用 `uvicorn.Config + uvicorn.Server` 方式，通过 `should_exit=True` 优雅停止
- 兼容飞书 schema 1.0 和 2.0 两种回调格式
- 支持 3 类事件：URL 验证、`card.action.trigger`（卡片按钮点击）、`approval_instance`（审批状态变更）
- 异步回写策略：用 `asyncio.create_task` + `run_in_executor` 避免飞书 3 秒超时

**公网隧道（`src/gui/services/cloudflare_tunnel_thread.py` + `cloudflared_downloader.py`）**：
- 用 Cloudflare Tunnel 替代 ngrok，免费且无需注册
- 首次使用自动下载 `cloudflared`（约 50MB）到 exe 同目录，无需手动安装
- 启动后自动提取公网 URL（形如 `xxx.trycloudflare.com`）
- 启动成功后**自动复制完整回调地址**（`公网 URL + /callback`）到剪贴板
- 在 GUI 渲染**蓝色 HTML 指引卡片**，列出飞书后台两处填写位置的完整路径：
  - ① 事件配置（接收审批状态变更）
  - ② 卡片回传交互（接收审批卡片按钮点击）

### 7.3 审批扫描机制（`src/gui/services/approval_service.py`）

业务用户在飞书审批后台创建审批定义后，GUI 自动扫描获取，无需手动复制 approval_code。

```mermaid
sequenceDiagram
    participant User as 业务用户
    participant GUI as 审批流管理页
    participant ScanThread as 扫描线程
    participant Auth as 飞书认证
    participant API as 飞书审批 API

    User->>GUI: 点"➕ 新建审批规则"
    GUI->>ScanThread: 启动自动扫描
    ScanThread->>Auth: 用 App ID/Secret 换 tenant_access_token
    Auth-->>ScanThread: 返回 token
    ScanThread->>API: POST /approval/v4/approvals（拉取所有已发布审批定义）
    API-->>ScanThread: 返回审批定义列表
    ScanThread-->>GUI: 显示列表供用户选择
    User->>GUI: 点选一个审批定义
    GUI->>API: GET /approval/v4/approvals/{code}（查字段 ID 和节点 ID）
    API-->>GUI: 返回表单字段 ID + 审批节点 ID
    GUI->>GUI: 写入 .env，规则保存生效
```

**扫描前置条件**（扫不到的 3 个常见原因）：
1. 审批定义已发布（草稿扫不到）
2. 应用拥有 `approval:approval` 权限
3. 凭证已保存（系统拿不到 token 就调不了 API）

**PyInstaller 打包**：
- `scripts/build_exe.py` — 打包脚本
- 输出 `dist/跨境电商AI运营中台.exe`（约 80-120MB）
- 用 `--onefile` 打包成单文件，用户双击即用
- 用 `--windowed` 隐藏控制台窗口
- 用 `--collect-submodules src` 收集所有 src 子模块

## 三、数据流

```mermaid
flowchart LR
    subgraph 输入
        I1[飞书采集配置表<br/>15条启用配置]
    end

    subgraph 处理
        P1[读取配置]
        P2[多平台采集<br/>75个商品]
        P3[清洗过滤<br/>剔除低质量]
        P4[SyncService增量同步<br/>去重+分类]
    end

    subgraph 输出
        O1[飞书选品池表<br/>含来源平台字段]
        O2[SyncResult统计<br/>新增/更新/跳过]
    end

    subgraph 周期维护
        M1[每3天凌晨2:00<br/>数据清理任务]
        M2[删除超过3天的旧数据]
    end

    I1 --> P1 --> P2 --> P3 --> P4 --> O1
    P4 -.->|统计| O2
    M1 --> M2 -.->|清理| O1

    style I1 fill:#2d5a3d,color:#fff
    style P4 fill:#5a3d2d,color:#fff
    style O1 fill:#2d3a5a,color:#fff
    style O2 fill:#2d3a5a,color:#fff
    style M1 fill:#4a3d2d,color:#fff
```

## 四、扩展性设计

### 4.1 添加新品类
- **不用改代码**：在飞书"采集配置"表中添加一行，填品类名+平台+数量
- 采集器自动用默认模板生成合理数据

### 4.2 添加新平台
- 在 `multi_platform_mock.py` 的 `_PLATFORM_DB` 中添加平台配置（URL模板/品牌池/价格系数）
- 在 `table_schema.py` 的"来源平台"和"平台"字段选项中添加新平台名

### 4.3 替换为真实采集器
- 实现 `BaseCollector.collect()` 接口
- 在 `tasks.py` 中替换 `MockMultiPlatformCollector` 为真实采集器
- 其他代码无需改动

## 五、测试覆盖

| 测试文件 | 覆盖范围 |
|----------|----------|
| test_collectors.py | ProductInfo / MockAmazonCollector / MockMultiPlatformCollector |
| test_cleaners.py | DataCleaner 过滤逻辑 |
| test_scheduler.py | InventoryAlert / SchedulerManager（5个任务注册） |
| test_feishu_auth.py | 飞书认证 |
| test_feishu_bitable.py | BitableClient |
| test_sync_service.py | SyncResult / 字段映射 / SyncService增量同步 / 数据清理任务 |
| test_feishu_bot.py | Webhook 机器人消息发送 / 库存预警卡片模板 |
| test_card_callback.py | 选品报告卡片 / 销售日报卡片 / 审批卡片 / FastAPI 回调服务 |
| test_approval.py | ApprovalClient / 表单构建 / 审批状态变更回调 / ASIN 提取 / 自动触发任务 |

**当前测试结果**：161 个测试全部通过，覆盖率 63%。

**test_approval.py 覆盖场景**（29 个测试，08-06 新增）：
- ApprovalClient 配置：全配置通过 / 缺 approval_code / 缺 approver_open_id / 缺 node_id
- 表单构建：5 个字段完整 / 字段 ID 正确 / 字段值正确 / 中文不转义
- 创建审批实例：成功返回 instance_code / 未配置返回空 / API 错误返回空
- 查询审批状态：成功返回详情 / 空 instance_code 返回空 / 中文状态文本 / 查询失败返回未知
- 状态码映射：包含所有状态码 / 值都是中文
- 审批状态变更回调：合法事件返回成功 / 缺字段返回失败 / 兼容新格式 schema 2.0
- ASIN 提取：成功提取 / 无 ASIN 字段返回空 / 查询失败返回空
- 自动触发任务：未配置返回 0 / 金额提取（数字/字符串/列表/空值/无效值）
