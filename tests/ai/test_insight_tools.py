"""数据洞察 Agent 工具集单元测试：测试 fetch_daily_data、analyze_daily_data、save_insight_report。

mock 策略：
- fetch_daily_data：mock bitable_client，避免真实飞书 API 调用
- analyze_daily_data：mock ModelRouter 和 PromptManager，避免真实 LLM 调用
- save_insight_report：mock bitable_client 和 application_bot，避免飞书 API 调用
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

import pytest

from src.ai.agents.insight_tools import (
    _build_table_insight,
    _extract_field_value,
    _extract_json,
    _normalize_date,
    analyze_daily_data,
    fetch_daily_data,
    save_insight_report,
)


# ============================================================
# 辅助函数测试
# ============================================================


class TestNormalizeDate:
    """_normalize_date 日期归一化测试。"""

    def test_empty_returns_yesterday(self) -> None:
        """空字符串应返回昨天的日期。"""
        result = _normalize_date("")
        expected = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
        assert result == expected

    def test_iso_format_passed_through(self) -> None:
        """YYYY-MM-DD 格式应原样返回。"""
        result = _normalize_date("2026-07-27")
        assert result == "2026-07-27"

    def test_invalid_format_returned_as_is(self) -> None:
        """无法解析的格式应原样返回。"""
        result = _normalize_date("not-a-date")
        assert result == "not-a-date"


class TestExtractFieldValue:
    """_extract_field_value 飞书字段值提取测试。"""

    def test_none_returns_empty(self) -> None:
        assert _extract_field_value(None) == ""

    def test_int_passed_through(self) -> None:
        assert _extract_field_value(123) == 123

    def test_float_passed_through(self) -> None:
        assert _extract_field_value(45.6) == 45.6

    def test_str_passed_through(self) -> None:
        assert _extract_field_value("hello") == "hello"

    def test_list_with_text_dict(self) -> None:
        field = [{"text": "内容", "type": "text"}]
        assert _extract_field_value(field) == "内容"

    def test_list_with_name_dict(self) -> None:
        field = [{"name": "选项A"}]
        assert _extract_field_value(field) == "选项A"

    def test_dict_with_name(self) -> None:
        field = {"name": "正常"}
        assert _extract_field_value(field) == "正常"

    def test_dict_with_text(self) -> None:
        field = {"text": "内容"}
        assert _extract_field_value(field) == "内容"


class TestExtractJson:
    """_extract_json JSON 提取测试。"""

    def test_plain_json(self) -> None:
        text = '{"a": 1}'
        assert _extract_json(text) == '{"a": 1}'

    def test_json_in_code_block(self) -> None:
        text = '```json\n{"a": 1}\n```'
        assert _extract_json(text) == '{"a": 1}'

    def test_json_in_plain_code_block(self) -> None:
        text = '```\n{"a": 1}\n```'
        assert _extract_json(text) == '{"a": 1}'

    def test_json_embedded_in_text(self) -> None:
        text = '分析结果如下：\n{"a": 1, "b": 2}\n请查看。'
        result = _extract_json(text)
        assert result is not None
        assert '"a": 1' in result

    def test_no_json_returns_none(self) -> None:
        assert _extract_json("纯文本无JSON") is None


class TestBuildTableInsight:
    """_build_table_insight 表格洞察文本构建测试。"""

    def test_full_analysis(self) -> None:
        """完整分析应拼接所有字段。"""
        analysis = {
            "sales_insight": {"summary": "销量上升"},
            "ad_insight": {"acos_eval": "ACoS 偏高"},
            "inventory_insight": {"health": "预警"},
            "top_priority": "补货 SKU-A",
        }
        result = _build_table_insight(analysis)
        assert "销量" in result
        assert "广告" in result
        assert "库存" in result
        assert "优先" in result

    def test_empty_analysis(self) -> None:
        """空分析应返回默认文本。"""
        result = _build_table_insight({})
        assert result == "AI 洞察生成中"

    def test_partial_analysis(self) -> None:
        """部分字段缺失时只拼接存在的字段。"""
        analysis = {
            "sales_insight": {"summary": "销量平稳"},
            "ad_insight": {},
            "inventory_insight": {},
            "top_priority": "",
        }
        result = _build_table_insight(analysis)
        assert "销量" in result
        assert "广告" not in result
        assert "库存" not in result


# ============================================================
# fetch_daily_data 工具测试
# ============================================================


class TestFetchDailyData:
    """fetch_daily_data 工具测试。"""

    def test_fetch_with_empty_date_uses_yesterday(self) -> None:
        """target_date 留空时应查询昨天的数据。"""
        yesterday = (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")

        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = "tblSales123"
            mock_settings.feishu_table_id_inventory = "tblInv456"
            # v0.6.1：query_records 调用 3 次（当天/前一天/库存）
            mock_bitable.query_records.return_value = []

            result = fetch_daily_data.invoke({"target_date": ""})

        parsed = json.loads(result)
        assert parsed["date"] == yesterday
        assert parsed["sales_count"] == 0
        assert parsed["inventory_alert_count"] == 0
        mock_bitable.query_records.assert_called()

    def test_fetch_with_specific_date(self) -> None:
        """传入指定日期时应查询该日期的数据。"""
        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = "tblSales123"
            mock_settings.feishu_table_id_inventory = "tblInv456"
            mock_bitable.query_records.return_value = []

            result = fetch_daily_data.invoke({"target_date": "2026-07-27"})

        parsed = json.loads(result)
        assert parsed["date"] == "2026-07-27"

    def test_fetch_with_sales_records(self) -> None:
        """销售日报表有数据时应正确解析。"""
        mock_sales_records = [
            {
                "record_id": "rec1",
                "fields": {
                    "平台": [{"text": "亚马逊", "type": "text"}],
                    "销售额": 1234.56,
                    "订单数": 50,
                    "广告花费": 200.0,
                    "ACoS": 16.2,
                    "退货数": 2,
                    "库存天数": 30,
                    "异常标记": "",
                },
            }
        ]

        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = "tblSales123"
            mock_settings.feishu_table_id_inventory = "tblInv456"

            # v0.6.1 调用顺序：当天销售 → 前一天销售 → 库存预警
            mock_bitable.query_records.side_effect = [
                mock_sales_records,  # 当天销售
                [],                  # 前一天销售（空）
                [],                  # 库存预警（空）
            ]

            result = fetch_daily_data.invoke({"target_date": "2026-07-27"})

        parsed = json.loads(result)
        assert parsed["sales_count"] == 1
        assert parsed["inventory_alert_count"] == 0
        # v0.6.1 新增字段
        assert "previous_sales_records" in parsed
        assert "anomalies" in parsed
        # 验证字段提取
        sales = parsed["sales_records"][0]
        assert sales["平台"] == "亚马逊"
        assert sales["销售额"] == 1234.56
        assert sales["订单数"] == 50

    def test_fetch_with_inventory_alerts(self) -> None:
        """库存预警表有数据时应正确解析。"""
        mock_inventory_records = [
            {
                "record_id": "rec1",
                "fields": {
                    "ASIN": "B08TEST",
                    "商品名称": [{"text": "测试商品", "type": "text"}],
                    "SKU": "SKU-001",
                    "平台": [{"text": "亚马逊", "type": "text"}],
                    "当前库存": 10,
                    "日均销量": 5.0,
                    "可售天数": 2,
                    "预警等级": {"name": "紧急"},
                    "建议采购量": 100,
                },
            }
        ]

        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = "tblSales123"
            mock_settings.feishu_table_id_inventory = "tblInv456"

            # v0.6.1 调用顺序：当天销售 → 前一天销售 → 库存预警
            mock_bitable.query_records.side_effect = [
                [],                    # 当天销售（空）
                [],                    # 前一天销售（空）
                mock_inventory_records,  # 库存预警
            ]

            result = fetch_daily_data.invoke({"target_date": "2026-07-27"})

        parsed = json.loads(result)
        assert parsed["sales_count"] == 0
        assert parsed["inventory_alert_count"] == 1
        # 验证字段提取
        inv = parsed["inventory_records"][0]
        assert inv["ASIN"] == "B08TEST"
        assert inv["商品名称"] == "测试商品"
        assert inv["预警等级"] == "紧急"

    def test_fetch_without_table_ids(self) -> None:
        """未配置表 ID 时应正常返回（空数据 + warning 日志）。"""
        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = ""
            mock_settings.feishu_table_id_inventory = ""

            result = fetch_daily_data.invoke({"target_date": "2026-07-27"})

        parsed = json.loads(result)
        assert parsed["sales_count"] == 0
        assert parsed["inventory_alert_count"] == 0
        mock_bitable.query_records.assert_not_called()

    def test_fetch_handles_bitable_exception(self) -> None:
        """bitable_client 抛异常时应返回 error 字段。"""
        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = "tblSales123"
            mock_settings.feishu_table_id_inventory = "tblInv456"
            mock_bitable.query_records.side_effect = RuntimeError("飞书 API 限流")

            result = fetch_daily_data.invoke({"target_date": "2026-07-27"})

        parsed = json.loads(result)
        assert "error" in parsed
        assert "飞书 API 限流" in parsed["error"]


# ============================================================
# analyze_daily_data 工具测试
# ============================================================


class TestAnalyzeDailyData:
    """analyze_daily_data 工具测试。"""

    def test_analyze_with_mock_llm_returns_json(self) -> None:
        """mock LLM 返回合法 JSON 时应正确解析。"""
        data_json = json.dumps({
            "date": "2026-07-27",
            "sales_records": [
                {"平台": "亚马逊", "销售额": 1000.0, "订单数": 30}
            ],
            "inventory_records": [],
        })

        # mock LLM 响应（带 ```json 包裹）
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "date": "2026-07-27",
            "sales_insight": {
                "summary": "销量平稳",
                "trend": "平稳",
                "anomaly": "",
            },
            "ad_insight": {
                "acos_eval": "ACoS 正常",
                "efficiency": "正常",
            },
            "inventory_insight": {
                "health": "健康",
                "suggestion": "无需补货",
                "risk_items": [],
            },
            "top_priority": "无紧急事项",
            "action_items": ["继续观察销量趋势"],
        })

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        mock_router = MagicMock()
        mock_router.get_llm.return_value = mock_llm

        mock_pm = MagicMock()
        mock_prompt = MagicMock()
        mock_prompt.format_messages.return_value = []
        mock_pm.get_prompt.return_value = mock_prompt

        with patch(
            "src.ai.agents.insight_tools.get_model_router",
            return_value=mock_router,
        ), patch(
            "src.ai.agents.insight_tools.get_prompt_manager",
            return_value=mock_pm,
        ):
            result = analyze_daily_data.invoke({"data_json": data_json})

        parsed = json.loads(result)
        assert parsed["date"] == "2026-07-27"
        assert "analysis" in parsed
        assert parsed["analysis"]["sales_insight"]["trend"] == "平稳"
        assert parsed["analysis"]["ad_insight"]["efficiency"] == "正常"
        assert parsed["analysis"]["inventory_insight"]["health"] == "健康"
        assert mock_llm.invoke.called

    def test_analyze_invalid_json_returns_error(self) -> None:
        """传入非法 JSON 应返回错误信息（不抛异常）。"""
        result = analyze_daily_data.invoke({"data_json": "{invalid json}"})

        parsed = json.loads(result)
        assert "error" in parsed

    def test_analyze_llm_returns_non_json_uses_fallback(self) -> None:
        """LLM 返回非 JSON 文本时应使用兜底结构。"""
        data_json = json.dumps({
            "date": "2026-07-27",
            "sales_records": [],
            "inventory_records": [],
        })

        # mock LLM 返回纯文本（无 JSON）
        mock_response = MagicMock()
        mock_response.content = "这是一段纯文本分析，无 JSON 结构。"

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        mock_router = MagicMock()
        mock_router.get_llm.return_value = mock_llm

        mock_pm = MagicMock()
        mock_prompt = MagicMock()
        mock_prompt.format_messages.return_value = []
        mock_pm.get_prompt.return_value = mock_prompt

        with patch(
            "src.ai.agents.insight_tools.get_model_router",
            return_value=mock_router,
        ), patch(
            "src.ai.agents.insight_tools.get_prompt_manager",
            return_value=mock_pm,
        ):
            result = analyze_daily_data.invoke({"data_json": data_json})

        parsed = json.loads(result)
        assert "analysis" in parsed
        # 兜底结构应包含 sales_insight 字段
        assert "sales_insight" in parsed["analysis"]
        assert "top_priority" in parsed["analysis"]


# ============================================================
# save_insight_report 工具测试
# ============================================================


class TestSaveInsightReport:
    """save_insight_report 工具测试。"""

    def test_save_with_table_id_updates_records(self) -> None:
        """配置了 table_id 时应更新多维表格的 AI 洞察字段。"""
        analysis_json = json.dumps({
            "date": "2026-07-27",
            "analysis": {
                "sales_insight": {"summary": "销量上升"},
                "ad_insight": {"acos_eval": "ACoS 正常"},
                "inventory_insight": {"health": "健康"},
                "top_priority": "无紧急事项",
            },
        })

        # mock 已有的销售日报记录
        mock_records = [
            {"record_id": "rec1", "fields": {}},
            {"record_id": "rec2", "fields": {}},
        ]

        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.insight_tools.application_bot"
        ) as mock_bot, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = "tblSales123"
            mock_bitable.query_records.return_value = mock_records
            mock_bitable.update_record.return_value = "rec1"
            mock_bot.send_card.return_value = True

            result = save_insight_report.invoke({
                "analysis_json": analysis_json,
                "push_to_feishu": True,
            })

        parsed = json.loads(result)
        assert parsed["updated_records"] == 2
        assert parsed["pushed_to_feishu"] is True
        # 验证 update_record 被调用 2 次
        assert mock_bitable.update_record.call_count == 2
        # 验证 send_card 被调用 1 次
        mock_bot.send_card.assert_called_once()

    def test_save_without_table_id_skips_update(self) -> None:
        """未配置 table_id 时跳过多维表格写入。"""
        analysis_json = json.dumps({
            "date": "2026-07-27",
            "analysis": {
                "sales_insight": {"summary": "销量平稳"},
            },
        })

        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.insight_tools.application_bot"
        ) as mock_bot, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = ""
            mock_bot.send_card.return_value = True

            result = save_insight_report.invoke({
                "analysis_json": analysis_json,
                "push_to_feishu": True,
            })

        parsed = json.loads(result)
        assert parsed["updated_records"] == 0
        mock_bitable.query_records.assert_not_called()
        mock_bitable.update_record.assert_not_called()

    def test_save_without_feishu_push(self) -> None:
        """push_to_feishu=False 时不推送飞书。"""
        analysis_json = json.dumps({
            "date": "2026-07-27",
            "analysis": {
                "sales_insight": {"summary": "销量平稳"},
            },
        })

        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ), patch(
            "src.ai.agents.insight_tools.application_bot"
        ) as mock_bot, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = ""

            result = save_insight_report.invoke({
                "analysis_json": analysis_json,
                "push_to_feishu": False,
            })

        parsed = json.loads(result)
        assert parsed["pushed_to_feishu"] is False
        mock_bot.send_card.assert_not_called()

    def test_save_invalid_json_returns_error(self) -> None:
        """传入非法 JSON 应返回错误信息。"""
        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ), patch(
            "src.ai.agents.insight_tools.application_bot"
        ):
            result = save_insight_report.invoke({
                "analysis_json": "{invalid}",
                "push_to_feishu": False,
            })

        parsed = json.loads(result)
        assert "error" in parsed

    def test_save_push_failure_does_not_block_update(self) -> None:
        """推送卡片失败不应影响表格更新结果。"""
        analysis_json = json.dumps({
            "date": "2026-07-27",
            "analysis": {
                "sales_insight": {"summary": "销量上升"},
            },
        })

        mock_records = [{"record_id": "rec1", "fields": {}}]

        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.insight_tools.application_bot"
        ) as mock_bot, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = "tblSales123"
            mock_bitable.query_records.return_value = mock_records
            mock_bitable.update_record.return_value = "rec1"
            # 推送卡片抛异常
            mock_bot.send_card.side_effect = RuntimeError("飞书群不存在")

            result = save_insight_report.invoke({
                "analysis_json": analysis_json,
                "push_to_feishu": True,
            })

        parsed = json.loads(result)
        # 表格更新应成功
        assert parsed["updated_records"] == 1
        # 推送应失败
        assert parsed["pushed_to_feishu"] is False

    def test_save_update_record_failure_continues(self) -> None:
        """单条记录更新失败不应影响其他记录。"""
        analysis_json = json.dumps({
            "date": "2026-07-27",
            "analysis": {
                "sales_insight": {"summary": "销量上升"},
            },
        })

        mock_records = [
            {"record_id": "rec1", "fields": {}},
            {"record_id": "rec2", "fields": {}},
            {"record_id": "rec3", "fields": {}},
        ]

        with patch(
            "src.ai.agents.insight_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.insight_tools.application_bot"
        ) as mock_bot, patch(
            "src.ai.agents.insight_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_daily_report = "tblSales123"
            mock_bitable.query_records.return_value = mock_records
            # 第二条更新失败
            mock_bitable.update_record.side_effect = [
                "rec1",
                RuntimeError("权限不足"),
                "rec3",
            ]
            mock_bot.send_card.return_value = True

            result = save_insight_report.invoke({
                "analysis_json": analysis_json,
                "push_to_feishu": True,
            })

        parsed = json.loads(result)
        # 应只成功 2 条
        assert parsed["updated_records"] == 2
        assert parsed["pushed_to_feishu"] is True
