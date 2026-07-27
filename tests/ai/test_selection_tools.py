"""选品 Agent 工具集单元测试：测试 fetch_products、analyze_products、save_report。

mock 策略：
- fetch_products：使用真实的 MockAmazonCollector（本身就是模拟数据，无网络请求）
- analyze_products：mock ModelRouter 和 PromptManager，避免真实 LLM 调用
- save_report：mock bitable_client 和 application_bot，避免飞书 API 调用
"""

from __future__ import annotations

import json
from unittest.mock import MagicMock, patch

import pytest

from src.ai.agents.selection_tools import (
    fetch_products,
    analyze_products,
    save_report,
)


class TestFetchProducts:
    """fetch_products 工具测试。"""

    def test_fetch_returns_valid_json(self) -> None:
        """抓取商品应返回合法 JSON 数组。"""
        result = fetch_products.invoke({"category": "家居收纳", "limit": 5})

        products = json.loads(result)
        assert isinstance(products, list)
        assert len(products) == 5

    def test_fetch_product_fields_complete(self) -> None:
        """每个商品应包含完整字段。"""
        result = fetch_products.invoke({"category": "厨房用品", "limit": 3})

        products = json.loads(result)
        required_fields = {
            "asin", "name", "category", "price_range",
            "rating", "review_count", "bsr_rank",
            "market_capacity", "competition_level", "profit_margin",
        }
        for p in products:
            assert required_fields.issubset(p.keys()), f"缺少字段: {required_fields - set(p.keys())}"

    def test_fetch_unknown_category_uses_default(self) -> None:
        """未知品类应使用默认品类数据（不抛异常）。"""
        result = fetch_products.invoke({"category": "不存在的品类", "limit": 2})

        products = json.loads(result)
        assert len(products) == 2

    def test_fetch_default_limit(self) -> None:
        """不传 limit 时使用默认值 10。"""
        result = fetch_products.invoke({"category": "家居收纳"})

        products = json.loads(result)
        assert len(products) == 10


class TestAnalyzeProducts:
    """analyze_products 工具测试。"""

    def test_analyze_with_mock_llm(self) -> None:
        """mock LLM 后应返回分析结果。"""
        # 准备商品数据
        products_json = json.dumps([
            {
                "asin": "B0TEST1", "name": "测试商品1", "category": "家居收纳",
                "price_range": "$15-$25", "rating": 4.5, "review_count": 500,
                "bsr_rank": 1000, "market_capacity": "中",
                "competition_level": "中等", "profit_margin": "高",
            }
        ])

        # mock LLM 响应
        mock_response = MagicMock()
        mock_response.content = json.dumps({
            "category": "家居收纳",
            "market_capacity": "中",
            "competition_level": "中等",
            "profit_potential": "高",
            "top_picks": [
                {
                    "asin": "B0TEST1", "name": "测试商品1",
                    "reason": "评分高评论多", "estimated_margin": "高",
                }
            ],
            "summary": "测试分析结果",
        })

        mock_llm = MagicMock()
        mock_llm.invoke.return_value = mock_response

        mock_router = MagicMock()
        mock_router.get_llm.return_value = mock_llm

        with patch(
            "src.ai.agents.selection_tools.get_model_router",
            return_value=mock_router,
        ):
            result = analyze_products.invoke({
                "category": "家居收纳",
                "products_json": products_json,
            })

        # 验证 LLM 被调用
        assert mock_llm.invoke.called
        # 验证返回的是 LLM 的内容
        parsed = json.loads(result)
        assert parsed["category"] == "家居收纳"
        assert len(parsed["top_picks"]) == 1

    def test_analyze_invalid_json_returns_error(self) -> None:
        """传入非法 JSON 应返回错误信息（不抛异常）。"""
        result = analyze_products.invoke({
            "category": "家居收纳",
            "products_json": "{invalid json}",
        })

        parsed = json.loads(result)
        assert "error" in parsed


class TestSaveReport:
    """save_report 工具测试。"""

    def test_save_with_table_id(self) -> None:
        """配置了 table_id 时应写入多维表格。"""
        analysis_json = json.dumps({
            "category": "家居收纳",
            "market_capacity": "中",
            "competition_level": "中等",
            "top_picks": [
                {
                    "asin": "B0TEST1", "name": "测试商品1",
                    "reason": "评分高", "estimated_margin": "高",
                }
            ],
            "summary": "测试总结",
        })

        with patch(
            "src.ai.agents.selection_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.selection_tools.application_bot"
        ) as mock_bot, patch(
            "src.ai.agents.selection_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_selection = "tblTest123"
            mock_bitable.create_record.return_value = {"record_id": "rec123"}
            mock_bot.send_text.return_value = True

            result = save_report.invoke({
                "analysis_json": analysis_json,
                "push_to_feishu": True,
            })

        parsed = json.loads(result)
        assert parsed["saved_records"] == 1
        assert parsed["pushed_to_feishu"] is True

    def test_save_without_table_id_skips_bitable(self) -> None:
        """未配置 table_id 时跳过多维表格写入。"""
        analysis_json = json.dumps({
            "category": "家居收纳",
            "top_picks": [],
            "summary": "无推荐",
        })

        with patch(
            "src.ai.agents.selection_tools.bitable_client"
        ) as mock_bitable, patch(
            "src.ai.agents.selection_tools.application_bot"
        ) as mock_bot, patch(
            "src.ai.agents.selection_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_selection = ""
            mock_bot.send_text.return_value = True

            result = save_report.invoke({
                "analysis_json": analysis_json,
                "push_to_feishu": True,
            })

        parsed = json.loads(result)
        assert parsed["saved_records"] == 0
        mock_bitable.create_record.assert_not_called()

    def test_save_without_feishu_push(self) -> None:
        """push_to_feishu=False 时不推送飞书。"""
        analysis_json = json.dumps({
            "category": "家居收纳",
            "top_picks": [],
            "summary": "测试",
        })

        with patch(
            "src.ai.agents.selection_tools.bitable_client"
        ), patch(
            "src.ai.agents.selection_tools.application_bot"
        ) as mock_bot, patch(
            "src.ai.agents.selection_tools.settings"
        ) as mock_settings:
            mock_settings.feishu_table_id_selection = ""

            result = save_report.invoke({
                "analysis_json": analysis_json,
                "push_to_feishu": False,
            })

        parsed = json.loads(result)
        assert parsed["pushed_to_feishu"] is False
        mock_bot.send_text.assert_not_called()

    def test_save_invalid_json_returns_error(self) -> None:
        """传入非法 JSON 应返回错误信息。"""
        with patch(
            "src.ai.agents.selection_tools.bitable_client"
        ), patch(
            "src.ai.agents.selection_tools.application_bot"
        ):
            result = save_report.invoke({
                "analysis_json": "{invalid}",
                "push_to_feishu": False,
            })

        parsed = json.loads(result)
        assert "error" in parsed
