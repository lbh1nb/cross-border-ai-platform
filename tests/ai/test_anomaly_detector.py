"""异常检测器单元测试（v0.6.1 新增，08-18 任务②）。

覆盖：
- detect_anomalies: 销量跌幅检测、ACoS 过高检测、空数据兜底
- detect_inventory_anomalies: 库存紧急检测
- 辅助函数: _safe_float / _safe_int / _safe_str
"""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai.agents.anomaly_detector import (
    ACOS_HIGH_THRESHOLD,
    INVENTORY_CRITICAL_DAYS,
    SALES_DROP_THRESHOLD,
    _safe_float,
    _safe_int,
    _safe_str,
    detect_anomalies,
    detect_inventory_anomalies,
)


# ============ detect_anomalies 测试 ============
class TestDetectAnomalies:
    """销量异常检测测试。"""

    def test_no_anomaly_when_sales_stable(self) -> None:
        """销量平稳时不应检测到异常。"""
        current = [
            {"平台": "亚马逊", "销售额": 10000, "订单数": 100, "ACoS": 0.20},
        ]
        previous = [
            {"平台": "亚马逊", "销售额": 10000, "订单数": 100, "ACoS": 0.20},
        ]
        anomalies = detect_anomalies(current, previous)
        assert anomalies == []

    def test_sales_drop_detected_when_drop_exceeds_threshold(self) -> None:
        """销量跌幅超过 30% 应检测到异常。"""
        # 10000 -> 5000 跌幅 50%，>= 50% 应标记为 critical
        current = [{"平台": "亚马逊", "销售额": 5000, "订单数": 50, "ACoS": 0.20}]
        previous = [{"平台": "亚马逊", "销售额": 10000, "订单数": 100, "ACoS": 0.20}]
        anomalies = detect_anomalies(current, previous)
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "sales_drop"
        assert anomalies[0]["platform"] == "亚马逊"
        assert anomalies[0]["severity"] == "critical"  # 50% >= 50% 是 critical

    def test_sales_drop_warning_when_drop_between_30_and_50(self) -> None:
        """销量跌幅 30%-50% 应标记为 warning。"""
        current = [{"平台": "亚马逊", "销售额": 6500, "订单数": 65, "ACoS": 0.20}]
        previous = [{"平台": "亚马逊", "销售额": 10000, "订单数": 100, "ACoS": 0.20}]
        anomalies = detect_anomalies(current, previous)
        assert len(anomalies) == 1
        assert anomalies[0]["severity"] == "warning"

    def test_acos_high_detected_when_exceeds_threshold(self) -> None:
        """ACoS 超过 50% 应检测到异常。"""
        current = [{"平台": "沃尔玛", "销售额": 4000, "订单数": 40, "ACoS": 0.55}]
        previous = [{"平台": "沃尔玛", "销售额": 4000, "订单数": 40, "ACoS": 0.15}]
        anomalies = detect_anomalies(current, previous)
        # 应同时检测到 ACoS 过高（无销量下跌）
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "acos_high"

    def test_multiple_anomalies_in_one_call(self) -> None:
        """同一次调用应能检测到多个异常。"""
        current = [
            # 10000 -> 5000 跌幅 50%（critical）
            {"平台": "亚马逊", "销售额": 5000, "订单数": 50, "ACoS": 0.20},
            # ACoS=0.55 过高（warning）
            {"平台": "沃尔玛", "销售额": 4000, "订单数": 40, "ACoS": 0.55},
        ]
        previous = [
            {"平台": "亚马逊", "销售额": 10000, "订单数": 100, "ACoS": 0.20},
            {"平台": "沃尔玛", "销售额": 4000, "订单数": 40, "ACoS": 0.15},
        ]
        anomalies = detect_anomalies(current, previous)
        assert len(anomalies) == 2
        types = {a["type"] for a in anomalies}
        assert types == {"sales_drop", "acos_high"}

    def test_empty_current_returns_empty(self) -> None:
        """当天无数据应返回空列表。"""
        anomalies = detect_anomalies([], [{"平台": "亚马逊", "销售额": 10000}])
        assert anomalies == []

    def test_no_previous_data_skips_sales_drop(self) -> None:
        """无前一天数据时，跳过销量跌幅检测（只检测 ACoS）。"""
        current = [{"平台": "亚马逊", "销售额": 1000, "订单数": 10, "ACoS": 0.20}]
        anomalies = detect_anomalies(current, None)
        # 无前一天数据，但 ACoS=0.20 不超阈值，应无异常
        assert anomalies == []

    def test_threshold_boundary_30_pct(self) -> None:
        """跌幅正好 30% 应触发异常（>= 阈值）。"""
        # 10000 -> 7000 跌幅 30%
        current = [{"平台": "亚马逊", "销售额": 7000, "订单数": 70, "ACoS": 0.20}]
        previous = [{"平台": "亚马逊", "销售额": 10000, "订单数": 100, "ACoS": 0.20}]
        anomalies = detect_anomalies(current, previous)
        assert len(anomalies) == 1
        assert anomalies[0]["metric"]["drop_pct"] == pytest.approx(0.30, abs=0.001)

    def test_threshold_boundary_29_pct_no_alert(self) -> None:
        """跌幅 29% 不应触发异常（< 阈值）。"""
        # 10000 -> 7100 跌幅 29%
        current = [{"平台": "亚马逊", "销售额": 7100, "订单数": 71, "ACoS": 0.20}]
        previous = [{"平台": "亚马逊", "销售额": 10000, "订单数": 100, "ACoS": 0.20}]
        anomalies = detect_anomalies(current, previous)
        assert anomalies == []

    def test_platform_missing_skipped(self) -> None:
        """平台字段为空的记录应被跳过。"""
        current = [{"平台": "", "销售额": 1000, "订单数": 10, "ACoS": 0.60}]
        anomalies = detect_anomalies(current, [])
        assert anomalies == []

    def test_anomaly_structure_complete(self) -> None:
        """异常结构应包含所有必需字段。"""
        current = [{"平台": "亚马逊", "销售额": 5000, "订单数": 50, "ACoS": 0.55}]
        previous = [{"平台": "亚马逊", "销售额": 10000, "订单数": 100, "ACoS": 0.20}]
        anomalies = detect_anomalies(current, previous)
        assert len(anomalies) == 2
        for a in anomalies:
            assert "type" in a
            assert "platform" in a
            assert "detail" in a
            assert "severity" in a
            assert "metric" in a

    def test_feishu_list_format_platform(self) -> None:
        """飞书单选字段返回 [{"text": "..."}] 格式应能正确解析。"""
        current = [
            {"平台": [{"text": "亚马逊"}], "销售额": 5000, "订单数": 50, "ACoS": 0.20},
        ]
        previous = [
            {"平台": [{"text": "亚马逊"}], "销售额": 10000, "订单数": 100, "ACoS": 0.20},
        ]
        anomalies = detect_anomalies(current, previous)
        assert len(anomalies) == 1
        assert anomalies[0]["platform"] == "亚马逊"


# ============ detect_inventory_anomalies 测试 ============
class TestDetectInventoryAnomalies:
    """库存异常检测测试。"""

    def test_critical_when_days_below_threshold(self) -> None:
        """可售天数 ≤ 7 应检测为 critical。"""
        records = [{"平台": "亚马逊", "ASIN": "B12345", "可售天数": 5}]
        anomalies = detect_inventory_anomalies(records)
        assert len(anomalies) == 1
        assert anomalies[0]["type"] == "inventory_critical"
        assert anomalies[0]["severity"] == "critical"

    def test_no_anomaly_when_days_above_threshold(self) -> None:
        """可售天数 > 7 不应检测到异常。"""
        records = [{"平台": "亚马逊", "ASIN": "B12345", "可售天数": 30}]
        anomalies = detect_inventory_anomalies(records)
        assert anomalies == []

    def test_boundary_7_days_triggers(self) -> None:
        """可售天数正好 7 天应触发异常。"""
        records = [{"平台": "亚马逊", "ASIN": "B12345", "可售天数": 7}]
        anomalies = detect_inventory_anomalies(records)
        assert len(anomalies) == 1

    def test_empty_records_returns_empty(self) -> None:
        """空列表应返回空。"""
        assert detect_inventory_anomalies([]) == []


# ============ 辅助函数测试 ============
class TestSafeHelpers:
    """辅助函数测试。"""

    def test_safe_float_normal(self) -> None:
        assert _safe_float(3.14) == 3.14
        assert _safe_float("2.5") == 2.5
        assert _safe_float(10) == 10.0

    def test_safe_float_invalid(self) -> None:
        assert _safe_float(None) == 0.0
        assert _safe_float("abc") == 0.0
        assert _safe_float([]) == 0.0

    def test_safe_int_normal(self) -> None:
        assert _safe_int(42) == 42
        assert _safe_int("100") == 100
        assert _safe_int(3.7) == 3  # 截断小数

    def test_safe_int_invalid(self) -> None:
        assert _safe_int(None) == 0
        assert _safe_int("abc") == 0

    def test_safe_str_normal(self) -> None:
        assert _safe_str("hello") == "hello"
        assert _safe_str(123) == "123"

    def test_safe_str_feishu_list_format(self) -> None:
        """飞书单选格式 [{"text": "..."}] 应能正确提取。"""
        assert _safe_str([{"text": "亚马逊"}]) == "亚马逊"
        assert _safe_str([{"name": "沃尔玛"}]) == "沃尔玛"

    def test_safe_str_none(self) -> None:
        assert _safe_str(None) == ""

    def test_safe_str_dict(self) -> None:
        assert _safe_str({"text": "Wayfair"}) == "Wayfair"


# ============ 阈值常量测试 ============
class TestThresholdConstants:
    """阈值常量应符合业务规则。"""

    def test_sales_drop_threshold(self) -> None:
        assert SALES_DROP_THRESHOLD == 0.30

    def test_acos_high_threshold(self) -> None:
        assert ACOS_HIGH_THRESHOLD == 0.50

    def test_inventory_critical_days(self) -> None:
        assert INVENTORY_CRITICAL_DAYS == 7
