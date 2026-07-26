"""飞书卡片模板和回调服务单元测试。

覆盖：
1. 选品报告卡片 build_selection_report_card
2. 销售日报卡片 build_daily_report_card
3. 审批卡片 build_approval_card（带回调按钮）
4. FastAPI 回调服务：URL 验证、按钮点击、未知 action
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.feishu.card_callback import app
from src.feishu.card_templates import (
    build_approval_card,
    build_daily_report_card,
    build_selection_report_card,
)


# ============ 选品报告卡片测试 ============


class TestSelectionReportCard:
    """选品报告卡片模板测试。"""

    def test_basic_card_structure(self) -> None:
        """基础结构：含 header/elements/config。"""
        card = build_selection_report_card(
            date="2026-07-26",
            total_configs=15,
            new_count=60,
            update_count=15,
            skip_count=0,
            fail_count=0,
        )
        assert card["config"]["wide_screen_mode"] is True
        assert card["header"]["template"] == "blue"
        assert "2026-07-26" in card["header"]["title"]["content"]

    def test_total_processed_calculation(self) -> None:
        """总处理数 = 新增 + 更新。"""
        card = build_selection_report_card(
            date="2026-07-26",
            total_configs=10,
            new_count=30,
            update_count=20,
            skip_count=5,
            fail_count=2,
        )
        # 找到包含"总处理商品数"的元素
        total_text = ""
        for el in card["elements"]:
            text = el.get("text", {}).get("content", "")
            if "总处理商品数" in text:
                total_text = text
                break
        assert "50" in total_text  # 30 + 20 = 50

    def test_fail_warning_displayed_when_fail_count_gt_zero(self) -> None:
        """失败数 > 0 时显示警告。"""
        card = build_selection_report_card(
            date="2026-07-26",
            total_configs=15,
            new_count=60,
            update_count=15,
            skip_count=0,
            fail_count=3,
        )
        warning_text = ""
        for el in card["elements"]:
            text = el.get("text", {}).get("content", "")
            if "采集失败" in text:
                warning_text = text
                break
        assert "3" in warning_text

    def test_no_warning_when_no_failure(self) -> None:
        """失败数 = 0 时不显示警告。"""
        card = build_selection_report_card(
            date="2026-07-26",
            total_configs=15,
            new_count=75,
            update_count=0,
            skip_count=0,
            fail_count=0,
        )
        for el in card["elements"]:
            text = el.get("text", {}).get("content", "")
            assert "采集失败" not in text

    def test_top_categories_displayed(self) -> None:
        """顶部品类最多展示 3 个。"""
        card = build_selection_report_card(
            date="2026-07-26",
            total_configs=15,
            new_count=75,
            update_count=0,
            skip_count=0,
            fail_count=0,
            top_categories=["家居收纳", "厨房用品", "户外家具", "办公家具"],
        )
        categories_text = ""
        for el in card["elements"]:
            text = el.get("text", {}).get("content", "")
            if "采集品类" in text:
                categories_text = text
                break
        # 最多 3 个
        assert "家居收纳" in categories_text
        assert "厨房用品" in categories_text
        assert "户外家具" in categories_text
        # 第 4 个不显示
        assert "办公家具" not in categories_text


# ============ 销售日报卡片测试 ============


class TestDailyReportCard:
    """销售日报卡片模板测试。"""

    def test_normal_day_uses_green_header(self) -> None:
        """无异常订单时用绿色标题。"""
        card = build_daily_report_card(
            date="2026-07-26",
            total_sales=12500.50,
            total_orders=120,
            avg_acos=18.5,
            abnormal_count=0,
        )
        assert card["header"]["template"] == "green"

    def test_abnormal_day_uses_orange_header(self) -> None:
        """有异常订单时用橙色标题。"""
        card = build_daily_report_card(
            date="2026-07-26",
            total_sales=9800.0,
            total_orders=95,
            avg_acos=25.0,
            abnormal_count=3,
        )
        assert card["header"]["template"] == "orange"

    def test_abnormal_count_displayed(self) -> None:
        """异常订单数显示在卡片中。"""
        card = build_daily_report_card(
            date="2026-07-26",
            total_sales=9800.0,
            total_orders=95,
            avg_acos=25.0,
            abnormal_count=3,
        )
        abnormal_text = ""
        for el in card["elements"]:
            text = el.get("text", {}).get("content", "")
            if "异常订单" in text:
                abnormal_text = text
                break
        assert "3" in abnormal_text

    def test_no_abnormal_message_when_zero(self) -> None:
        """无异常时显示"无异常订单"。"""
        card = build_daily_report_card(
            date="2026-07-26",
            total_sales=12500.0,
            total_orders=120,
            avg_acos=18.5,
            abnormal_count=0,
        )
        found = False
        for el in card["elements"]:
            text = el.get("text", {}).get("content", "")
            if "无异常订单" in text:
                found = True
                break
        assert found

    def test_ai_insight_displayed_when_provided(self) -> None:
        """提供 AI 洞察时显示。"""
        card = build_daily_report_card(
            date="2026-07-26",
            total_sales=12500.0,
            total_orders=120,
            avg_acos=18.5,
            abnormal_count=0,
            ai_insight="今日销售额环比增长 15%，主要驱动品类为户外家具。",
        )
        insight_text = ""
        for el in card["elements"]:
            text = el.get("text", {}).get("content", "")
            if "AI 洞察" in text:
                insight_text = text
                break
        assert "户外家具" in insight_text

    def test_ai_insight_omitted_when_empty(self) -> None:
        """AI 洞察为空时不显示。"""
        card = build_daily_report_card(
            date="2026-07-26",
            total_sales=12500.0,
            total_orders=120,
            avg_acos=18.5,
            abnormal_count=0,
            ai_insight="",
        )
        for el in card["elements"]:
            text = el.get("text", {}).get("content", "")
            assert "AI 洞察" not in text


# ============ 审批卡片测试 ============


class TestApprovalCard:
    """审批卡片（带回调按钮）测试。"""

    def test_basic_structure(self) -> None:
        """基础结构含 header/elements。"""
        card = build_approval_card(
            biz_type="选品采购",
            biz_id="B08X4ABC",
            title="户外折叠椅采购审批",
            amount=8500.0,
            description="单笔采购金额超过 5000 美金，需审批",
        )
        assert card["header"]["template"] == "orange"
        assert "户外折叠椅采购审批" in card["header"]["title"]["content"]

    def test_amount_displayed_correctly(self) -> None:
        """金额按美金格式展示。"""
        card = build_approval_card(
            biz_type="选品采购",
            biz_id="B08X4ABC",
            title="测试",
            amount=12345.67,
            description="测试",
        )
        amount_text = ""
        for el in card["elements"]:
            if el.get("tag") == "div":
                for field in el.get("fields", []):
                    content = field.get("text", {}).get("content", "")
                    if "审批金额" in content:
                        amount_text = content
                        break
        assert "$12,345.67" in amount_text

    def test_approve_button_has_value_field(self) -> None:
        """通过按钮含 value 字段（用于回调）。"""
        card = build_approval_card(
            biz_type="选品采购",
            biz_id="B08X4ABC",
            title="测试",
            amount=8500.0,
            description="测试",
        )
        # 找到 action 元素
        action_el = None
        for el in card["elements"]:
            if el.get("tag") == "action":
                action_el = el
                break
        assert action_el is not None

        actions = action_el["actions"]
        approve_btn = next(a for a in actions if "通过" in a["text"]["content"])
        assert "value" in approve_btn
        assert approve_btn["value"]["action"] == "approve"
        assert approve_btn["value"]["biz_id"] == "B08X4ABC"

    def test_reject_button_has_value_field(self) -> None:
        """拒绝按钮含 value 字段。"""
        card = build_approval_card(
            biz_type="库存补货",
            biz_id="SKU-001",
            title="测试",
            amount=6000.0,
            description="测试",
        )
        action_el = next(el for el in card["elements"] if el.get("tag") == "action")
        reject_btn = next(a for a in action_el["actions"] if "拒绝" in a["text"]["content"])
        assert reject_btn["value"]["action"] == "reject"
        assert reject_btn["type"] == "danger"

    def test_view_detail_button_uses_url_when_provided(self) -> None:
        """提供 table_url 时显示查看详情按钮（url 跳转）。"""
        card = build_approval_card(
            biz_type="选品采购",
            biz_id="B08X4ABC",
            title="测试",
            amount=8500.0,
            description="测试",
            table_url="https://example.feishu.cn/base/xxx",
        )
        action_el = next(el for el in card["elements"] if el.get("tag") == "action")
        view_btn = next(
            a for a in action_el["actions"] if "查看详情" in a["text"]["content"]
        )
        assert view_btn["url"] == "https://example.feishu.cn/base/xxx"

    def test_no_view_detail_button_when_url_empty(self) -> None:
        """无 table_url 时不显示查看详情按钮。"""
        card = build_approval_card(
            biz_type="选品采购",
            biz_id="B08X4ABC",
            title="测试",
            amount=8500.0,
            description="测试",
        )
        action_el = next(el for el in card["elements"] if el.get("tag") == "action")
        # 应该只有通过/拒绝两个按钮，没有查看详情
        assert len(action_el["actions"]) == 2


# ============ 回调服务测试 ============


class TestCallbackServiceURLVerification:
    """URL 验证（challenge）测试。"""

    def test_url_verification_returns_challenge(self) -> None:
        """URL 验证请求原样返回 challenge。"""
        client = TestClient(app)
        response = client.post("/callback", json={
            "challenge": "ajks38bkdhv",
            "token": "xxxxxx",
            "type": "url_verification",
        })
        assert response.status_code == 200
        assert response.json()["challenge"] == "ajks38bkdhv"


class TestCallbackServiceCardAction:
    """卡片按钮点击回调测试。"""

    def test_approve_action_returns_toast_and_card(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """点击"通过"按钮返回 toast 提示 + 更新后的卡片。

        新版飞书回调响应格式：{"toast": {...}, "card": {...}}
        """
        # mock bitable_client，避免真实调用飞书 API
        monkeypatch.setattr(
            "src.feishu.card_callback.bitable_client.query_records",
            lambda *args, **kwargs: [{"record_id": "rec_test_001"}],
        )
        monkeypatch.setattr(
            "src.feishu.card_callback.bitable_client.update_record",
            lambda *args, **kwargs: "rec_test_001",
        )

        client = TestClient(app)
        response = client.post("/callback", json={
            "token": "xxx",
            "type": "event_callback",
            "event": {
                "event_type": "card.action.trigger",
                "operator": {"open_id": "ou_test_user"},
                "action": {
                    "value": {
                        "action": "approve",
                        "biz_type": "选品采购",
                        "biz_id": "B08X4ABC",
                        "amount": "8500.0",
                    },
                    "tag": "button",
                },
                "context": {"open_message_id": "om_xxx"},
            },
        })
        assert response.status_code == 200
        data = response.json()
        # 新格式：toast 提示
        assert "toast" in data
        assert data["toast"]["type"] == "success"
        assert "B08X4ABC" in data["toast"]["content"]
        # 新格式：更新后的卡片
        assert "card" in data
        assert data["card"]["type"] == "raw"
        card_data = data["card"]["data"]
        assert "已通过" in card_data["header"]["title"]["content"]

    def test_reject_action_returns_toast_and_card(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """点击"拒绝"按钮返回 toast 提示 + 更新后的卡片。"""
        monkeypatch.setattr(
            "src.feishu.card_callback.bitable_client.query_records",
            lambda *args, **kwargs: [{"record_id": "rec_test_002"}],
        )
        monkeypatch.setattr(
            "src.feishu.card_callback.bitable_client.update_record",
            lambda *args, **kwargs: "rec_test_002",
        )

        client = TestClient(app)
        response = client.post("/callback", json={
            "token": "xxx",
            "type": "event_callback",
            "event": {
                "event_type": "card.action.trigger",
                "operator": {"open_id": "ou_test_user"},
                "action": {
                    "value": {
                        "action": "reject",
                        "biz_type": "库存补货",
                        "biz_id": "SKU-001",
                        "amount": "6000.0",
                    },
                    "tag": "button",
                },
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert "toast" in data
        assert data["toast"]["type"] == "success"
        assert "SKU-001" in data["toast"]["content"]
        assert "card" in data
        card_data = data["card"]["data"]
        assert "已拒绝" in card_data["header"]["title"]["content"]

    def test_unknown_action_returns_failure(self) -> None:
        """未知 action 返回失败但不报 500。"""
        client = TestClient(app)
        response = client.post("/callback", json={
            "token": "xxx",
            "type": "event_callback",
            "event": {
                "event_type": "card.action.trigger",
                "operator": {"open_id": "ou_test"},
                "action": {
                    "value": {"action": "unknown_action"},
                    "tag": "button",
                },
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert data["success"] is False
        assert "unknown_action" in data["message"]

    def test_unsupported_event_type_returns_200_with_error(self) -> None:
        """不支持的事件类型返回 200 + 错误信息（避免飞书重试）。"""
        client = TestClient(app)
        response = client.post("/callback", json={
            "token": "xxx",
            "type": "event_callback",
            "event": {"event_type": "some_other_event"},
        })
        assert response.status_code == 200
        assert response.json()["success"] is False

    def test_new_schema_2_0_card_action(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """新格式（schema 2.0）的卡片按钮点击能正确处理。

        飞书新版回调格式顶层无 type 字段，event_type 在 header 里。
        """
        # mock bitable_client，避免真实调用飞书 API
        monkeypatch.setattr(
            "src.feishu.card_callback.bitable_client.query_records",
            lambda *args, **kwargs: [{"record_id": "rec_test_003"}],
        )
        monkeypatch.setattr(
            "src.feishu.card_callback.bitable_client.update_record",
            lambda *args, **kwargs: "rec_test_003",
        )

        client = TestClient(app)
        response = client.post("/callback", json={
            "schema": "2.0",
            "header": {
                "event_id": "xxx",
                "event_type": "card.action.trigger",
                "token": "xxx",
                "app_id": "cli_xxx",
            },
            "event": {
                "operator": {"open_id": "ou_test"},
                "action": {
                    "value": {"action": "approve", "biz_id": "TEST123", "biz_type": "选品采购", "amount": "5000.0"},
                    "tag": "button",
                },
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert "toast" in data
        assert data["toast"]["type"] == "success"

    def test_invalid_json_returns_400(self) -> None:
        """请求体不是 JSON 返回 400。"""
        client = TestClient(app)
        response = client.post(
            "/callback",
            data="not a json",
            headers={"Content-Type": "application/json"},
        )
        assert response.status_code == 400

    def test_approve_failure_returns_error_toast(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """回写多维表格失败时返回 error toast（但仍返回 200，避免飞书重试）。"""
        # mock query_records 抛异常，模拟回写失败
        def _raise(*args, **kwargs):
            raise RuntimeError("飞书 API 不可用")
        monkeypatch.setattr(
            "src.feishu.card_callback.bitable_client.query_records",
            _raise,
        )

        client = TestClient(app)
        response = client.post("/callback", json={
            "type": "event_callback",
            "event": {
                "event_type": "card.action.trigger",
                "operator": {"open_id": "ou_test"},
                "action": {
                    "value": {
                        "action": "approve",
                        "biz_type": "选品采购",
                        "biz_id": "B08FAIL",
                        "amount": "5000.0",
                    },
                    "tag": "button",
                },
            },
        })
        assert response.status_code == 200
        data = response.json()
        assert data["toast"]["type"] == "error"
        assert "更新失败" in data["toast"]["content"]

    def test_unsupported_callback_type_returns_200(self) -> None:
        """未支持的回调类型返回 200（避免飞书重试）。"""
        client = TestClient(app)
        response = client.post("/callback", json={
            "type": "unknown_type",
        })
        assert response.status_code == 200
        assert response.json()["success"] is False


class TestHealthEndpoint:
    """健康检查端点测试。"""

    def test_health_returns_ok(self) -> None:
        """健康检查返回 ok。"""
        client = TestClient(app)
        response = client.get("/health")
        assert response.status_code == 200
        assert response.json()["status"] == "ok"

    def test_root_returns_service_info(self) -> None:
        """根路径返回服务说明。"""
        client = TestClient(app)
        response = client.get("/")
        assert response.status_code == 200
        data = response.json()
        assert "service" in data
        assert "version" in data
