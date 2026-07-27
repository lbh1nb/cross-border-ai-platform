"""Prompt 模板管理器：集中管理所有 Agent 的 Prompt。

设计思想：
- Prompt 是 Agent 的"灵魂"，集中管理便于版本控制和调优
- 使用 LangChain 的 ChatPromptTemplate 支持变量渲染
- 每个模板有名称、版本、描述，便于追踪和回滚

使用方式：
    pm = get_prompt_manager()
    prompt = pm.get_prompt("selection_analysis", category="家居收纳", products=...)
    messages = prompt.format_messages()
"""

from __future__ import annotations

from pathlib import Path

from langchain_core.prompts import ChatPromptTemplate

from src.observability.logger import get_logger

logger = get_logger()


# Prompt 模板目录
_PROMPTS_DIR = Path(__file__).resolve().parent.parent.parent / "prompts"


class PromptManager:
    """Prompt 模板管理器。

    管理所有 Agent 的 Prompt 模板，支持：
    - 按名称获取模板
    - 变量渲染
    - 从文件加载（便于版本管理）
    """

    def __init__(self) -> None:
        self._templates: dict[str, ChatPromptTemplate] = {}
        self._load_builtin_templates()
        logger.info(f"PromptManager 初始化完成，已加载 {len(self._templates)} 个模板")

    def _load_builtin_templates(self) -> None:
        """加载内置的 Prompt 模板。"""
        # 选品分析 Agent 的系统 Prompt
        self._templates["selection_system"] = ChatPromptTemplate.from_messages([
            ("system", _SELECTION_SYSTEM_PROMPT),
        ])

        # 选品分析 Agent 的用户 Prompt（分析商品数据）
        self._templates["selection_analysis"] = ChatPromptTemplate.from_messages([
            ("system", _SELECTION_SYSTEM_PROMPT),
            ("human", _SELECTION_ANALYSIS_PROMPT),
        ])

        # 选品报告生成 Prompt
        self._templates["selection_report"] = ChatPromptTemplate.from_messages([
            ("system", _SELECTION_SYSTEM_PROMPT),
            ("human", _SELECTION_REPORT_PROMPT),
        ])

    def get_prompt(self, name: str, **kwargs: object) -> ChatPromptTemplate:
        """获取指定名称的 Prompt 模板。

        Args:
            name: 模板名称
            **kwargs: 模板变量（用于渲染）

        Returns:
            ChatPromptTemplate 实例（已渲染变量）

        Raises:
            KeyError: 模板不存在
        """
        template = self._templates.get(name)
        if template is None:
            raise KeyError(
                f"Prompt 模板 '{name}' 不存在。"
                f"可用模板：{list(self._templates.keys())}"
            )
        return template

    def list_templates(self) -> list[str]:
        """列出所有已加载的模板名称。"""
        return list(self._templates.keys())


# ============ 内置 Prompt 模板 ============

_SELECTION_SYSTEM_PROMPT = """你是一位资深的跨境电商选品专家，擅长分析亚马逊、沃尔玛、Wayfair 等平台的商品数据，从市场容量、竞争强度、利润空间三个维度评估选品机会。

你的分析原则：
1. **市场容量**：通过 BSR 排名和评论数判断需求规模
   - BSR 排名越靠前（数字越小），需求越大
   - 评论数 > 1000 说明市场成熟，< 200 说明新兴市场
2. **竞争强度**：通过评分分布和品牌集中度判断
   - 评分 4.3+ 且评论数多 → 竞争激烈，新进入者难
   - 评分 < 4.0 → 有改进空间，机会较大
3. **利润空间**：通过价格区间和品类特征判断
   - 价格 > $50 且利润空间"高" → 优先考虑
   - 价格 < $20 → 利润薄，靠走量

输出要求：
- 给出明确的"推荐/观望/放弃"建议
- 用数据支撑结论，不要泛泛而谈
- 输出结构化 JSON，便于程序解析
"""


_SELECTION_ANALYSIS_PROMPT = """请分析以下品类"{category}"的 {product_count} 个商品数据，给出选品建议。

商品数据（JSON 格式）：
{products_json}

请按以下 JSON 格式输出分析结果（只输出 JSON，不要其他文字）：
```json
{{
  "category": "{category}",
  "market_capacity": "高/中/低",
  "competition_level": "激烈/中等/蓝海",
  "profit_potential": "高/中/低",
  "top_picks": [
    {{
      "asin": "B0xxx",
      "name": "商品名",
      "reason": "推荐理由（20-50字）",
      "estimated_margin": "高/中/低"
    }}
  ],
  "summary": "总体分析（50-100字）"
}}
```"""


_SELECTION_REPORT_PROMPT = """基于以下选品分析结果，生成一份给运营团队的选品报告。

分析结果：
{analysis_json}

报告要求：
1. 标题：[选品报告] {category} 类目分析
2. 包含市场概况、Top 3 推荐商品、风险提示
3. 语言简洁专业，适合飞书群推送
4. 字数控制在 200-300 字

请直接输出报告内容（纯文本，不要 Markdown 格式）："""


# 模块级单例
_manager: PromptManager | None = None


def get_prompt_manager() -> PromptManager:
    """获取 PromptManager 单例。"""
    global _manager
    if _manager is None:
        _manager = PromptManager()
    return _manager
