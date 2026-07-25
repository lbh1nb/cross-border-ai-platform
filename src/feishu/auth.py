"""飞书认证模块：获取与缓存 tenant_access_token。

飞书所有 API 调用都需要 tenant_access_token，有效期 2 小时。
本模块负责：获取 token、缓存 token、过期自动刷新。
"""

from __future__ import annotations

import time

import httpx

from src.config import settings
from src.observability.logger import get_logger

logger = get_logger()

# 飞书开放平台 API 基础地址
FEISHU_BASE_URL = "https://open.feishu.cn/open-apis"

# token 有效期 2 小时（7200 秒），提前 5 分钟刷新，避免边界过期
TOKEN_EXPIRE_SECONDS = 7200
TOKEN_REFRESH_AHEAD = 300


class FeishuAuth:
    """飞书认证管理器：获取与缓存 tenant_access_token。

    设计说明：
    - 单例模式，全项目共享一个 token
    - 内存缓存，过期前 5 分钟自动刷新
    - 线程安全由 GIL 保证（单进程足够）
    """

    def __init__(self) -> None:
        self._token: str | None = None
        self._expires_at: float = 0.0

    def get_token(self) -> str:
        """获取有效的 tenant_access_token，过期则自动刷新。

        Returns:
            有效的 tenant_access_token 字符串

        Raises:
            RuntimeError: App ID/Secret 未配置
            httpx.HTTPError: 飞书 API 调用失败
        """
        # 未配置凭证直接报错，避免发出无效请求
        if not settings.feishu_app_id or not settings.feishu_app_secret:
            raise RuntimeError(
                "飞书应用凭证未配置，请在 .env 中设置 FEISHU_APP_ID 和 FEISHU_APP_SECRET"
            )

        # token 仍有效，直接返回
        if self._token and time.time() < self._expires_at:
            return self._token

        # 刷新 token
        self._refresh_token()
        return self._token  # type: ignore[return-value]

    def _refresh_token(self) -> None:
        """调用飞书 API 获取新的 tenant_access_token。"""
        url = f"{FEISHU_BASE_URL}/auth/v3/tenant_access_token/internal"
        payload = {
            "app_id": settings.feishu_app_id,
            "app_secret": settings.feishu_app_secret,
        }

        logger.info("正在获取飞书 tenant_access_token...")

        try:
            response = httpx.post(url, json=payload, timeout=10)
            response.raise_for_status()
            data = response.json()
        except httpx.HTTPError as e:
            logger.error(f"获取 tenant_access_token 失败: {e}")
            raise

        if data.get("code") != 0:
            msg = f"飞书 API 返回错误: code={data.get('code')}, msg={data.get('msg')}"
            logger.error(msg)
            raise RuntimeError(msg)

        self._token = data["tenant_access_token"]
        # 提前 5 分钟过期，避免边界场景
        self._expires_at = time.time() + TOKEN_EXPIRE_SECONDS - TOKEN_REFRESH_AHEAD
        logger.info("tenant_access_token 获取成功，有效期 2 小时")


# 全局单例
feishu_auth = FeishuAuth()


if __name__ == "__main__":
    """直接运行本文件，测试 token 获取是否成功。

    用法：
        1. 复制 .env.example 为 .env
        2. 填入真实的 FEISHU_APP_ID 和 FEISHU_APP_SECRET
        3. python -m src.feishu.auth
    """
    token = feishu_auth.get_token()
    # 只显示前 20 位，避免完整 token 泄露到日志
    print(f"✅ tenant_access_token 获取成功: {token[:20]}...")
    print(f"   完整 token 长度: {len(token)} 字符")
