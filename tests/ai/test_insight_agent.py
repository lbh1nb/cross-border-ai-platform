"""数据洞察 Agent 单元测试：测试 Agent 主流程编排。

mock 策略：
- mock create_insight_agent 返回一个 mock agent
- 验证 run_insight_agent 的输入输出处理
- 不测试真实 LLM 调用（那是端到端测试的范畴）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.ai.agents.insight_agent import run_insight_agent


class TestRunInsightAgent:
    """run_insight_agent 主流程测试。"""

    def test_successful_run_returns_agent_output(self) -> None:
        """Agent 成功执行时应返回 agent_output。"""
        mock_message = MagicMock()
        mock_message.content = "数据洞察完成：昨日销量上升 15%，建议关注库存预警。"

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {
            "messages": [mock_message]
        }

        with patch(
            "src.ai.agents.insight_agent.create_insight_agent",
            return_value=mock_agent,
        ):
            result = run_insight_agent("2026-07-27")

        assert result["success"] is True
        assert result["target_date"] == "2026-07-27"
        assert "数据洞察完成" in result["agent_output"]
        mock_agent.invoke.assert_called_once()

    def test_agent_exception_returns_error(self) -> None:
        """Agent 执行抛异常时应返回 success=False。"""
        with patch(
            "src.ai.agents.insight_agent.create_insight_agent",
            side_effect=RuntimeError("LLM 服务不可用"),
        ):
            result = run_insight_agent("2026-07-27")

        assert result["success"] is False
        assert "LLM 服务不可用" in result["error"]
        assert result["target_date"] == "2026-07-27"

    def test_empty_target_date_uses_yesterday_desc(self) -> None:
        """target_date 留空时 target_date 字段应为「昨天」。"""
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": []}

        with patch(
            "src.ai.agents.insight_agent.create_insight_agent",
            return_value=mock_agent,
        ):
            result = run_insight_agent("")

        assert result["success"] is True
        assert result["target_date"] == "昨天"

    def test_empty_messages_returns_empty_output(self) -> None:
        """Agent 返回空消息列表时应返回空输出。"""
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": []}

        with patch(
            "src.ai.agents.insight_agent.create_insight_agent",
            return_value=mock_agent,
        ):
            result = run_insight_agent("2026-07-27")

        assert result["success"] is True
        assert result["agent_output"] == ""

    def test_user_message_contains_date(self) -> None:
        """验证传给 Agent 的用户消息包含目标日期。"""
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": []}

        with patch(
            "src.ai.agents.insight_agent.create_insight_agent",
            return_value=mock_agent,
        ):
            run_insight_agent("2026-07-27")

        # 验证 invoke 被调用，且消息内容包含日期
        call_args = mock_agent.invoke.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0].get("messages")
        assert messages is not None
        # 第一条消息的 content 应包含日期
        user_msg = messages[0]
        assert "2026-07-27" in user_msg.content

    def test_recursion_limit_is_set(self) -> None:
        """验证调用 Agent 时设置了 recursion_limit=10（最多5轮工具调用）。"""
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": []}

        with patch(
            "src.ai.agents.insight_agent.create_insight_agent",
            return_value=mock_agent,
        ):
            run_insight_agent("2026-07-27")

        call_kwargs = mock_agent.invoke.call_args.kwargs
        config = call_kwargs.get("config", {})
        assert config.get("recursion_limit") == 10


class TestCreateInsightAgent:
    """create_insight_agent 创建测试。"""

    def test_create_agent_without_api_key_raises(self) -> None:
        """未配置 API Key 时创建 Agent 应抛异常。"""
        from src.ai.agents.insight_agent import create_insight_agent
        from src.ai.model_router import reset_model_router
        from src.config import settings

        # 确保单例被重置
        reset_model_router()

        with patch.object(settings, "anthropic_api_key", ""), \
             patch.object(settings, "openai_api_key", ""):
            # ModelRouter 在创建时会检测到无凭证
            # create_insight_agent 调用 get_llm 时会抛 ValueError
            with pytest.raises(ValueError, match="未配置 AI 模型凭证"):
                create_insight_agent()
