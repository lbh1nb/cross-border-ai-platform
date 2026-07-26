"""飞书群聊搜索服务。

让业务用户在 GUI 一键列出机器人已加入的所有群聊，
点选一个即可自动填入 chat_id，不用手动调用通讯录 API。

调用飞书 API：
- 端点：GET /im/v1/chats
- 需要 im:chat:readonly 权限

前置条件：
- 应用机器人已加入目标群聊（否则扫不到）
"""

from __future__ import annotations

from typing import Any

import httpx

from src.feishu.auth import FEISHU_BASE_URL, get_tenant_access_token
from src.observability.logger import get_logger

logger = get_logger()

# HTTP 请求超时时间（秒）
_REQUEST_TIMEOUT = 10

# 每页返回数量（飞书最大 100）
_PAGE_SIZE = 100


def list_bot_chats() -> list[dict[str, Any]]:
    """列出应用机器人已加入的所有群聊。

    业务用户在 GUI 点"搜索群聊"按钮后调用本函数，
    返回机器人所在的所有群聊列表，用户点选一个即可。

    Returns:
        群聊列表，每项含 chat_id / name / description / owner_id。
        出错或无结果返回空列表，不抛出异常。
    """
    try:
        token = get_tenant_access_token()
    except Exception as e:
        logger.error(f"获取 tenant_access_token 失败: {e}", exc_info=True)
        return []

    if not token:
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    params = {"page_size": _PAGE_SIZE, "user_id_type": "open_id"}

    all_items: list[dict[str, Any]] = []
    page_token = ""

    try:
        while True:
            if page_token:
                params["page_token"] = page_token

            with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
                response = client.get(
                    f"{FEISHU_BASE_URL}/im/v1/chats",
                    headers=headers,
                    params=params,
                )
                data = response.json()

            if data.get("code") != 0:
                logger.error(
                    f"列出群聊失败: code={data.get('code')}, msg={data.get('msg')}"
                )
                return []

            items = data.get("data", {}).get("items", [])
            all_items.extend(items)

            # 是否还有下一页
            page_token = data.get("data", {}).get("page_token", "")
            has_more = data.get("data", {}).get("has_more", False)
            if not has_more or not page_token:
                break

        logger.info(f"列出机器人所在群聊 {len(all_items)} 个")
        return all_items

    except Exception as e:
        logger.error(f"列出群聊异常: {e}", exc_info=True)
        return []
