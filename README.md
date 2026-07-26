# 跨境电商 AI 运营中台

> 以飞书为协作入口，用 AI Agent 替代人工重复运营工作，实现从选品到售后全链路智能化。

## 快速开始

### 1. 环境要求

- Python 3.11+
- 飞书开放平台开发者账号

### 2. 安装依赖

```bash
cd cross-border-ai-platform
python -m venv .venv
.venv\Scripts\activate        # Windows
# source .venv/bin/activate   # macOS/Linux
pip install -e ".[dev]"
```

### 3. 配置环境变量

```bash
cp .env.example .env
# 编辑 .env，填入飞书应用凭证
```

### 4. 验证飞书 Token 获取

```bash
python -m src.feishu.auth
```

看到 `✅ tenant_access_token 获取成功` 即表示飞书应用配置正确。

### 5. 运行测试

```bash
pytest
```

## 项目结构

```
cross-border-ai-platform/
├── src/
│   ├── config.py              # 配置中心（统一从 .env 读取）
│   ├── pipeline/              # 数据管道层
│   │   ├── collectors/        # 采集器
│   │   │   ├── base.py        # 采集器基类 + ProductInfo 数据结构
│   │   │   ├── amazon_mock.py # 亚马逊模拟采集器
│   │   │   ├── multi_platform_mock.py  # 多平台采集器（亚马逊/沃尔玛/Wayfair）
│   │   │   └── amazon_real.py # 真实采集器（预留）
│   │   ├── cleaners/          # 清洗器
│   │   ├── writers/           # 写入器（飞书多维表格）
│   │   └── pipeline.py        # 管道编排器
│   ├── feishu/                # 飞书中台
│   │   ├── auth.py            # 认证（tenant_access_token）
│   │   ├── bitable.py         # 多维表格 API（增删改查+字段管理）
│   │   ├── init_tables.py     # 业务表初始化（选品池/Listing/销售日报/库存预警）
│   │   ├── config_table.py    # 采集配置表初始化（含15条默认家具配置）
│   │   └── table_schema.py    # 表结构定义（5张表）
│   ├── mock/                  # 模拟数据
│   │   └── mock_erp.py        # Mock ERP 库存数据
│   ├── observability/         # 可观测性
│   │   └── logger.py          # 日志（loguru，按天切割）
│   └── scheduler/             # 定时任务
│       ├── scheduler.py       # APScheduler 调度器
│       ├── tasks.py           # 任务函数（选品采集/库存检查/日报）
│       ├── triggers.py        # 触发器配置
│       └── inventory_alert.py # 库存预警等级
├── scripts/                   # 运维脚本
│   ├── init_tables.py         # 创建业务表
│   ├── add_platform_field.py  # 给旧选品池表加"来源平台"字段
│   ├── run_task_once.py       # 手动触发任务
│   ├── start_scheduler.py     # 启动后台调度器
│   ├── e2e_test_pipeline.py   # 端到端验证
│   ├── install.ps1            # 一键安装（开机自启）
│   └── uninstall.ps1          # 一键卸载
├── tests/                     # 单元测试
├── pyproject.toml
├── .env.example
└── .pre-commit-config.yaml
```

## 核心功能

### 1. 选品助手（多平台多品类采集）

**解决什么问题**：不知道该进什么货卖。

**怎么做的**：
- 飞书"采集配置"表定义企业经营品类与采集平台（可自定义，非家具企业也能用）
- 每天 9:00 自动读取启用的配置，循环采集多平台多品类商品
- 默认 5 个家具品类 × 3 个平台（亚马逊/沃尔玛/Wayfair）= 15 条采集任务
- 每条任务采集 5 个商品，共 75 个/天
- 自动清洗过滤（评分/价格/排名）
- 写入飞书选品池表，含商品名/价格/评分/来源平台/利润空间等

**企业自定义**：
- 在飞书"采集配置"表中停用默认配置
- 添加自己的品类（如"蓝牙耳机"/"美妆"等文本字段，无需改代码）
- 选择平台、设置采集数量和优先级

### 2. 库存预警

每 30 分钟检查一次飞书库存预警表，根据可售天数自动更新预警等级（紧急/预警/关注/正常）。

### 3. 定时调度

APScheduler + SQLite 持久化，支持开机自启的后台运行模式。

## 已实现功能

- [x] 项目骨架搭建 + 飞书认证（tenant_access_token 自动刷新）
- [x] 多维表格表结构设计 + 5张业务表创建（选品池/Listing库/销售日报/库存预警/采集配置）
- [x] 多平台数据采集（亚马逊/沃尔玛/Wayfair 三大跨境电商平台）
- [x] 数据管道框架（采集 → 清洗 → 写入 三层架构）
- [x] 定时调度（APScheduler + SQLite 持久化）
- [x] 后台运行（开机自启 + 无终端静默运行）
- [x] 可配置采集范围（企业可在飞书表格自定义品类，非家具企业也能用）
- [x] 库存预警（每30分钟自动检查，更新预警等级）
- [x] 表格权限管理（一键设置组织内可编辑）

完整计划见 [28天实施计划.md](file:///d:\ai\07-26\28天实施计划.md)

## 技术栈

| 层 | 技术 |
|----|------|
| AI 框架 | LangChain，GPT-4o-mini / Claude 3.5 Sonnet |
| 后端 | Python，FastAPI，APScheduler |
| 数据 | 飞书多维表格（Bitable API），SQLite |
| 通知 | 飞书 Webhook 机器人，交互卡片 |
| 部署 | Docker，GitHub Actions |
