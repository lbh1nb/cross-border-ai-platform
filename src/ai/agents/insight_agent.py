"""数据洞察 Agent：ReAct 模式，每日 18:00 自动生成日报。

设计思想：
- 使用 LangChain v1.0 的 create_agent（基于 LangGraph）
- Agent 拥有 3 个工具：拉数据、分析、保存+推送
- LLM 自主决策调用顺序，最多 5 轮工具调用
- 业务用户无感，定时任务每日 18:00 触发，自动推送日报到飞书群

使用方式：
    from src.ai.agents.insight_agent import run_insight_agent
    result = run_insight_agent()  # 默认分析昨天数据
    print(result)

架构图：
    定时任务 18:00 触发
        ↓
    [Agent LLM 决策] ← [工具列表]
        ↓
    调用 fetch_daily_data（拉昨日销售+库存数据）
        ↓
    [Agent LLM 决策]
        ↓
    调用 analyze_daily_data（LLM 三维度分析）
        ↓
    [Agent LLM 决策]
        ↓
    调用 save_insight_report（写回表格 + 推送卡片）
        ↓
    飞书群收到日报卡片
"""

from __future__ import annotations

from typing import Any

from langchain_core.messages import HumanMessage

from src.ai.agents.insight_tools import INSIGHT_TOOLS
from src.ai.model_router import get_model_router
from src.observability.logger import get_logger

logger = get_logger()


# Agent 系统 Prompt
_AGENT_SYSTEM_PROMPT = """你是一个跨境电商数据洞察 Agent。你的任务是每日生成数据洞察日报并推送到飞书群。

工作流程：
1. 调用 fetch_daily_data 拉取昨日销售数据和当前库存预警数据
2. 调用 analyze_daily_data 让 LLM 从销量/广告/库存三维度分析数据
3. 调用 save_insight_report 把 AI 洞察写回销售日报表 + 推送日报卡片到飞书群

决策原则：
- 按顺序调用上述 3 个工具
- 每个工具的输出是下一个工具的输入
- 如果某个工具失败，向用户报告错误，不要继续调用后续工具
- 完成所有步骤后，用中文总结日报要点

你可以使用以下工具：
{tools}
"""


def create_insight_agent():
    """创建数据洞察 Agent。

    使用 LangChain v1.0 的 create_agent（基于 LangGraph）。

    Returns:
        CompiledStateGraph 实例（LangGraph 编译后的 Agent）
    """
    from langchain.agents import create_agent

    router = get_model_router()
    llm = router.get_llm("complex", temperature=0.2)

    # 构建带工具描述的系统 Prompt
    tools_descriptions = "\n".join(
        f"- {t.name}: {t.description}" for t in INSIGHT_TOOLS
    )
    system_prompt = _AGENT_SYSTEM_PROMPT.format(tools=tools_descriptions)

    agent = create_agent(
        model=llm,
        tools=INSIGHT_TOOLS,
        system_prompt=system_prompt,
    )

    logger.info("数据洞察 Agent 创建完成")
    return agent


def run_insight_agent(target_date: str = "") -> dict[str, Any]:
    """运行数据洞察 Agent。

    业务入口：定时任务每日 18:00 调用，自动拉昨日数据 → 分析 → 推送日报。

    Args:
        target_date: 目标日期 YYYY-MM-DD，留空表示昨天

    Returns:
        包含 agent_output 和 success 的字典
    """
    date_desc = target_date if target_date else "昨天"
    logger.info(f"启动数据洞察 Agent，分析日期：{date_desc}")

    try:
        agent = create_insight_agent()

        # 构造用户输入
        date_arg = target_date if target_date else ""
        user_message = HumanMessage(
            content=f"请分析 {date_desc} 的业务数据，"
                    f"拉取销售日报和库存预警数据，"
                    f"生成数据洞察日报并推送到飞书群。"
                    f"（target_date 参数填：{date_arg}）"
        )

        # 调用 Agent，限制最多 5 轮工具调用（recursion_limit=10）
        # LangGraph 每轮工具调用约 2 步（agent 节点 + tools 节点），5 轮 = 10 步
        # 防止 Agent 死循环或无限调用工具
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

        logger.info("数据洞察 Agent 执行完成")
        return {
            "success": True,
            "agent_output": final_message,
            "target_date": date_desc,
        }

    except Exception as e:
        error_msg = str(e)
        logger.error("数据洞察 Agent 执行失败: {}", error_msg, exc_info=True)
        return {
            "success": False,
            "error": error_msg,
            "target_date": date_desc,
        }


if __name__ == "__main__":
    # 直接运行此文件可测试
    import sys

    target = sys.argv[1] if len(sys.argv) > 1 else ""
    result = run_insight_agent(target)
    print(f"\n{'='*60}")
    print(f"数据洞察 Agent 结果：")
    print(f"{'='*60}")
    print(f"成功：{result.get('success')}")
    print(f"日期：{result.get('target_date')}")
    if result.get("success"):
        print(f"\n输出：\n{result.get('agent_output')}")
    else:
        print(f"\n错误：\n{result.get('error')}")
