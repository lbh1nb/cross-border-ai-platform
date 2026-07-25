"""Bitable API 封装模块测试。

使用 mock 模拟飞书 API 响应，不依赖真实飞书服务。
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from src.feishu.bitable import BitableClient


def _mock_response(json_data: dict, status_code: int = 200) -> httpx.Response:
    """构造带 request 实例的 mock Response。"""
    request = httpx.Request("POST", "https://open.feishu.cn/open-apis/test")
    return httpx.Response(status_code, json=json_data, request=request)


def test_create_table_success():
    """创建数据表成功，返回 table_id。"""
    client = BitableClient()
    mock_data = {
        "code": 0,
        "msg": "success",
        "data": {"table_id": "tbl1234567890"},
    }

    with (
        patch("src.feishu.bitable.feishu_auth") as mock_auth,
        patch("src.feishu.bitable.settings") as mock_settings,
        patch("httpx.request", return_value=_mock_response(mock_data)),
    ):
        mock_auth.get_token.return_value = "fake_token"
        mock_settings.feishu_bitable_app_token = "app_test_token"

        table_id = client.create_table("选品池", [{"field_name": "商品名称", "type": 1}])

    assert table_id == "tbl1234567890"


def test_add_record_success():
    """新增记录成功，返回 record_id。"""
    client = BitableClient()
    mock_data = {
        "code": 0,
        "msg": "success",
        "data": {"record": {"record_id": "rec123456", "fields": {"ASIN": "B123"}}},
    }

    with (
        patch("src.feishu.bitable.feishu_auth") as mock_auth,
        patch("src.feishu.bitable.settings") as mock_settings,
        patch("httpx.request", return_value=_mock_response(mock_data)),
    ):
        mock_auth.get_token.return_value = "fake_token"
        mock_settings.feishu_bitable_app_token = "app_test_token"

        record_id = client.add_record("tbl001", {"ASIN": "B123", "商品名称": "测试商品"})

    assert record_id == "rec123456"


def test_batch_add_records_success():
    """批量新增记录成功，返回 record_id 列表。"""
    client = BitableClient()
    mock_data = {
        "code": 0,
        "msg": "success",
        "data": {
            "records": [
                {"record_id": "rec001", "fields": {"ASIN": "B001"}},
                {"record_id": "rec002", "fields": {"ASIN": "B002"}},
            ]
        },
    }

    with (
        patch("src.feishu.bitable.feishu_auth") as mock_auth,
        patch("src.feishu.bitable.settings") as mock_settings,
        patch("httpx.request", return_value=_mock_response(mock_data)),
    ):
        mock_auth.get_token.return_value = "fake_token"
        mock_settings.feishu_bitable_app_token = "app_test_token"

        record_ids = client.batch_add_records("tbl001", [{"ASIN": "B001"}, {"ASIN": "B002"}])

    assert record_ids == ["rec001", "rec002"]


def test_query_records_with_pagination():
    """分页查询：has_more=True 时自动获取下一页。"""
    client = BitableClient()
    page1 = {
        "code": 0,
        "data": {"items": [{"record_id": "r1"}], "has_more": True, "page_token": "token2"},
    }
    page2 = {
        "code": 0,
        "data": {"items": [{"record_id": "r2"}], "has_more": False},
    }

    with (
        patch("src.feishu.bitable.feishu_auth") as mock_auth,
        patch("src.feishu.bitable.settings") as mock_settings,
        patch("httpx.request", side_effect=[_mock_response(page1), _mock_response(page2)]),
    ):
        mock_auth.get_token.return_value = "fake_token"
        mock_settings.feishu_bitable_app_token = "app_test_token"

        records = client.query_records("tbl001")

    assert len(records) == 2
    assert records[0]["record_id"] == "r1"
    assert records[1]["record_id"] == "r2"


def test_update_record_success():
    """更新记录成功，返回 record_id。"""
    client = BitableClient()
    mock_data = {
        "code": 0,
        "data": {"record": {"record_id": "rec123", "fields": {"状态": "已通过"}}},
    }

    with (
        patch("src.feishu.bitable.feishu_auth") as mock_auth,
        patch("src.feishu.bitable.settings") as mock_settings,
        patch("httpx.request", return_value=_mock_response(mock_data)),
    ):
        mock_auth.get_token.return_value = "fake_token"
        mock_settings.feishu_bitable_app_token = "app_test_token"

        result = client.update_record("tbl001", "rec123", {"状态": "已通过"})

    assert result == "rec123"


def test_delete_record_success():
    """删除记录成功，返回 True。"""
    client = BitableClient()
    mock_data = {"code": 0, "data": {}}

    with (
        patch("src.feishu.bitable.feishu_auth") as mock_auth,
        patch("src.feishu.bitable.settings") as mock_settings,
        patch("httpx.request", return_value=_mock_response(mock_data)),
    ):
        mock_auth.get_token.return_value = "fake_token"
        mock_settings.feishu_bitable_app_token = "app_test_token"

        result = client.delete_record("tbl001", "rec123")

    assert result is True


def test_api_error_raises_runtime_error():
    """飞书 API 返回非 0 code 时，抛出 RuntimeError。"""
    client = BitableClient()
    mock_data = {"code": 1254607, "msg": "table not found"}

    with (
        patch("src.feishu.bitable.feishu_auth") as mock_auth,
        patch("src.feishu.bitable.settings") as mock_settings,
        patch("httpx.request", return_value=_mock_response(mock_data)),
        pytest.raises(RuntimeError, match="飞书 API 错误"),
    ):
        mock_auth.get_token.return_value = "fake_token"
        mock_settings.feishu_bitable_app_token = "app_test_token"
        client.list_tables()
