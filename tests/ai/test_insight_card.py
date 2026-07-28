"""数据洞察日报卡片模板单元测试。

测试 build_ai_insight_card 函数生成的飞书卡片 JSON 结构。
"""

from __future__ import annotations

from src.feishu.card_templates import build_ai_insight_card


class TestBuildAiInsightCard:
    """build_ai_insight_card 卡片模板测试。"""

    def test_basic_card_structure(self) -> None:
        """基本结构应包含 config、header、elements。"""
        analysis = {
            "sales_insight": {"trend": "上升", "summary": "销量增长 15%"},
            "ad_insight": {"efficiency": "正常", "acos_eval": "ACoS 18%"},
            "inventory_insight": {"health": "健康", "suggestion": "库存充足"},
        }
        card = build_ai_insight_card("2026-07-27", analysis)

        assert "config" in card
        assert "header" in card
        assert "elements" in card
        assert card["config"]["wide_screen_mode"] is True

    def test_header_contains_date(self) -> None:
        """标题应包含日期。"""
        card = build_ai_insight_card("2026-07-27", {})
        title = card["header"]["title"]["content"]
        assert "2026-07-27" in title
        assert "数据洞察日报" in title

    def test_header_template_is_blue(self) -> None:
        """标题颜色模板应为 blue（普通通知）。"""
        card = build_ai_insight_card("2026-07-27", {})
        assert card["header"]["template"] == "blue"

    def test_trend_color_mapping(self) -> None:
        """销量趋势颜色应正确映射（上升=green）。"""
        analysis = {
            "sales_insight": {"trend": "上升"},
            "ad_insight": {"efficiency": "高效"},
            "inventory_insight": {"health": "健康"},
        }
        card = build_ai_insight_card("2026-07-27", analysis)
        # 第一项是三维度概览的 div
        overview_div = card["elements"][0]
        fields = overview_div["fields"]
        # 销量趋势应包含 green 颜色
        sales_content = fields[0]["text"]["content"]
        assert "green" in sales_content
        assert "上升" in sales_content

    def test_efficiency_color_mapping(self) -> None:
        """广告效率颜色应正确映射（低效=red）。"""
        analysis = {
            "sales_insight": {"trend": "平稳"},
            "ad_insight": {"efficiency": "低效"},
            "inventory_insight": {"health": "健康"},
        }
        card = build_ai_insight_card("2026-07-27", analysis)
        overview_div = card["elements"][0]
        fields = overview_div["fields"]
        ad_content = fields[1]["text"]["content"]
        assert "red" in ad_content
        assert "低效" in ad_content

    def test_health_color_mapping(self) -> None:
        """库存健康颜色应正确映射（紧急=red）。"""
        analysis = {
            "sales_insight": {"trend": "平稳"},
            "ad_insight": {"efficiency": "正常"},
            "inventory_insight": {"health": "紧急"},
        }
        card = build_ai_insight_card("2026-07-27", analysis)
        overview_div = card["elements"][0]
        fields = overview_div["fields"]
        inv_content = fields[2]["text"]["content"]
        assert "red" in inv_content
        assert "紧急" in inv_content

    def test_sales_summary_displayed(self) -> None:
        """销量 summary 应展示在卡片中。"""
        analysis = {
            "sales_insight": {"summary": "销量较昨日上升 15%"},
        }
        card = build_ai_insight_card("2026-07-27", analysis)
        elements_text = str(card["elements"])
        assert "销量较昨日上升 15%" in elements_text

    def test_anomaly_displayed(self) -> None:
        """销量异常应展示在异常预警区。"""
        analysis = {
            "sales_insight": {"anomaly": "亚马逊销量下降 30%"},
            "inventory_insight": {"risk_items": ["SKU-A 断货"]},
        }
        card = build_ai_insight_card("2026-07-27", analysis)
        elements_text = str(card["elements"])
        assert "亚马逊销量下降 30%" in elements_text
        assert "SKU-A 断货" in elements_text

    def test_top_priority_displayed(self) -> None:
        """top_priority 应展示在「今日最紧急」区。"""
        analysis = {
            "top_priority": "立即补货 SKU-A",
        }
        card = build_ai_insight_card("2026-07-27", analysis)
        elements_text = str(card["elements"])
        assert "立即补货 SKU-A" in elements_text
        assert "今日最紧急" in elements_text

    def test_action_items_displayed(self) -> None:
        """action_items 应展示在「行动建议」区。"""
        analysis = {
            "action_items": ["补货 SKU-A", "降低 ACoS", "优化广告投放"],
        }
        card = build_ai_insight_card("2026-07-27", analysis)
        elements_text = str(card["elements"])
        assert "补货 SKU-A" in elements_text
        assert "降低 ACoS" in elements_text
        assert "行动建议" in elements_text

    def test_table_url_button_displayed(self) -> None:
        """配置 table_url 时应展示「查看销售日报」按钮。"""
        card = build_ai_insight_card(
            "2026-07-27",
            {},
            table_url="https://example.feishu.cn/base/xxx",
        )
        elements_text = str(card["elements"])
        assert "查看销售日报" in elements_text
        assert "https://example.feishu.cn/base/xxx" in elements_text

    def test_no_table_url_no_button(self) -> None:
        """未配置 table_url 时不应展示按钮。"""
        card = build_ai_insight_card("2026-07-27", {}, table_url="")
        elements_text = str(card["elements"])
        assert "查看销售日报" not in elements_text

    def test_empty_analysis(self) -> None:
        """空分析应仍能生成基础卡片（不抛异常）。"""
        card = build_ai_insight_card("2026-07-27", {})
        assert "header" in card
        assert "elements" in card
        # 基础元素（三维度概览 + 分隔线）应存在
        assert len(card["elements"]) >= 2

    def test_risk_items_truncated_to_three(self) -> None:
        """risk_items 超过 3 条时应只展示前 3 条。"""
        analysis = {
            "inventory_insight": {
                "risk_items": ["SKU-A", "SKU-B", "SKU-C", "SKU-D", "SKU-E"],
            },
        }
        card = build_ai_insight_card("2026-07-27", analysis)
        elements_text = str(card["elements"])
        assert "SKU-A" in elements_text
        assert "SKU-B" in elements_text
        assert "SKU-C" in elements_text
        assert "SKU-D" not in elements_text
        assert "SKU-E" not in elements_text

    def test_action_items_truncated_to_three(self) -> None:
        """action_items 超过 3 条时应只展示前 3 条。"""
        analysis = {
            "action_items": ["行动1", "行动2", "行动3", "行动4", "行动5"],
        }
        card = build_ai_insight_card("2026-07-27", analysis)
        elements_text = str(card["elements"])
        assert "行动1" in elements_text
        assert "行动2" in elements_text
        assert "行动3" in elements_text
        assert "行动4" not in elements_text
        assert "行动5" not in elements_text
