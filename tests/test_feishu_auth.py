"""飞书认证模块测试。

验证 tenant_access_token 获取逻辑（使用 mock，不依赖真实飞书 API）。
"""

from __future__ import annotations

from unittest.mock import patch

import httpx
import pytest

from src.feishu.auth import FeishuAuth


def test_missing_credentials_raises():
    """未配置凭证时，应抛出 RuntimeError 并给出明确提示。"""
    auth = FeishuAuth()
    with patch("src.feishu.auth.settings") as mock_settings:
        mock_settings.feishu_app_id = ""
        mock_settings.feishu_app_secret = ""
        with pytest.raises(RuntimeError, match="飞书应用凭证未配置"):
            auth.get_token()


def test_token_cached_until_expiry():
    """token 未过期时，第二次调用不应重新请求飞书 API。"""
    auth = FeishuAuth()
    auth._token = "fake_token"
    auth._expires_at = float("inf")  # 永不过期

    with patch("src.feishu.auth.settings") as mock_settings:
        mock_settings.feishu_app_id = "cli_test"
        mock_settings.feishu_app_secret = "secret_test"
        token = auth.get_token()

    assert token == "fake_token"


def test_refresh_token_on_expiry():
    """token 过期后，应重新调用飞书 API 获取新 token。"""
    auth = FeishuAuth()
    auth._token = "old_token"
    auth._expires_at = 0.0  # 已过期

    mock_response = httpx.Response(
        200,
        json={
            "code": 0,
            "msg": "ok",
            "tenant_access_token": "new_token",
            "expire": 7200,
        },
    )

    with (
        patch("src.feishu.auth.settings") as mock_settings,
        patch("httpx.post", return_value=mock_response),
    ):
        mock_settings.feishu_app_id = "cli_test"
        mock_settings.feishu_app_secret = "secret_test"
        token = auth.get_token()

    assert token == "new_token"


def test_api_error_raises_runtime_error():
    """飞书 API 返回非 0 code 时，应抛出 RuntimeError。"""
    auth = FeishuAuth()

    mock_response = httpx.Response(
        200,
        json={"code": 9999, "msg": "invalid app_id"},
    )

    with (
        patch("src.feishu.auth.settings") as mock_settings,
        patch("httpx.post", return_value=mock_response),
        pytest.raises(RuntimeError, match="飞书 API 返回错误"),
    ):
        mock_settings.feishu_app_id = "cli_test"
        mock_settings.feishu_app_secret = "secret_test"
        auth.get_token()
