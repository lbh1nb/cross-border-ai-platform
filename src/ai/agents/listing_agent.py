"""Listing 优化 Agent：对"待优化"状态的 Listing 自动生成优化文案。

设计思想（v0.7.0 新增）：
- 与 selection_agent / insight_agent 保持一致的代码风格
- 使用 LangChain v1.0 的 create_agent（基于 LangGraph）
- 3 工具：fetch_pending_listings / optimize_listing / save_listing
- 未配置 API Key 时由 listing_tools 内部 Mock 兜底，Agent 流程仍可跑通
- 接入 API Key 后自动切换真实 LLM 生成优化文案，无需改代码

使用方式：
    from src.ai.agents.listing_agent import run_listing_agent
    result = run_listing_agent()
    print(result)

架构图：
    启动 Listing Agent
        ↓
    [Agent LLM 决策] ← [工具列表]
        ↓
    调用 fetch_pending_listings（拉取待优化商品）
        ↓
    [Agent LLM 决策]
        ↓
    调用 optimize_listing（LLM 优化 或 Mock 兜底）
        ↓
    [Agent LLM 决策]
        ↓
    调用 save_listing（写回表格 + 推送卡片）
        ↓
    输出最终结果
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from src.ai.agents.listing_tools import LISTING_TOOLS
from src.ai.model_router import get_model_router
from src.observability.logger import get_logger

logger = get_logger()


# Agent 系统 Prompt
_AGENT_SYSTEM_PROMPT = """你是一个跨境电商 Listing 优化 Agent。你的任务是为"待优化"状态的 Listing 自动生成优化文案。

工作流程：
1. 调用 fetch_pending_listings 拉取 Listing 库中"待优化"状态的商品
2. 调用 optimize_listing 对待优化商品生成优化标题/五点描述/关键词/建议
3. 调用 save_listing 把优化结果写回飞书 Listing 库 + 推送联动进度卡片

决策原则：
- 按顺序调用上述 3 个工具
- 每个工具的输出是下一个工具的输入
- 如果某个工具失败，向用户报告错误，不要继续调用后续工具
- 完成所有步骤后，用中文总结优化结果

你可以使用以下工具：
{tools}
"""


def create_listing_agent():
    """创建 Listing 优化 Agent。

    使用 LangChain v1.0 的 create_agent（基于 LangGraph）。

    Returns:
        CompiledStateGraph 实例（LangGraph 编译后的 Agent）
    """
    from langchain.agents import create_agent

    router = get_model_router()
    llm = router.get_llm("complex", temperature=0.2)

    # 构建带工具描述的系统 Prompt
    tools_descriptions = "\n".join(
        f"- {t.name}: {t.description}" for t in LISTING_TOOLS
    )
    system_prompt = _AGENT_SYSTEM_PROMPT.format(tools=tools_descriptions)

    agent = create_agent(
        model=llm,
        tools=LISTING_TOOLS,
        system_prompt=system_prompt,
    )

    logger.info("Listing 优化 Agent 创建完成")
    return agent


def run_listing_agent(limit: int = 5) -> dict[str, Any]:
    """运行 Listing 优化 Agent。

    业务入口：拉取 Listing 库"待优化"记录，自动生成优化文案并写回。

    Args:
        limit: 最多处理多少条待优化记录，默认 5

    Returns:
        包含 agent_output 和 success 的字典
    """
    logger.info(f"启动 Listing 优化 Agent，最大处理 {limit} 条")

    try:
        agent = create_listing_agent()

        user_message = HumanMessage(
            content=f"请拉取 {limit} 条待优化 Listing，"
                    f"生成优化文案并保存到飞书 Listing 库，"
                    f"推送进度卡片到飞书群。"
        )

        # 限制最多 5 轮工具调用（recursion_limit=10）
        logger.info("Agent 开始执行...")
        result = agent.invoke(
            {"messages": [user_message]},
            config={"recursion_limit": 10},
        )

        # 提取最终输出
        messages = result.get("messages", [])
        final_message = ""
        if messages:
            last_msg = messages[-1]
            final_message = (
                last_msg.content
                if hasattr(last_msg, "content")
                else str(last_msg)
            )

        logger.info("Listing Agent 执行完成")
        return {
            "success": True,
            "agent_output": final_message,
            "limit": limit,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error("Listing Agent 执行失败: {}", error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg,
            "limit": limit,
        }


if __name__ == "__main__":
    # 直接运行此文件可测试
    result = run_listing_agent()
    print(f"\n{'='*60}")
    print(f"Listing Agent 结果：")
    print(f"{'='*60}")
    print(f"成功：{result.get('success')}")
    if result.get("success"):
        print(f"\n输出：\n{result.get('agent_output')}")
    else:
        print(f"\n错误：\n{result.get('error')}")
