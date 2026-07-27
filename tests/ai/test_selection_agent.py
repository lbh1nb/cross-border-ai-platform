"""选品 Agent 集成测试：测试 Agent 主流程编排。

mock 策略：
- mock create_agent 返回一个 mock agent
- 验证 run_selection_agent 的输入输出处理
- 不测试真实 LLM 调用（那是端到端测试的范畴）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.ai.agents.selection_agent import run_selection_agent


class TestRunSelectionAgent:
    """run_selection_agent 主流程测试。"""

    def test_successful_run_returns_agent_output(self) -> None:
        """Agent 成功执行时应返回 agent_output。"""
        # mock agent 的 invoke 返回
        mock_message = MagicMock()
        mock_message.content = "分析完成：家居收纳类目有 3 个推荐商品"

        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {
            "messages": [mock_message]
        }

        with patch(
            "src.ai.agents.selection_agent.create_selection_agent",
            return_value=mock_agent,
        ):
            result = run_selection_agent("家居收纳")

        assert result["success"] is True
        assert result["category"] == "家居收纳"
        assert "分析完成" in result["agent_output"]
        mock_agent.invoke.assert_called_once()

    def test_agent_exception_returns_error(self) -> None:
        """Agent 执行抛异常时应返回 success=False。"""
        with patch(
            "src.ai.agents.selection_agent.create_selection_agent",
            side_effect=RuntimeError("LLM 服务不可用"),
        ):
            result = run_selection_agent("厨房用品")

        assert result["success"] is False
        assert "LLM 服务不可用" in result["error"]
        assert result["category"] == "厨房用品"

    def test_empty_messages_returns_empty_output(self) -> None:
        """Agent 返回空消息列表时应返回空输出。"""
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": []}

        with patch(
            "src.ai.agents.selection_agent.create_selection_agent",
            return_value=mock_agent,
        ):
            result = run_selection_agent("户外家具")

        assert result["success"] is True
        assert result["agent_output"] == ""

    def test_user_message_contains_category(self) -> None:
        """验证传给 Agent 的用户消息包含品类名。"""
        mock_agent = MagicMock()
        mock_agent.invoke.return_value = {"messages": []}

        with patch(
            "src.ai.agents.selection_agent.create_selection_agent",
            return_value=mock_agent,
        ):
            run_selection_agent("办公家具")

        # 验证 invoke 被调用，且消息内容包含品类
        call_args = mock_agent.invoke.call_args
        messages = call_args.kwargs.get("messages") or call_args.args[0].get("messages")
        assert messages is not None
        # 第一条消息的 content 应包含品类名
        user_msg = messages[0]
        assert "办公家具" in user_msg.content


class TestCreateSelectionAgent:
    """create_selection_agent 创建测试。"""

    def test_create_agent_without_api_key_raises(self) -> None:
        """未配置 API Key 时创建 Agent 应抛异常。"""
        from src.ai.agents.selection_agent import create_selection_agent
        from src.ai.model_router import reset_model_router
        from src.config import settings

        # 确保单例被重置
        reset_model_router()

        with patch.object(settings, "anthropic_api_key", ""), \
             patch.object(settings, "openai_api_key", ""):
            # ModelRouter 在创建时会检测到无凭证
            # create_selection_agent 调用 get_llm 时会抛 ValueError
            with pytest.raises(ValueError, match="未配置 AI 模型凭证"):
                create_selection_agent()
