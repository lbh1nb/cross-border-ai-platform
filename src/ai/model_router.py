"""多模型路由：按任务复杂度自动选择 LLM 模型。

设计思想：
- 业务代码只关心"我要做什么任务"，不关心用哪个模型
- ModelRouter 根据任务类型映射到对应模型（成本 vs 质量的平衡）
- 支持 OpenAI 官方、OpenAI 兼容的国内大模型（DeepSeek/通义千问/智谱 GLM/Kimi）和 Anthropic

任务复杂度分级：
- simple：分类、提取、摘要（用便宜模型）
- standard：分析、生成、翻译（用标准模型）
- complex：多步推理、Agent 决策（用强模型）

国内大模型支持（v0.5.1 新增）：
    设置 OPENAI_API_BASE 指向国内大模型的 OpenAI 兼容端点，
    ModelRouter 会自动识别并切换到对应模型名。
    例如 DeepSeek：OPENAI_API_BASE=https://api.deepseek.com/v1

使用方式：
    router = get_model_router()
    llm = router.get_llm("standard")  # 获取标准模型
    response = llm.invoke([HumanMessage(content="分析这个商品")])
"""

from __future__ import annotations

from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import BaseMessage

from src.config import settings
from src.observability.logger import get_logger
from src.observability.llm_monitor import llm_monitor

logger = get_logger()


# 任务复杂度 → 模型映射
# 按成本从低到高排序，业务代码根据任务难度选择
_TASK_MODEL_MAP: dict[str, dict[str, str]] = {
    "simple": {
        "openai": "gpt-4o-mini",
        "anthropic": "claude-haiku-4-5",
    },
    "standard": {
        "openai": "gpt-4o",
        "anthropic": "claude-sonnet-4-6",
    },
    "complex": {
        "openai": "gpt-4o",
        "anthropic": "claude-opus-4-8",
    },
}


# 国内大模型 base_url → 模型名映射（v0.5.1 新增）
# 当 OPENAI_API_BASE 命中以下域名时，自动替换为对应国内模型名
# key 是 base_url 中的特征子串（小写），value 是 (simple, standard, complex) 三个模型
_DOMESTIC_MODEL_MAP: dict[str, dict[str, str]] = {
    # DeepSeek：性价比最高，国内访问稳定
    "deepseek": {
        "simple": "deepseek-chat",
        "standard": "deepseek-chat",
        "complex": "deepseek-reasoner",
    },
    # 通义千问（阿里云）
    "dashscope": {
        "simple": "qwen-turbo",
        "standard": "qwen-plus",
        "complex": "qwen-max",
    },
    # 智谱 GLM
    "bigmodel": {
        "simple": "glm-4-flash",
        "standard": "glm-4-plus",
        "complex": "glm-4-plus",
    },
    # 月之暗面 Kimi
    "moonshot": {
        "simple": "moonshot-v1-8k",
        "standard": "moonshot-v1-32k",
        "complex": "moonshot-v1-32k",
    },
}


def _detect_domestic_provider(base_url: str) -> str | None:
    """根据 base_url 识别国内大模型提供商。

    Args:
        base_url: OPENAI_API_BASE 配置值

    Returns:
        命中的国内模型标识（如 "deepseek"），未命中返回 None
    """
    if not base_url:
        return None
    base_lower = base_url.lower()
    for keyword in _DOMESTIC_MODEL_MAP:
        if keyword in base_lower:
            return keyword
    return None


class ModelRouter:
    """多模型路由器：按任务复杂度选择 LLM。

    优先级（v0.5.1 调整）：
    1. 配置了 OPENAI_API_BASE（国内大模型）→ 走 OpenAI 兼容接口
    2. 配置了 ANTHROPIC_API_KEY → 走 Claude
    3. 仅配置了 OPENAI_API_KEY → 走 OpenAI 官方（需代理）
    4. 都没配置 → 抛异常引导用户配置
    """

    def __init__(self) -> None:
        self._provider = self._detect_provider()
        self._domestic = _detect_domestic_provider(settings.openai_api_base)
        if self._domestic:
            logger.info(
                f"AI 模型路由器初始化，使用国内大模型：{self._domestic} "
                f"（base_url={settings.openai_api_base}）"
            )
        elif self._provider:
            logger.info(f"AI 模型路由器初始化，使用 {self._provider} 作为主模型")

    def _detect_provider(self) -> str:
        """检测可用的模型提供商。

        优先级：国内大模型（OPENAI_API_BASE 命中）> Anthropic > OpenAI 官方
        """
        # 国内大模型优先：配了 base_url 且 OpenAI Key 也有，走兼容接口
        if settings.openai_api_base and settings.openai_api_key:
            return "openai"
        if settings.anthropic_api_key:
            return "anthropic"
        if settings.openai_api_key:
            return "openai"
        logger.error(
            "未配置任何 AI 模型凭证。请在 .env 文件中设置：\n"
            "  - 国内大模型（推荐）：OPENAI_API_BASE + OPENAI_API_KEY\n"
            "  - Anthropic Claude：ANTHROPIC_API_KEY\n"
            "  - OpenAI 官方（需代理）：OPENAI_API_KEY"
        )
        return ""

    def get_llm(self, task_type: str = "standard", **kwargs: Any) -> BaseChatModel:
        """获取指定任务类型的 LLM 实例。

        Args:
            task_type: 任务复杂度，可选 "simple" / "standard" / "complex"
            **kwargs: 透传给 LLM 构造函数的额外参数（如 temperature）

        Returns:
            LangChain ChatModel 实例

        Raises:
            ValueError: 未配置任何 AI 凭证时抛出
        """
        if not self._provider:
            raise ValueError(
                "未配置 AI 模型凭证。请在 .env 文件中设置：\n"
                "  - 国内大模型（推荐 DeepSeek）：\n"
                "      OPENAI_API_BASE=https://api.deepseek.com/v1\n"
                "      OPENAI_API_KEY=sk-xxxxxxxx\n"
                "  - Anthropic Claude：ANTHROPIC_API_KEY=sk-ant-xxxxxxxx\n"
            )

        if task_type not in _TASK_MODEL_MAP:
            logger.warning(f"未知任务类型 '{task_type}'，回退到 'standard'")
            task_type = "standard"

        # 国内大模型：用对应的国内模型名替换 OpenAI 默认模型名
        if self._domestic:
            model_name = _DOMESTIC_MODEL_MAP[self._domestic][task_type]
            return self._create_openai_llm(model_name, **kwargs)

        model_name = _TASK_MODEL_MAP[task_type][self._provider]

        if self._provider == "anthropic":
            return self._create_anthropic_llm(model_name, **kwargs)
        return self._create_openai_llm(model_name, **kwargs)

    def _create_anthropic_llm(
        self, model_name: str, **kwargs: Any
    ) -> BaseChatModel:
        """创建 Anthropic Claude LLM 实例（已挂载调用监控）。"""
        from langchain_anthropic import ChatAnthropic

        default_kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": settings.anthropic_api_key,
            "timeout": 60,
            "max_retries": 2,
            "callbacks": [llm_monitor],  # 挂载 LLM 调用监控
        }
        # Claude 4.6+ 默认开启 adaptive thinking，不传 thinking 参数
        default_kwargs.update(kwargs)

        logger.info(f"创建 Anthropic LLM: {model_name}")
        return ChatAnthropic(**default_kwargs)

    def _create_openai_llm(
        self, model_name: str, **kwargs: Any
    ) -> BaseChatModel:
        """创建 OpenAI 兼容 LLM 实例（已挂载调用监控）。

        支持三种场景：
        - OpenAI 官方：OPENAI_API_BASE 留空
        - 国内大模型兼容：OPENAI_API_BASE 填对应端点（如 DeepSeek）
        - 自建代理/网关：OPENAI_API_BASE 填自定义地址
        """
        from langchain_openai import ChatOpenAI

        default_kwargs: dict[str, Any] = {
            "model": model_name,
            "api_key": settings.openai_api_key,
            "timeout": 60,
            "max_retries": 2,
            "callbacks": [llm_monitor],  # 挂载 LLM 调用监控
        }
        # 仅当配置了 base_url 才传入（v0.5.1 新增，支持国内大模型）
        if settings.openai_api_base:
            default_kwargs["base_url"] = settings.openai_api_base
        default_kwargs.update(kwargs)

        provider_label = self._domestic or "OpenAI"
        base_info = f"，base_url={settings.openai_api_base}" if settings.openai_api_base else ""
        logger.info(f"创建 {provider_label} LLM: {model_name}{base_info}")
        return ChatOpenAI(**default_kwargs)


# 模块级单例
_router: ModelRouter | None = None


def get_model_router() -> ModelRouter:
    """获取 ModelRouter 单例。

    使用单例模式避免重复初始化，业务代码直接调用即可。
    """
    global _router
    if _router is None:
        _router = ModelRouter()
    return _router


def reset_model_router() -> None:
    """重置单例（配置变更后调用，如 GUI 保存了新的 API Key）。"""
    global _router
    _router = None
