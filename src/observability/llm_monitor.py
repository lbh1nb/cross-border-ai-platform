"""LLM 调用拦截器：基于 LangChain Callback 机制，自动记录每次调用。

设计思想：
- 使用 LangChain 标准的 BaseCallbackHandler，不侵入业务代码
- 在 model_router.py 创建 LLM 时挂载本 Handler，所有调用自动被监控
- 记录：输入摘要、输出摘要、耗时、Token 用量、成本估算、成功/失败
- 异常时触发告警检查

工作流程：
    LLM.invoke() 触发
        ↓
    on_llm_start（记录开始时间、输入摘要、模型名）
        ↓
    LLM 执行
        ↓
    on_llm_end → 计算耗时、提取 token、估算成本 → 写入 SQLite
        ↓
    on_llm_error → 记录失败 → 触发告警检查
"""

from __future__ import annotations

import time
from typing import Any

from langchain_core.callbacks import BaseCallbackHandler
from langchain_core.outputs import LLMResult

from src.observability.logger import get_logger
from src.observability.metrics_store import metrics_store

logger = get_logger()


# ============ 模型成本表（每 1K token 价格，单位：美元）============

_PRICING_PER_1K: dict[str, dict[str, float]] = {
    # Anthropic
    "claude-haiku-4-5": {"input": 0.001, "output": 0.005},
    "claude-sonnet-4-6": {"input": 0.003, "output": 0.015},
    "claude-opus-4-8": {"input": 0.015, "output": 0.075},
    # OpenAI
    "gpt-4o-mini": {"input": 0.00015, "output": 0.0006},
    "gpt-4o": {"input": 0.005, "output": 0.015},
}


def _estimate_cost(model_name: str, input_tokens: int, output_tokens: int) -> float:
    """根据模型名和 token 数估算成本（美元）。

    Args:
        model_name: 模型名称
        input_tokens: 输入 token 数
        output_tokens: 输出 token 数

    Returns:
        估算成本（美元），未知模型返回 0.0
    """
    pricing = _PRICING_PER_1K.get(model_name)
    if not pricing:
        return 0.0
    input_cost = (input_tokens / 1000) * pricing["input"]
    output_cost = (output_tokens / 1000) * pricing["output"]
    return round(input_cost + output_cost, 6)


def _truncate(text: str, max_len: int = 500) -> str:
    """截断长文本，避免日志和数据库过大。"""
    if len(text) <= max_len:
        return text
    return text[:max_len] + f"...[截断，共 {len(text)} 字符]"


class LLMCallMonitor(BaseCallbackHandler):
    """LLM 调用监控回调。

    挂载到 LangChain LLM 实例后，每次 invoke 都会自动触发：
    - on_llm_start: 记录开始时间
    - on_llm_end: 提取 token、计算成本、写入 SQLite
    - on_llm_error: 记录失败、触发告警
    """

    def __init__(self) -> None:
        # run_id → 调用上下文（开始时间、模型名、输入摘要）
        self._contexts: dict[str, dict[str, Any]] = {}

    def on_llm_start(
        self,
        serialized: dict[str, Any],
        prompts: list[str],
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """LLM 调用开始：记录上下文。"""
        # 从 serialized 提取模型名（格式：{"id": ["langchain", "chat_models", "ChatAnthropic", "claude-...", ...]}）
        model_name = ""
        if "id" in serialized and isinstance(serialized["id"], list):
            # id 列表最后一个元素通常是模型名
            model_name = str(serialized["id"][-1])
        elif "name" in serialized:
            model_name = str(serialized["name"])

        self._contexts[str(run_id)] = {
            "start_time": time.time(),
            "model_name": model_name,
            "input_summary": _truncate(prompts[0]) if prompts else "",
        }

    def on_llm_end(
        self,
        response: LLMResult,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """LLM 调用结束：提取 token、计算成本、写入数据库。"""
        run_id_str = str(run_id)
        ctx = self._contexts.pop(run_id_str, None)
        if not ctx:
            return

        duration_ms = int((time.time() - ctx["start_time"]) * 1000)
        model_name = ctx["model_name"]

        # 提取 token 用量
        input_tokens = 0
        output_tokens = 0
        output_summary = ""

        try:
            if response.llm_output and "token_usage" in response.llm_output:
                usage = response.llm_output["token_usage"]
                input_tokens = usage.get("prompt_tokens", 0)
                output_tokens = usage.get("completion_tokens", 0)

            if response.generations and response.generations[0]:
                gen = response.generations[0][0]
                output_summary = _truncate(gen.text or "")
        except Exception as e:
            logger.warning(f"提取 token 用量失败: {e}")

        cost = _estimate_cost(model_name, input_tokens, output_tokens)

        # 写入 SQLite
        try:
            metrics_store.record_call(
                call_id=run_id_str,
                model_name=model_name,
                input_summary=ctx["input_summary"],
                output_summary=output_summary,
                duration_ms=duration_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                cost_usd=cost,
                success=True,
                error_message="",
            )
        except Exception as e:
            logger.error(f"写入 LLM 调用记录失败: {e}")

        logger.info(
            f"LLM 调用完成 | 模型={model_name} | 耗时={duration_ms}ms | "
            f"tokens={input_tokens}+{output_tokens} | 成本=${cost:.6f}"
        )

    def on_llm_error(
        self,
        error: BaseException,
        *,
        run_id: Any = None,
        **kwargs: Any,
    ) -> None:
        """LLM 调用失败：记录失败信息、触发告警。"""
        run_id_str = str(run_id)
        ctx = self._contexts.pop(run_id_str, None)
        if not ctx:
            return

        duration_ms = int((time.time() - ctx["start_time"]) * 1000)
        error_msg = _truncate(str(error), 1000)

        try:
            metrics_store.record_call(
                call_id=run_id_str,
                model_name=ctx["model_name"],
                input_summary=ctx["input_summary"],
                output_summary="",
                duration_ms=duration_ms,
                input_tokens=0,
                output_tokens=0,
                cost_usd=0.0,
                success=False,
                error_message=error_msg,
            )
        except Exception as e:
            logger.error(f"写入 LLM 失败记录失败: {e}")

        logger.error(
            f"LLM 调用失败 | 模型={ctx['model_name']} | 耗时={duration_ms}ms | 错误={error_msg}"
        )

        # 触发告警检查（异步，避免阻塞回调）
        try:
            from src.observability.alert import alert_checker
            alert_checker.check_and_alert()
        except Exception as e:
            logger.warning(f"告警检查失败: {e}")


# 模块级单例
llm_monitor = LLMCallMonitor()
