"""飞书 Webhook 机器人模块单元测试。

覆盖范围：
1. FeishuBot 类：配置检查、消息发送（文本/富文本/卡片）、错误处理
2. card_templates：库存预警卡片构建、预警等级颜色映射、建议文案
3. 库存检查任务：等级变化触发告警、等级未变化不告警、非告警等级不发送
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import httpx
import pytest

from src.feishu.card_templates import (
    ALERT_TEMPLATE_MAP,
    _get_alert_suggestion,
    build_inventory_alert_card,
)
from src.feishu.feishu_bot import FeishuBot


# ============================================================
# FeishuBot 类测试
# ============================================================
class TestFeishuBotConfig:
    """测试机器人配置检查。"""

    def test_is_configured_true_when_url_set(self) -> None:
        """配置了 Webhook URL 时 is_configured 应返回 True。"""
        bot = FeishuBot(webhook_url="https://open.feishu.cn/open-apis/bot/v2/hook/test-123")
        assert bot.is_configured is True

    def test_is_configured_false_when_url_empty(self) -> None:
        """Webhook URL 为空时 is_configured 应返回 False。

        注意：需 patch settings.feishu_webhook_url，否则会 fallback 到 .env 中的配置。
        """
        with patch("src.feishu.feishu_bot.settings") as mock_settings:
            mock_settings.feishu_webhook_url = ""
            bot = FeishuBot(webhook_url="")
            assert bot.is_configured is False

    def test_is_configured_false_when_url_whitespace(self) -> None:
        """Webhook URL 仅空格时 is_configured 应返回 False。"""
        with patch("src.feishu.feishu_bot.settings") as mock_settings:
            mock_settings.feishu_webhook_url = ""
            bot = FeishuBot(webhook_url="   ")
            assert bot.is_configured is False


class TestFeishuBotSendText:
    """测试文本消息发送。"""

    @patch("src.feishu.feishu_bot.httpx.Client")
    def test_send_text_success(self, mock_client_class: MagicMock) -> None:
        """发送成功时返回 True。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "msg": "success"}
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        bot = FeishuBot(webhook_url="https://example.com/hook/test")
        result = bot.send_text("库存预警测试")

        assert result is True
        mock_client.post.assert_called_once()
        # 验证请求体格式
        call_kwargs = mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["msg_type"] == "text"
        assert call_kwargs["json"]["content"]["text"] == "库存预警测试"

    def test_send_text_skip_when_not_configured(self) -> None:
        """未配置 Webhook URL 时发送应被跳过，返回 False。"""
        bot = FeishuBot(webhook_url="")
        result = bot.send_text("测试消息")
        assert result is False

    @patch("src.feishu.feishu_bot.httpx.Client")
    def test_send_text_fail_on_api_error(self, mock_client_class: MagicMock) -> None:
        """飞书 API 返回非零 code 时应返回 False。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 9499, "msg": "关键词不匹配"}
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        bot = FeishuBot(webhook_url="https://example.com/hook/test")
        result = bot.send_text("不含关键词的消息")

        assert result is False

    @patch("src.feishu.feishu_bot.httpx.Client")
    def test_send_text_fail_on_http_error(self, mock_client_class: MagicMock) -> None:
        """HTTP 错误时应返回 False。"""
        mock_response = MagicMock()
        mock_response.raise_for_status.side_effect = httpx.HTTPStatusError(
            "Server Error", request=MagicMock(), response=MagicMock(status_code=500)
        )

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        bot = FeishuBot(webhook_url="https://example.com/hook/test")
        result = bot.send_text("测试消息")

        assert result is False


class TestFeishuBotSendRichText:
    """测试富文本消息发送。"""

    @patch("src.feishu.feishu_bot.httpx.Client")
    def test_send_rich_text_success(self, mock_client_class: MagicMock) -> None:
        """富文本消息发送成功。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "msg": "success"}
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        bot = FeishuBot(webhook_url="https://example.com/hook/test")
        result = bot.send_rich_text(
            title="库存预警通知",
            content=[
                [{"tag": "text", "text": "商品A 可售5天，"}],
                [{"tag": "b", "text": "紧急预警"}],
            ],
        )

        assert result is True
        call_kwargs = mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["msg_type"] == "post"
        assert call_kwargs["json"]["content"]["post"]["zh_cn"]["title"] == "库存预警通知"


class TestFeishuBotSendCard:
    """测试交互卡片消息发送。"""

    @patch("src.feishu.feishu_bot.httpx.Client")
    def test_send_card_success(self, mock_client_class: MagicMock) -> None:
        """交互卡片发送成功。"""
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "msg": "success"}
        mock_response.raise_for_status.return_value = None

        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_client_class.return_value = mock_client

        bot = FeishuBot(webhook_url="https://example.com/hook/test")
        card = {
            "config": {"wide_screen_mode": True},
            "header": {"title": {"tag": "plain_text", "content": "测试卡片"}},
            "elements": [{"tag": "div", "text": {"tag": "plain_text", "content": "内容"}}],
        }
        result = bot.send_card(card)

        assert result is True
        call_kwargs = mock_client.post.call_args.kwargs
        assert call_kwargs["json"]["msg_type"] == "interactive"
        assert call_kwargs["json"]["card"]["header"]["title"]["content"] == "测试卡片"


# ============================================================
# card_templates 卡片模板测试
# ============================================================
class TestAlertTemplateMap:
    """测试预警等级颜色映射。"""

    def test_urgent_maps_to_red(self) -> None:
        assert ALERT_TEMPLATE_MAP["紧急"] == "red"

    def test_warning_maps_to_orange(self) -> None:
        assert ALERT_TEMPLATE_MAP["预警"] == "orange"

    def test_watch_maps_to_yellow(self) -> None:
        assert ALERT_TEMPLATE_MAP["关注"] == "yellow"

    def test_normal_maps_to_green(self) -> None:
        assert ALERT_TEMPLATE_MAP["正常"] == "green"


class TestGetAlertSuggestion:
    """测试预警建议文案生成。"""

    def test_urgent_suggestion(self) -> None:
        suggestion = _get_alert_suggestion("紧急", 5)
        assert "5" in suggestion
        assert "紧急采购" in suggestion

    def test_warning_suggestion(self) -> None:
        suggestion = _get_alert_suggestion("预警", 10)
        assert "10" in suggestion
        assert "补货" in suggestion

    def test_watch_suggestion(self) -> None:
        suggestion = _get_alert_suggestion("关注", 18)
        assert "18" in suggestion

    def test_normal_no_suggestion(self) -> None:
        suggestion = _get_alert_suggestion("正常", 30)
        assert suggestion == ""


class TestBuildInventoryAlertCard:
    """测试库存预警卡片构建。"""

    def test_card_has_correct_header_for_urgent(self) -> None:
        """紧急预警卡片标题应为红色。"""
        card = build_inventory_alert_card(
            asin="B08X4ABC",
            product_name="户外折叠椅",
            sku="CHAIR-001",
            platform="亚马逊",
            stock_days=5,
            alert_level="紧急",
        )
        assert card["header"]["template"] == "red"
        assert "紧急" in card["header"]["title"]["content"]

    def test_card_has_correct_header_for_warning(self) -> None:
        """预警等级卡片标题应为橙色。"""
        card = build_inventory_alert_card(
            asin="B08X4ABC",
            product_name="测试商品",
            sku="TEST-001",
            platform="沃尔玛",
            stock_days=10,
            alert_level="预警",
        )
        assert card["header"]["template"] == "orange"

    def test_card_contains_product_info(self) -> None:
        """卡片正文应包含商品信息。"""
        card = build_inventory_alert_card(
            asin="B08TEST",
            product_name="测试椅子",
            sku="SKU-001",
            platform="亚马逊",
            stock_days=5,
            alert_level="紧急",
        )
        # 把 elements 序列化为字符串检查关键字段是否出现
        card_str = str(card["elements"])
        assert "B08TEST" in card_str
        assert "测试椅子" in card_str
        assert "SKU-001" in card_str
        assert "亚马逊" in card_str

    def test_card_contains_stock_days(self) -> None:
        """卡片应包含可售天数。"""
        card = build_inventory_alert_card(
            asin="B08X4ABC",
            product_name="测试商品",
            sku="SKU-001",
            platform="亚马逊",
            stock_days=7,
            alert_level="预警",
        )
        card_str = str(card["elements"])
        assert "7" in card_str

    def test_card_includes_suggestion_for_urgent(self) -> None:
        """紧急卡片应包含处理建议。"""
        card = build_inventory_alert_card(
            asin="B08X4ABC",
            product_name="测试商品",
            sku="SKU-001",
            platform="亚马逊",
            stock_days=5,
            alert_level="紧急",
        )
        card_str = str(card["elements"])
        assert "处理建议" in card_str
        assert "紧急采购" in card_str

    def test_card_includes_suggested_purchase_when_set(self) -> None:
        """设置建议采购量时卡片应显示。"""
        card = build_inventory_alert_card(
            asin="B08X4ABC",
            product_name="测试商品",
            sku="SKU-001",
            platform="亚马逊",
            stock_days=5,
            alert_level="紧急",
            suggested_purchase=200,
        )
        card_str = str(card["elements"])
        assert "200" in card_str
        assert "建议采购量" in card_str

    def test_card_excludes_suggested_purchase_when_zero(self) -> None:
        """未设置建议采购量时卡片不应显示该字段。"""
        card = build_inventory_alert_card(
            asin="B08X4ABC",
            product_name="测试商品",
            sku="SKU-001",
            platform="亚马逊",
            stock_days=5,
            alert_level="紧急",
            suggested_purchase=0,
        )
        card_str = str(card["elements"])
        assert "建议采购量" not in card_str

    def test_card_includes_button_when_table_url_configured(self) -> None:
        """配置了表格 URL 时应包含查看详情按钮。"""
        card = build_inventory_alert_card(
            asin="B08X4ABC",
            product_name="测试商品",
            sku="SKU-001",
            platform="亚马逊",
            stock_days=5,
            alert_level="紧急",
            table_url="https://feishu.cn/base/xxx?table=yyy",
        )
        # 最后一个元素应是 action 类型，包含 button
        last_element = card["elements"][-1]
        assert last_element["tag"] == "action"
        assert last_element["actions"][0]["tag"] == "button"
        assert "查看库存详情" in last_element["actions"][0]["text"]["content"]


# ============================================================
# 库存检查任务集成测试
# ============================================================
class TestInventoryCheckTaskIntegration:
    """测试库存检查任务与机器人告警的集成。"""

    @patch("src.feishu.bitable.bitable_client")
    @patch("src.feishu.feishu_bot.httpx.Client")
    def test_alert_triggered_when_level_changes_to_urgent(
        self, mock_http_client: MagicMock, mock_bitable: MagicMock
    ) -> None:
        """等级变为紧急时应触发机器人告警。"""
        from src.scheduler.tasks import _process_one_inventory_record

        # 模拟飞书返回的记录：当前等级"正常"，可售5天（应判为紧急）
        mock_bitable.query_records.return_value = []
        mock_response = MagicMock()
        mock_response.json.return_value = {"code": 0, "msg": "success"}
        mock_response.raise_for_status.return_value = None
        mock_client = MagicMock()
        mock_client.__enter__.return_value = mock_client
        mock_client.post.return_value = mock_response
        mock_http_client.return_value = mock_client

        record = {
            "record_id": "rec1",
            "fields": {
                "ASIN": "B08TEST",
                "商品名称": "测试椅子",
                "SKU": "SKU-001",
                "平台": "亚马逊",
                "可售天数": 5,
                "预警等级": "正常",
                "当前库存": 25,
                "日均销量": 5.0,
            },
        }

        with patch("src.feishu.feishu_bot.feishu_bot") as mock_bot:
            mock_bot.is_configured = True
            mock_bot.send_card.return_value = True

            updated, new_level = _process_one_inventory_record("tbl1", record)

            assert updated is True
            assert new_level == "紧急"
            # 应该调用了飞书表格更新
            mock_bitable.update_record.assert_called_once()
            # 应该发送了告警卡片
            mock_bot.send_card.assert_called_once()
            sent_card = mock_bot.send_card.call_args.args[0]
            assert sent_card["header"]["template"] == "red"

    @patch("src.feishu.bitable.bitable_client")
    def test_no_alert_when_level_unchanged(self, mock_bitable: MagicMock) -> None:
        """等级未变化时不应触发告警。"""
        from src.scheduler.tasks import _process_one_inventory_record

        record = {
            "record_id": "rec1",
            "fields": {
                "ASIN": "B08TEST",
                "可售天数": 30,
                "预警等级": "正常",
            },
        }

        with patch("src.feishu.feishu_bot.feishu_bot") as mock_bot:
            mock_bot.is_configured = True

            updated, new_level = _process_one_inventory_record("tbl1", record)

            assert updated is False
            assert new_level == "正常"
            mock_bitable.update_record.assert_not_called()
            mock_bot.send_card.assert_not_called()

    @patch("src.feishu.bitable.bitable_client")
    def test_no_alert_for_watch_level(self, mock_bitable: MagicMock) -> None:
        """等级变为"关注"时不应触发告警（仅紧急+预警告警）。"""
        from src.scheduler.tasks import _process_one_inventory_record

        record = {
            "record_id": "rec1",
            "fields": {
                "ASIN": "B08TEST",
                "可售天数": 18,  # 关注级
                "预警等级": "正常",
            },
        }

        with patch("src.feishu.feishu_bot.feishu_bot") as mock_bot:
            mock_bot.is_configured = True

            updated, new_level = _process_one_inventory_record("tbl1", record)

            assert updated is True
            assert new_level == "关注"
            # 应该更新了表格
            mock_bitable.update_record.assert_called_once()
            # 但不应发送告警
            mock_bot.send_card.assert_not_called()

    @patch("src.feishu.bitable.bitable_client")
    def test_no_alert_when_bot_not_configured(self, mock_bitable: MagicMock) -> None:
        """机器人未配置时不应发送告警，但仍应更新表格。"""
        from src.scheduler.tasks import _process_one_inventory_record

        record = {
            "record_id": "rec1",
            "fields": {
                "ASIN": "B08TEST",
                "可售天数": 3,  # 紧急
                "预警等级": "正常",
            },
        }

        with patch("src.feishu.feishu_bot.feishu_bot") as mock_bot:
            mock_bot.is_configured = False

            updated, new_level = _process_one_inventory_record("tbl1", record)

            assert updated is True
            assert new_level == "紧急"
            mock_bitable.update_record.assert_called_once()
            mock_bot.send_card.assert_not_called()

    def test_extract_inventory_field_handles_text_format(self) -> None:
        """_extract_inventory_field 应正确解析多行文本格式。"""
        from src.scheduler.tasks import _extract_inventory_field

        # 多行文本格式
        assert _extract_inventory_field([{"text": "B08TEST", "type": "text"}]) == "B08TEST"
        # 单选格式
        assert _extract_inventory_field([{"name": "亚马逊"}]) == "亚马逊"
        # 纯字符串
        assert _extract_inventory_field("B08TEST") == "B08TEST"
        # 数字
        assert _extract_inventory_field(5) == 5
        # 空值
        assert _extract_inventory_field(None, default="N/A") == "N/A"
        # 空列表
        assert _extract_inventory_field([], default="N/A") == "N/A"
