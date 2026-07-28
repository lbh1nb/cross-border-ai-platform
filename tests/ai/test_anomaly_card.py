"""异常预警卡片模板测试（v0.6.1 新增，08-18 任务②）。

覆盖 build_anomaly_alert_card 的结构和内容生成。
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.feishu.card_templates import build_anomaly_alert_card


class TestBuildAnomalyAlertCard:
    """异常预警卡片测试。"""

    def test_card_uses_red_template(self) -> None:
        """异常预警卡片应使用红色模板（强调严重性）。"""
        anomalies = [
            {"type": "sales_drop", "platform": "亚马逊", "detail": "销量下跌 50%",
             "severity": "critical", "metric": {}},
        ]
        card = build_anomaly_alert_card("2026-07-28", anomalies)
        assert card["header"]["template"] == "red"

    def test_card_title_contains_date_and_count(self) -> None:
        """卡片标题应包含日期和异常数量。"""
        anomalies = [
            {"type": "sales_drop", "platform": "亚马逊", "detail": "测试",
             "severity": "warning", "metric": {}},
        ]
        card = build_anomaly_alert_card("2026-07-28", anomalies)
        title = card["header"]["title"]["content"]
        assert "2026-07-28" in title
        assert "1" in title

    def test_critical_anomalies_sorted_first(self) -> None:
        """critical 异常应排在 warning 之前。"""
        anomalies = [
            {"type": "acos_high", "platform": "沃尔玛", "detail": "ACoS 高",
             "severity": "warning", "metric": {}},
            {"type": "sales_drop", "platform": "亚马逊", "detail": "销量跌",
             "severity": "critical", "metric": {}},
        ]
        card = build_anomaly_alert_card("2026-07-28", anomalies)
        # 找到异常详情文本
        detail_div = next(
            e for e in card["elements"]
            if e.get("tag") == "div" and "异常详情" in e.get("text", {}).get("content", "")
        )
        content = detail_div["text"]["content"]
        # critical 应该在 warning 前面
        critical_pos = content.find("销量跌")
        warning_pos = content.find("ACoS 高")
        assert critical_pos < warning_pos

    def test_stats_fields_correct(self) -> None:
        """统计字段应正确显示 critical 和 warning 数量。"""
        anomalies = [
            {"type": "sales_drop", "platform": "亚马逊", "detail": "跌",
             "severity": "critical", "metric": {}},
            {"type": "sales_drop", "platform": "沃尔玛", "detail": "跌",
             "severity": "critical", "metric": {}},
            {"type": "acos_high", "platform": "Wayfair", "detail": "高",
             "severity": "warning", "metric": {}},
        ]
        card = build_anomaly_alert_card("2026-07-28", anomalies)
        # 找到含"严重异常"的字段
        fields_div = next(
            e for e in card["elements"] if e.get("tag") == "div" and "fields" in e
        )
        fields_content = [
            f["text"]["content"] for f in fields_div["fields"]
        ]
        content_str = " ".join(fields_content)
        assert "2" in content_str  # critical count
        assert "1" in content_str  # warning count
        assert "3" in content_str  # total

    def test_button_added_when_table_url_provided(self) -> None:
        """提供 table_url 时应添加查看按钮。"""
        anomalies = [
            {"type": "sales_drop", "platform": "亚马逊", "detail": "跌",
             "severity": "warning", "metric": {}},
        ]
        card = build_anomaly_alert_card(
            "2026-07-28", anomalies, table_url="https://example.com"
        )
        # 最后一个元素应该是 action
        action_elem = next(
            (e for e in card["elements"] if e.get("tag") == "action"), None
        )
        assert action_elem is not None
        button = action_elem["actions"][0]
        assert button["url"] == "https://example.com"
        assert button["type"] == "danger"  # 红色危险按钮

    def test_no_button_when_table_url_empty(self) -> None:
        """未提供 table_url 时不应有按钮。"""
        anomalies = [
            {"type": "sales_drop", "platform": "亚马逊", "detail": "跌",
             "severity": "warning", "metric": {}},
        ]
        card = build_anomaly_alert_card("2026-07-28", anomalies)
        action_elem = next(
            (e for e in card["elements"] if e.get("tag") == "action"), None
        )
        assert action_elem is None

    def test_empty_anomalies_still_generates_card(self) -> None:
        """空异常列表也应能生成卡片（不会崩溃）。"""
        card = build_anomaly_alert_card("2026-07-28", [])
        assert card["header"]["template"] == "red"
        # 应显示"无异常详情"
        detail_div = next(
            e for e in card["elements"]
            if e.get("tag") == "div" and "异常详情" in e.get("text", {}).get("content", "")
        )
        assert "无异常详情" in detail_div["text"]["content"]

    def test_severity_icon_mapping(self) -> None:
        """critical 用 🔴，warning 用 🟡。"""
        anomalies = [
            {"type": "t1", "platform": "p1", "detail": "d1",
             "severity": "critical", "metric": {}},
            {"type": "t2", "platform": "p2", "detail": "d2",
             "severity": "warning", "metric": {}},
        ]
        card = build_anomaly_alert_card("2026-07-28", anomalies)
        detail_div = next(
            e for e in card["elements"]
            if e.get("tag") == "div" and "异常详情" in e.get("text", {}).get("content", "")
        )
        content = detail_div["text"]["content"]
        assert "🔴" in content
        assert "🟡" in content

    def test_wide_screen_mode_enabled(self) -> None:
        """卡片应启用宽屏模式。"""
        card = build_anomaly_alert_card("2026-07-28", [])
        assert card["config"]["wide_screen_mode"] is True
