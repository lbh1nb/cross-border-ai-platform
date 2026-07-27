"""可观测性模块单元测试：metrics_store、llm_monitor、alert。

测试策略：
- metrics_store：用临时数据库，避免污染开发环境
- llm_monitor：测试成本估算和文本截断（纯函数，无副作用）
- alert：mock metrics_store 和飞书机器人，测试阈值判断和冷却逻辑
"""

from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
from unittest.mock import MagicMock, patch

import pytest

from src.observability.metrics_store import MetricsStore
from src.observability.llm_monitor import _estimate_cost, _truncate, LLMCallMonitor
from src.observability.alert import AlertChecker


# ============ MetricsStore 测试 ============

class TestMetricsStore:
    """MetricsStore 核心功能测试。"""

    @pytest.fixture
    def store(self, tmp_path: Path) -> MetricsStore:
        """用临时目录创建测试用 MetricsStore。"""
        db_path = tmp_path / "test_metrics.db"
        return MetricsStore(db_path=db_path)

    def test_init_creates_table(self, store: MetricsStore) -> None:
        """初始化后应自动建表。"""
        with sqlite3.connect(store._db_path) as conn:
            tables = conn.execute(
                "SELECT name FROM sqlite_master WHERE type='table'"
            ).fetchall()
        assert ("llm_call_logs",) in tables

    def test_record_and_query_call(self, store: MetricsStore) -> None:
        """写入一条调用记录后应能查询到。"""
        store.record_call(
            call_id="test-1",
            model_name="claude-sonnet-4-6",
            input_summary="测试输入",
            output_summary="测试输出",
            duration_ms=500,
            input_tokens=100,
            output_tokens=50,
            cost_usd=0.003,
            success=True,
            error_message="",
        )

        calls = store.get_recent_calls(limit=10)
        assert len(calls) == 1
        assert calls[0]["call_id"] == "test-1"
        assert calls[0]["model_name"] == "claude-sonnet-4-6"
        assert calls[0]["success"] is True

    def test_get_stats_success_rate(self, store: MetricsStore) -> None:
        """统计应正确计算成功率和失败率。"""
        # 写入 8 条成功 + 2 条失败
        for i in range(8):
            store.record_call(
                call_id=f"ok-{i}", model_name="test-model",
                input_summary="", output_summary="",
                duration_ms=100, input_tokens=10, output_tokens=5,
                cost_usd=0.001, success=True, error_message="",
            )
        for i in range(2):
            store.record_call(
                call_id=f"fail-{i}", model_name="test-model",
                input_summary="", output_summary="",
                duration_ms=100, input_tokens=0, output_tokens=0,
                cost_usd=0.0, success=False, error_message="timeout",
            )

        stats = store.get_stats(hours=1)
        assert stats["total"] == 10
        assert stats["success"] == 8
        assert stats["failed"] == 2
        assert stats["failure_rate"] == 0.2

    def test_get_stats_empty_returns_zeros(self, store: MetricsStore) -> None:
        """无数据时统计应返回零值。"""
        stats = store.get_stats(hours=1)
        assert stats["total"] == 0
        assert stats["failure_rate"] == 0.0
        assert stats["total_cost_usd"] == 0.0

    def test_cleanup_removes_old_records(self, store: MetricsStore) -> None:
        """cleanup 应删除超过指定天数的旧记录。"""
        # 写入一条记录
        store.record_call(
            call_id="recent", model_name="test",
            input_summary="", output_summary="",
            duration_ms=100, input_tokens=0, output_tokens=0,
            cost_usd=0.0, success=True, error_message="",
        )

        # 手动将一条记录的时间改成 40 天前
        old_time = (datetime.now() - timedelta(days=40)).isoformat()
        with sqlite3.connect(store._db_path) as conn:
            conn.execute(
                "INSERT INTO llm_call_logs (call_id, model_name, duration_ms, success, created_at) "
                "VALUES ('old', 'test', 100, 1, ?)",
                (old_time,),
            )
            conn.commit()

        # 清理 30 天前的记录
        deleted = store.cleanup(days=30)
        assert deleted == 1

        # 验证 recent 还在
        calls = store.get_recent_calls(limit=10)
        call_ids = [c["call_id"] for c in calls]
        assert "recent" in call_ids
        assert "old" not in call_ids


# ============ llm_monitor 工具函数测试 ============

class TestEstimateCost:
    """成本估算函数测试。"""

    def test_anthropic_sonnet_pricing(self) -> None:
        """Claude Sonnet 成本计算正确。"""
        # input: 1000 tokens * $0.003/1K = $0.003
        # output: 500 tokens * $0.015/1K = $0.0075
        # total = $0.0105
        cost = _estimate_cost("claude-sonnet-4-6", 1000, 500)
        assert cost == pytest.approx(0.0105, rel=1e-3)

    def test_openai_gpt4o_mini_pricing(self) -> None:
        """GPT-4o-mini 成本计算正确。"""
        # input: 1000 * $0.00015/1K = $0.00015
        # output: 500 * $0.0006/1K = $0.0003
        # total = $0.00045
        cost = _estimate_cost("gpt-4o-mini", 1000, 500)
        assert cost == pytest.approx(0.00045, rel=1e-3)

    def test_unknown_model_returns_zero(self) -> None:
        """未知模型返回 0 成本。"""
        cost = _estimate_cost("unknown-model", 1000, 500)
        assert cost == 0.0

    def test_zero_tokens_returns_zero(self) -> None:
        """0 token 返回 0 成本。"""
        cost = _estimate_cost("claude-opus-4-8", 0, 0)
        assert cost == 0.0


class TestTruncate:
    """文本截断函数测试。"""

    def test_short_text_not_truncated(self) -> None:
        """短文本不被截断。"""
        text = "短文本"
        assert _truncate(text, max_len=100) == "短文本"

    def test_long_text_truncated(self) -> None:
        """长文本被截断并附加提示。"""
        text = "a" * 200
        result = _truncate(text, max_len=100)
        assert len(result) < len(text)
        assert "截断" in result
        assert "200" in result

    def test_exact_length_not_truncated(self) -> None:
        """恰好等于 max_len 不被截断。"""
        text = "a" * 50
        assert _truncate(text, max_len=50) == text


# ============ AlertChecker 测试 ============

class TestAlertChecker:
    """告警检查器测试。"""

    def test_no_alert_when_below_min_total(self) -> None:
        """调用数 < 10 时不告警。"""
        checker = AlertChecker()

        mock_stats = {
            "hours": 1, "total": 5, "success": 5, "failed": 0,
            "failure_rate": 0.0, "avg_duration_ms": 100,
            "total_cost_usd": 0.01, "total_input_tokens": 0, "total_output_tokens": 0,
        }

        with patch(
            "src.observability.alert.metrics_store.get_stats",
            return_value=mock_stats,
        ):
            alerted = checker.check_and_alert()

        assert alerted is False

    def test_no_alert_when_failure_rate_below_threshold(self) -> None:
        """失败率 <= 10% 时不告警。"""
        checker = AlertChecker()

        mock_stats = {
            "hours": 1, "total": 20, "success": 19, "failed": 1,
            "failure_rate": 0.05, "avg_duration_ms": 100,
            "total_cost_usd": 0.01, "total_input_tokens": 0, "total_output_tokens": 0,
        }

        with patch(
            "src.observability.alert.metrics_store.get_stats",
            return_value=mock_stats,
        ):
            alerted = checker.check_and_alert()

        assert alerted is False

    def test_alert_when_failure_rate_exceeds_threshold(self) -> None:
        """失败率 > 10% 且总数 >= 10 时触发告警。"""
        checker = AlertChecker()

        mock_stats = {
            "hours": 1, "total": 20, "success": 15, "failed": 5,
            "failure_rate": 0.25, "avg_duration_ms": 100,
            "total_cost_usd": 0.01, "total_input_tokens": 0, "total_output_tokens": 0,
        }

        with patch(
            "src.observability.alert.metrics_store.get_stats",
            return_value=mock_stats,
        ), patch.object(checker, "_send_alert") as mock_send:
            alerted = checker.check_and_alert()

        assert alerted is True
        mock_send.assert_called_once_with(mock_stats)

    def test_cooldown_prevents_repeated_alerts(self) -> None:
        """冷却期内不重复告警。"""
        checker = AlertChecker()

        mock_stats = {
            "hours": 1, "total": 20, "success": 10, "failed": 10,
            "failure_rate": 0.5, "avg_duration_ms": 100,
            "total_cost_usd": 0.01, "total_input_tokens": 0, "total_output_tokens": 0,
        }

        with patch(
            "src.observability.alert.metrics_store.get_stats",
            return_value=mock_stats,
        ), patch.object(checker, "_send_alert"):
            # 第一次告警
            first = checker.check_and_alert()
            assert first is True

            # 冷却期内第二次应被阻止
            second = checker.check_and_alert()
            assert second is False

    def test_alert_text_contains_key_info(self) -> None:
        """告警消息应包含关键信息。"""
        checker = AlertChecker()
        stats = {
            "hours": 1, "total": 20, "success": 15, "failed": 5,
            "failure_rate": 0.25, "avg_duration_ms": 200.5,
            "total_cost_usd": 0.05, "total_input_tokens": 0, "total_output_tokens": 0,
        }

        text = checker._format_alert_text(stats)

        assert "LLM 调用异常告警" in text
        assert "25.0%" in text
        assert "20" in text  # total
        assert "5" in text   # failed
