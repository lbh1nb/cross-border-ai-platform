"""Agent 编排引擎单元测试（v0.7.0 新增，08-19 任务）。

覆盖：
- OrchestratorState / OrchestrationScenario 枚举完整性
- OrchestratorContext / OrchestrationResult 数据结构默认值
- Orchestrator._should_trigger_review: 复盘触发关键词判断
- Orchestrator._extract_top_picks: 从选品 Agent 输出解析 top_picks
- Orchestrator._write_picks_to_listing: 写入 Listing 库
- Orchestrator.run_selection_to_listing: 场景① 选品→Listing 全流程
- Orchestrator.run_insight_to_selection_review: 场景② 洞察→复盘触发
- 便捷入口函数 run_selection_to_listing / run_insight_to_selection_review
- should_trigger_review_from_insight 工具函数

mock 策略：
- 注入 Mock 的 selection_runner / listing_runner，避免真实 LLM 调用
- mock create_listing_sync_service 和 bitable_client，避免飞书 API 调用
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai.orchestrator import (
    Orchestrator,
    OrchestratorContext,
    OrchestrationResult,
    OrchestrationScenario,
    OrchestratorState,
    _REVIEW_TRIGGER_KEYWORDS,
    run_insight_to_selection_review,
    run_selection_to_listing,
    should_trigger_review_from_insight,
)


# ============================================================
# 枚举与数据结构测试
# ============================================================


class TestOrchestratorEnums:
    """编排引擎枚举完整性测试。"""

    def test_state_enum_has_six_states(self) -> None:
        """状态机应包含 6 个核心状态。"""
        expected = {"idle", "selecting", "selecting_done",
                    "listing_optimizing", "completed", "failed"}
        actual = {s.value for s in OrchestratorState}
        assert actual == expected

    def test_scenario_enum_has_two_scenarios(self) -> None:
        """应包含 2 个联动场景。"""
        expected = {"selection_to_listing", "insight_to_selection"}
        actual = {s.value for s in OrchestrationScenario}
        assert actual == expected

    def test_state_enum_str_value(self) -> None:
        """状态枚举的字符串值应与预期一致。"""
        assert OrchestratorState.IDLE == "idle"
        assert OrchestratorState.SELECTING == "selecting"
        assert OrchestratorState.COMPLETED == "completed"
        assert OrchestratorState.FAILED == "failed"

    def test_review_keywords_complete(self) -> None:
        """复盘触发关键词列表应包含 5 个核心词。"""
        assert _REVIEW_TRIGGER_KEYWORDS == [
            "复盘", "选品", "爆款", "上升", "增长",
        ]


class TestOrchestratorContext:
    """编排引擎上下文数据结构测试。"""

    def test_default_values(self) -> None:
        """新建上下文应有合理的默认值。"""
        ctx = OrchestratorContext(
            scenario=OrchestrationScenario.SELECTION_TO_LISTING
        )
        assert ctx.state == OrchestratorState.IDLE
        assert ctx.scenario == OrchestrationScenario.SELECTION_TO_LISTING
        assert ctx.category == ""
        assert ctx.top_picks == []
        assert ctx.listing_records_created == 0
        assert ctx.review_triggered is False
        assert ctx.error == ""
        assert ctx.started_at != ""
        assert ctx.completed_at == ""

    def test_context_with_category(self) -> None:
        """带品类初始化的上下文应正确保存品类。"""
        ctx = OrchestratorContext(
            scenario=OrchestrationScenario.SELECTION_TO_LISTING,
            category="家居收纳",
        )
        assert ctx.category == "家居收纳"

    def test_context_for_insight_scenario(self) -> None:
        """场景②上下文应保存洞察输入。"""
        ctx = OrchestratorContext(
            scenario=OrchestrationScenario.INSIGHT_TO_SELECTION,
            insight_top_priority="销量上升 50%",
            insight_action_items=["建议复盘爆款"],
        )
        assert ctx.insight_top_priority == "销量上升 50%"
        assert ctx.insight_action_items == ["建议复盘爆款"]


class TestOrchestrationResult:
    """编排引擎结果数据结构测试。"""

    def test_default_success_false(self) -> None:
        """默认结果 success 应为 False。"""
        result = OrchestrationResult(
            success=False,
            scenario="selection_to_listing",
            state="failed",
        )
        assert result.success is False
        assert result.duration_seconds == 0.0
        assert result.summary == ""


# ============================================================
# _should_trigger_review 测试
# ============================================================


class TestShouldTriggerReview:
    """复盘触发判断测试。"""

    def test_keyword_in_top_priority_triggers(self) -> None:
        """top_priority 包含关键词应触发复盘。"""
        assert Orchestrator._should_trigger_review(
            "销量上升明显，建议立即复盘", []
        ) is True

    def test_keyword_in_action_items_triggers(self) -> None:
        """action_items 包含关键词应触发复盘。"""
        assert Orchestrator._should_trigger_review(
            "正常运营", ["对爆款商品进行复盘"]
        ) is True

    def test_no_keyword_does_not_trigger(self) -> None:
        """无任何关键词不应触发复盘。"""
        assert Orchestrator._should_trigger_review(
            "今日销售平稳", ["维持现状", "关注库存"]
        ) is False

    def test_empty_inputs_does_not_trigger(self) -> None:
        """空输入不应触发复盘。"""
        assert Orchestrator._should_trigger_review("", []) is False

    def test_none_action_items_does_not_trigger(self) -> None:
        """action_items 为 None 不应抛异常且不触发。"""
        assert Orchestrator._should_trigger_review("正常", None) is False

    def test_each_keyword_triggers(self) -> None:
        """每个关键词单独出现都应触发。"""
        for keyword in _REVIEW_TRIGGER_KEYWORDS:
            assert Orchestrator._should_trigger_review(
                f"包含{keyword}的文本", []
            ) is True, f"关键词 {keyword} 未触发复盘"

    def test_case_insensitive_keyword(self) -> None:
        """关键词判断应大小写不敏感（虽然中文无大小写，逻辑应保证）。"""
        # 中文关键词无大小写问题，但验证逻辑不抛异常
        assert Orchestrator._should_trigger_review("SELECTING 选品", []) is True

    def test_convenience_function_matches_method(self) -> None:
        """便捷函数 should_trigger_review_from_insight 应与方法行为一致。"""
        assert should_trigger_review_from_insight(
            "销量上升", []
        ) is True
        assert should_trigger_review_from_insight(
            "正常", []
        ) is False


# ============================================================
# _extract_top_picks 测试
# ============================================================


class TestExtractTopPicks:
    """从选品 Agent 输出提取 top_picks 测试。"""

    def test_extract_from_json_code_block(self) -> None:
        """应能从 ```json``` 代码块中提取 top_picks。"""
        selection_result = {
            "agent_output": (
                "分析完成，推荐如下：\n"
                "```json\n"
                '{"top_picks": [{"asin": "B001", "name": "商品A"}, '
                '{"asin": "B002", "name": "商品B"}]}\n'
                "```"
            )
        }
        picks = Orchestrator._extract_top_picks(selection_result)
        assert len(picks) == 2
        assert picks[0]["asin"] == "B001"
        assert picks[1]["name"] == "商品B"

    def test_extract_from_raw_json(self) -> None:
        """应能从裸 JSON 文本中提取 top_picks。"""
        selection_result = {
            "agent_output": (
                '{"top_picks": [{"asin": "B003", "name": "商品C"}], '
                '"summary": "测试"}'
            )
        }
        picks = Orchestrator._extract_top_picks(selection_result)
        assert len(picks) == 1
        assert picks[0]["asin"] == "B003"

    def test_extract_empty_when_no_json(self) -> None:
        """无 JSON 内容时应返回空列表。"""
        selection_result = {
            "agent_output": "今日无推荐商品，请明天再来。"
        }
        picks = Orchestrator._extract_top_picks(selection_result)
        assert picks == []

    def test_extract_empty_when_invalid_json(self) -> None:
        """JSON 解析失败时应返回空列表。"""
        selection_result = {
            "agent_output": "```json\n{invalid json}\n```"
        }
        picks = Orchestrator._extract_top_picks(selection_result)
        assert picks == []

    def test_extract_empty_when_no_top_picks_field(self) -> None:
        """JSON 中无 top_picks 字段时应返回空列表。"""
        selection_result = {
            "agent_output": '```json\n{"summary": "无推荐"}\n```'
        }
        picks = Orchestrator._extract_top_picks(selection_result)
        assert picks == []

    def test_extract_empty_when_no_agent_output(self) -> None:
        """agent_output 为空时应返回空列表。"""
        assert Orchestrator._extract_top_picks({}) == []
        assert Orchestrator._extract_top_picks(
            {"agent_output": ""}
        ) == []

    def test_extract_handles_non_string_output(self) -> None:
        """agent_output 非字符串时应安全处理。"""
        selection_result = {"agent_output": 12345}
        picks = Orchestrator._extract_top_picks(selection_result)
        assert picks == []

    def test_extract_top_picks_must_be_list(self) -> None:
        """top_picks 字段非 list 时应返回空。"""
        selection_result = {
            "agent_output": '```json\n{"top_picks": "not a list"}\n```'
        }
        picks = Orchestrator._extract_top_picks(selection_result)
        assert picks == []


# ============================================================
# _write_picks_to_listing 测试
# ============================================================


class TestWritePicksToListing:
    """选品结果写入 Listing 库测试。"""

    def test_write_returns_count_on_success(self) -> None:
        """成功写入时应返回新增+更新的记录数。"""
        top_picks = [
            {"asin": "B001", "name": "商品A"},
            {"asin": "B002", "name": "商品B"},
        ]

        mock_sync_result = MagicMock()
        mock_sync_result.new_count = 2
        mock_sync_result.update_count = 0
        mock_sync_result.skip_count = 0
        mock_sync_result.fail_count = 0

        mock_service = MagicMock()
        mock_service.sync_records.return_value = mock_sync_result

        # _write_picks_to_listing 内部使用 from import，
        # 需 patch src.feishu.sync_service 模块上的工厂函数
        with patch(
            "src.feishu.sync_service.create_listing_sync_service",
            return_value=mock_service,
        ):
            count = Orchestrator._write_picks_to_listing(
                top_picks, "家居收纳"
            )

        assert count == 2
        mock_service.sync_records.assert_called_once()

    def test_write_returns_zero_when_no_picks(self) -> None:
        """空 picks 列表应返回 0。"""
        count = Orchestrator._write_picks_to_listing([], "家居收纳")
        assert count == 0

    def test_write_returns_zero_when_picks_have_no_asin(self) -> None:
        """picks 中所有记录无 ASIN 时应返回 0。"""
        top_picks = [
            {"name": "商品A"},  # 无 asin
            {"name": "商品B"},
        ]
        count = Orchestrator._write_picks_to_listing(top_picks, "家居收纳")
        assert count == 0


# ============================================================
# Orchestrator.run_selection_to_listing 测试（场景①）
# ============================================================


class TestRunSelectionToListing:
    """场景①：选品 → Listing 联动测试。"""

    def _make_selection_success(self) -> dict:
        """构造选品成功的返回值。"""
        return {
            "success": True,
            "agent_output": (
                "```json\n"
                '{"top_picks": [{"asin": "B001", "name": "商品A"}, '
                '{"asin": "B002", "name": "商品B"}]}\n'
                "```"
            ),
        }

    def _make_listing_success(self) -> dict:
        """构造 Listing Agent 成功的返回值。"""
        return {
            "success": True,
            "agent_output": "Listing 优化完成，共 2 条",
        }

    def test_successful_flow_returns_completed_state(self) -> None:
        """成功流程应返回 state=completed。"""
        mock_sync_result = MagicMock()
        mock_sync_result.new_count = 2
        mock_sync_result.update_count = 0
        mock_sync_result.skip_count = 0
        mock_sync_result.fail_count = 0
        mock_service = MagicMock()
        mock_service.sync_records.return_value = mock_sync_result

        with patch(
            "src.feishu.sync_service.create_listing_sync_service",
            return_value=mock_service,
        ):
            orchestrator = Orchestrator(
                selection_runner=lambda c: self._make_selection_success(),
                listing_runner=lambda limit: self._make_listing_success(),
            )
            result = orchestrator.run_selection_to_listing("家居收纳")

        assert result.success is True
        assert result.state == "completed"
        assert result.scenario == "selection_to_listing"
        assert "场景①完成" in result.summary
        assert result.duration_seconds >= 0.0

    def test_selection_failure_returns_failed_state(self) -> None:
        """选品 Agent 失败时应返回 state=failed。"""
        mock_selection = MagicMock(
            return_value={"success": False, "error": "LLM 服务不可用"}
        )
        orchestrator = Orchestrator(
            selection_runner=mock_selection,
            listing_runner=lambda limit: self._make_listing_success(),
        )
        result = orchestrator.run_selection_to_listing("厨房用品")

        assert result.success is False
        assert result.state == "failed"
        assert "选品 Agent 失败" in result.summary

    def test_empty_top_picks_returns_failed(self) -> None:
        """选品成功但无 top_picks 时应返回 failed。"""
        mock_selection = MagicMock(
            return_value={
                "success": True,
                "agent_output": "今日无推荐商品",
            }
        )
        orchestrator = Orchestrator(
            selection_runner=mock_selection,
            listing_runner=lambda limit: self._make_listing_success(),
        )
        result = orchestrator.run_selection_to_listing("户外家具")

        assert result.success is False
        assert result.state == "failed"
        assert "未返回任何推荐商品" in result.summary

    def test_listing_failure_does_not_block_overall(self) -> None:
        """Listing Agent 失败不应阻塞整体流程（仍返回 success=True）。"""
        mock_sync_result = MagicMock()
        mock_sync_result.new_count = 2
        mock_sync_result.update_count = 0
        mock_sync_result.skip_count = 0
        mock_sync_result.fail_count = 0
        mock_service = MagicMock()
        mock_service.sync_records.return_value = mock_sync_result

        mock_listing = MagicMock(
            return_value={"success": False, "error": "Listing 工具异常"}
        )

        with patch(
            "src.feishu.sync_service.create_listing_sync_service",
            return_value=mock_service,
        ):
            orchestrator = Orchestrator(
                selection_runner=lambda c: self._make_selection_success(),
                listing_runner=mock_listing,
            )
            result = orchestrator.run_selection_to_listing("办公家具")

        # Listing 失败不阻塞
        assert result.success is True
        assert result.state == "completed"
        assert "部分失败" in result.summary

    def test_progress_callback_is_called(self) -> None:
        """进度回调应被多次调用。"""
        mock_sync_result = MagicMock()
        mock_sync_result.new_count = 2
        mock_sync_result.update_count = 0
        mock_sync_result.skip_count = 0
        mock_sync_result.fail_count = 0
        mock_service = MagicMock()
        mock_service.sync_records.return_value = mock_sync_result

        progress_calls: list[tuple[str, dict]] = []

        def progress_callback(msg: str, ctx: dict) -> None:
            progress_calls.append((msg, ctx))

        with patch(
            "src.feishu.sync_service.create_listing_sync_service",
            return_value=mock_service,
        ):
            orchestrator = Orchestrator(
                selection_runner=lambda c: self._make_selection_success(),
                listing_runner=lambda limit: self._make_listing_success(),
                progress_callback=progress_callback,
            )
            orchestrator.run_selection_to_listing("卧室家具")

        # 至少 3 次：选品启动、选品完成、Listing 启动
        assert len(progress_calls) >= 3
        # 验证回调中包含 state 字段
        for msg, ctx in progress_calls:
            assert "state" in ctx

    def test_progress_callback_exception_does_not_break_flow(self) -> None:
        """进度回调抛异常不应影响主流程。"""
        mock_sync_result = MagicMock()
        mock_sync_result.new_count = 2
        mock_sync_result.update_count = 0
        mock_sync_result.skip_count = 0
        mock_sync_result.fail_count = 0
        mock_service = MagicMock()
        mock_service.sync_records.return_value = mock_sync_result

        def bad_callback(msg: str, ctx: dict) -> None:
            raise RuntimeError("回调内部异常")

        with patch(
            "src.feishu.sync_service.create_listing_sync_service",
            return_value=mock_service,
        ):
            orchestrator = Orchestrator(
                selection_runner=lambda c: self._make_selection_success(),
                listing_runner=lambda limit: self._make_listing_success(),
                progress_callback=bad_callback,
            )
            result = orchestrator.run_selection_to_listing("家居收纳")

        assert result.success is True

    def test_context_records_category_and_picks(self) -> None:
        """上下文应记录品类和提取的 top_picks。"""
        mock_sync_result = MagicMock()
        mock_sync_result.new_count = 2
        mock_sync_result.update_count = 0
        mock_sync_result.skip_count = 0
        mock_sync_result.fail_count = 0
        mock_service = MagicMock()
        mock_service.sync_records.return_value = mock_sync_result

        with patch(
            "src.feishu.sync_service.create_listing_sync_service",
            return_value=mock_service,
        ):
            orchestrator = Orchestrator(
                selection_runner=lambda c: self._make_selection_success(),
                listing_runner=lambda limit: self._make_listing_success(),
            )
            result = orchestrator.run_selection_to_listing("厨房用品")

        assert result.context.category == "厨房用品"
        assert len(result.context.top_picks) == 2
        assert result.context.listing_records_created == 2


# ============================================================
# Orchestrator.run_insight_to_selection_review 测试（场景②）
# ============================================================


class TestRunInsightToSelectionReview:
    """场景②：洞察 → 选品复盘测试。"""

    def _make_selection_success(self) -> dict:
        """构造选品成功的返回值。"""
        return {
            "success": True,
            "agent_output": (
                "```json\n"
                '{"top_picks": [{"asin": "B001", "name": "商品A"}]}\n'
                "```"
            ),
        }

    def test_review_triggered_when_keyword_present(self) -> None:
        """top_priority 包含关键词时应触发复盘。"""
        mock_selection = MagicMock(return_value=self._make_selection_success())
        orchestrator = Orchestrator(selection_runner=mock_selection)
        result = orchestrator.run_insight_to_selection_review(
            top_priority="销量上升明显，建议立即复盘",
            action_items=[],
        )

        assert result.success is True
        assert result.state == "completed"
        assert result.context.review_triggered is True
        mock_selection.assert_called_once()
        assert "场景②完成" in result.summary
        assert "重跑品类" in result.summary

    def test_review_not_triggered_when_no_keyword(self) -> None:
        """无关键词时不应触发复盘。"""
        mock_selection = MagicMock(return_value=self._make_selection_success())
        orchestrator = Orchestrator(selection_runner=mock_selection)
        result = orchestrator.run_insight_to_selection_review(
            top_priority="今日销售平稳",
            action_items=["维持现状", "关注库存"],
        )

        assert result.success is True
        assert result.state == "completed"
        assert result.context.review_triggered is False
        # 不应调用 selection_runner
        mock_selection.assert_not_called()
        assert "未触发复盘条件" in result.summary

    def test_review_triggered_via_action_items(self) -> None:
        """action_items 包含关键词也应触发复盘。"""
        mock_selection = MagicMock(return_value=self._make_selection_success())
        orchestrator = Orchestrator(selection_runner=mock_selection)
        result = orchestrator.run_insight_to_selection_review(
            top_priority="正常运营",
            action_items=["对爆款商品进行复盘"],
        )

        assert result.success is True
        assert result.context.review_triggered is True
        mock_selection.assert_called_once()

    def test_review_uses_category_hint(self) -> None:
        """复盘应使用 category_hint 作为品类。"""
        mock_selection = MagicMock(return_value=self._make_selection_success())
        orchestrator = Orchestrator(selection_runner=mock_selection)
        result = orchestrator.run_insight_to_selection_review(
            top_priority="销量上升",
            action_items=[],
            category_hint="厨房用品",
        )

        assert result.success is True
        assert result.context.review_category == "厨房用品"
        # selection_runner 应被以"厨房用品"调用
        mock_selection.assert_called_once_with("厨房用品")

    def test_review_uses_default_category_when_no_hint(self) -> None:
        """未提供 category_hint 时应使用默认品类「家居收纳」。"""
        mock_selection = MagicMock(return_value=self._make_selection_success())
        orchestrator = Orchestrator(selection_runner=mock_selection)
        result = orchestrator.run_insight_to_selection_review(
            top_priority="建议复盘",
            action_items=[],
        )

        assert result.success is True
        assert result.context.review_category == "家居收纳"
        mock_selection.assert_called_once_with("家居收纳")

    def test_selection_failure_returns_failed(self) -> None:
        """复盘时选品 Agent 失败应返回 failed。"""
        mock_selection = MagicMock(
            return_value={"success": False, "error": "LLM 异常"}
        )
        orchestrator = Orchestrator(selection_runner=mock_selection)
        result = orchestrator.run_insight_to_selection_review(
            top_priority="销量上升",
            action_items=[],
        )

        assert result.success is False
        assert result.state == "failed"
        assert "复盘选品 Agent 失败" in result.summary

    def test_empty_inputs_does_not_trigger(self) -> None:
        """空输入不应触发复盘。"""
        mock_selection = MagicMock()
        orchestrator = Orchestrator(selection_runner=mock_selection)
        result = orchestrator.run_insight_to_selection_review(
            top_priority="",
            action_items=[],
        )

        assert result.success is True
        assert result.context.review_triggered is False
        mock_selection.assert_not_called()


# ============================================================
# 便捷入口函数测试
# ============================================================


class TestConvenienceFunctions:
    """便捷入口函数测试。"""

    def test_run_selection_to_listing_returns_result(self) -> None:
        """run_selection_to_listing 应返回 OrchestrationResult。"""
        mock_sync_result = MagicMock()
        mock_sync_result.new_count = 1
        mock_sync_result.update_count = 0
        mock_sync_result.skip_count = 0
        mock_sync_result.fail_count = 0
        mock_service = MagicMock()
        mock_service.sync_records.return_value = mock_sync_result

        with patch(
            "src.feishu.sync_service.create_listing_sync_service",
            return_value=mock_service,
        ), patch(
            "src.ai.agents.selection_agent.run_selection_agent",
            return_value={
                "success": True,
                "agent_output": '```json\n{"top_picks": [{"asin": "B001", "name": "A"}]}\n```',
            },
        ), patch(
            "src.ai.agents.listing_agent.run_listing_agent",
            return_value={"success": True, "agent_output": "ok"},
        ):
            result = run_selection_to_listing("家居收纳")

        assert isinstance(result, OrchestrationResult)
        assert result.success is True
        assert result.scenario == "selection_to_listing"

    def test_run_insight_to_selection_review_returns_result(self) -> None:
        """run_insight_to_selection_review 应返回 OrchestrationResult。"""
        with patch(
            "src.ai.agents.selection_agent.run_selection_agent"
        ) as mock_sel:
            # 无关键词，不会调用 selection_agent
            result = run_insight_to_selection_review(
                top_priority="正常",
                action_items=[],
            )

        assert isinstance(result, OrchestrationResult)
        assert result.success is True
        assert result.scenario == "insight_to_selection"
        mock_sel.assert_not_called()

    def test_run_selection_to_listing_with_progress_callback(self) -> None:
        """run_selection_to_listing 应支持进度回调。"""
        mock_sync_result = MagicMock()
        mock_sync_result.new_count = 1
        mock_sync_result.update_count = 0
        mock_sync_result.skip_count = 0
        mock_sync_result.fail_count = 0
        mock_service = MagicMock()
        mock_service.sync_records.return_value = mock_sync_result

        progress_calls: list[tuple[str, dict]] = []

        def progress_callback(msg: str, ctx: dict) -> None:
            progress_calls.append((msg, ctx))

        with patch(
            "src.feishu.sync_service.create_listing_sync_service",
            return_value=mock_service,
        ), patch(
            "src.ai.agents.selection_agent.run_selection_agent",
            return_value={
                "success": True,
                "agent_output": '```json\n{"top_picks": [{"asin": "B001", "name": "A"}]}\n```',
            },
        ), patch(
            "src.ai.agents.listing_agent.run_listing_agent",
            return_value={"success": True, "agent_output": "ok"},
        ):
            result = run_selection_to_listing(
                "家居收纳", progress_callback=progress_callback
            )

        assert result.success is True
        assert len(progress_calls) >= 3
