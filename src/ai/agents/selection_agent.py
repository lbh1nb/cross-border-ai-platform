"""选品分析 Agent：ReAct 模式的多步推理 Agent。

设计思想：
- 使用 LangChain v1.0 的 create_agent（基于 LangGraph）
- Agent 拥有 3 个工具：抓取、分析、报告
- LLM 自主决策调用顺序，最多 5 轮工具调用
- 业务用户输入品类名，Agent 自动完成"抓取 → 分析 → 推送"全流程

使用方式：
    from src.ai.agents.selection_agent import run_selection_agent
    result = run_selection_agent("家居收纳")
    print(result)

架构图：
    用户输入品类
        ↓
    [Agent LLM 决策] ← [工具列表]
        ↓
    调用 fetch_products（抓取商品）
        ↓
    [Agent LLM 决策]
        ↓
    调用 analyze_products（LLM 分析）
        ↓
    [Agent LLM 决策]
        ↓
    调用 save_report（保存 + 推送）
        ↓
    输出最终结果
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from src.ai.agents.selection_tools import SELECTION_TOOLS
from src.ai.model_router import get_model_router
from src.observability.logger import get_logger

logger = get_logger()


# Agent 系统 Prompt
_AGENT_SYSTEM_PROMPT = """你是一个跨境电商选品分析 Agent。你的任务是帮助运营团队分析指定品类的选品机会。

工作流程：
1. 调用 fetch_products 抓取指定品类的商品数据
2. 调用 analyze_products 分析商品数据，获得选品建议
3. 调用 save_report 保存结果到飞书多维表格并推送报告到飞书群

决策原则：
- 按顺序调用上述 3 个工具
- 每个工具的输出是下一个工具的输入
- 如果某个工具失败，向用户报告错误，不要继续调用后续工具
- 完成所有步骤后，用中文总结分析结果

你可以使用以下工具：
{tools}
"""


def create_selection_agent():
    """创建选品分析 Agent。

    使用 LangChain v1.0 的 create_agent（基于 LangGraph）。

    Returns:
        CompiledStateGraph 实例（LangGraph 编译后的 Agent）
    """
    from langchain.agents import create_agent

    router = get_model_router()
    llm = router.get_llm("complex", temperature=0.2)

    # 构建带工具描述的系统 Prompt
    tools_descriptions = "\n".join(
        f"- {t.name}: {t.description}" for t in SELECTION_TOOLS
    )
    system_prompt = _AGENT_SYSTEM_PROMPT.format(tools=tools_descriptions)

    # LangChain v1.0 的 create_agent 接受 system_prompt 字符串参数
    # 返回 LangGraph 编译后的 Agent，可直接 invoke
    agent = create_agent(
        model=llm,
        tools=SELECTION_TOOLS,
        system_prompt=system_prompt,
    )

    logger.info("选品分析 Agent 创建完成")
    return agent


def run_selection_agent(category: str) -> dict[str, Any]:
    """运行选品分析 Agent。

    业务入口：输入品类名，Agent 自动完成抓取 → 分析 → 推送全流程。

    Args:
        category: 品类名称，如 "家居收纳"

    Returns:
        包含 agent_output 和 success 的字典
    """
    logger.info(f"启动选品分析 Agent，品类：{category}")

    try:
        agent = create_selection_agent()

        # 构造用户输入
        user_message = HumanMessage(
            content=f"请分析品类「{category}」的选品机会，抓取 10 个商品，"
                    f"分析后保存结果并推送到飞书群。"
        )

        # 调用 Agent
        logger.info("Agent 开始执行...")
        result = agent.invoke({"messages": [user_message]})

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

        logger.info("Agent 执行完成")
        return {
            "success": True,
            "agent_output": final_message,
            "category": category,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error("Agent 执行失败: {}", error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg,
            "category": category,
        }


if __name__ == "__main__":
    # 直接运行此文件可测试
    import sys

    category = sys.argv[1] if len(sys.argv) > 1 else "家居收纳"
    result = run_selection_agent(category)
    print(f"\n{'='*60}")
    print(f"Agent 结果：")
    print(f"{'='*60}")
    print(f"成功：{result.get('success')}")
    print(f"品类：{result.get('category')}")
    if result.get("success"):
        print(f"\n输出：\n{result.get('agent_output')}")
    else:
        print(f"\n错误：{result.get('error')}")
