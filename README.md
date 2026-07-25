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
│   ├── config.py              # 配置中心
│   ├── pipeline/              # 数据管道层
│   │   ├── collectors/        # 采集器（亚马逊、ERP）
│   │   ├── cleaners/          # 清洗器
│   │   └── writers/           # 写入器（飞书多维表格）
│   ├── feishu/                # 飞书中台
│   │   ├── auth.py            # 认证（tenant_access_token）
│   │   ├── bitable.py         # 多维表格 API
│   │   ├── bot.py             # 机器人消息
│   │   ├── approval.py        # 审批流
│   │   └── client.py          # 统一封装
│   ├── ai/                    # AI 调度层
│   │   ├── prompt_manager.py
│   │   ├── tool_registry.py
│   │   ├── model_router.py
│   │   └── agents/            # 业务 Agent
│   ├── observability/         # 可观测性
│   │   ├── logger.py          # 日志
│   │   └── metrics.py         # 指标
│   └── scheduler.py           # 定时任务
├── tests/                     # 测试
├── docs/                      # 文档
├── pyproject.toml
├── .env.example
└── .pre-commit-config.yaml
```

## 开发进度

- [x] 07-27 项目骨架搭建
- [x] 07-27 飞书认证模块
- [ ] 07-28 多维表格表结构设计
- [ ] 07-29 亚马逊数据采集
- [ ] 07-30 数据管道框架

完整计划见 [28天实施计划.md](file:///d:\ai\07-26\28天实施计划.md)

## 技术栈

| 层 | 技术 |
|----|------|
| AI 框架 | LangChain，GPT-4o-mini / Claude 3.5 Sonnet |
| 后端 | Python，FastAPI，APScheduler |
| 数据 | 飞书多维表格（Bitable API），SQLite |
| 通知 | 飞书 Webhook 机器人，交互卡片 |
| 部署 | Docker，GitHub Actions |
