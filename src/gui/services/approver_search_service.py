"""飞书审批人搜索服务。

让业务用户在 GUI 输入姓名就能查到 open_id，
不用手动复制 ou_ 字符串。

调用飞书通讯录搜索用户 API：
- 端点：GET /search/v1/user
- 需要 contact:user.id:readonly 权限（详见 README）

返回字段：open_id / name / department_name / job_title，
其中 open_id 可直接写入 .env 的 FEISHU_APPROVAL_APPROVER_OPEN_ID。
"""

from __future__ import annotations

import httpx

from src.feishu.auth import FEISHU_BASE_URL, feishu_auth
from src.observability.logger import get_logger

logger = get_logger()

# HTTP 请求超时时间（秒）
_REQUEST_TIMEOUT = 10
# 默认每页返回数量
_DEFAULT_PAGE_SIZE = 20


def search_user(keyword: str) -> list[dict]:
    """按姓名/工号搜索飞书用户。

    业务用户在 GUI 输入姓名后调用本函数，返回匹配的用户列表。
    每个用户含 open_id，可直接用于审批人配置。

    Args:
        keyword: 搜索关键词（用户姓名或工号）

    Returns:
        用户列表，每项含 open_id / name / department_name / job_title。
        出错或无结果返回空列表，不抛出异常。
    """
    keyword = (keyword or "").strip()
    if not keyword:
        return []

    # 获取 tenant_access_token，失败则直接返回空列表
    try:
        token = feishu_auth.get_token()
    except Exception as e:
        logger.error(f"获取 tenant_access_token 失败: {e}", exc_info=True)
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }
    params = {
        "query": keyword,
        "page_size": _DEFAULT_PAGE_SIZE,
    }

    try:
        with httpx.Client(timeout=_REQUEST_TIMEOUT) as client:
            response = client.get(
                f"{FEISHU_BASE_URL}/search/v1/user",
                headers=headers,
                params=params,
            )
            data = response.json()
    except httpx.HTTPError as e:
        logger.error(
            f"搜索飞书用户请求失败: keyword={keyword}, error={e}",
            exc_info=True,
        )
        return []
    except ValueError as e:
        # 响应非 JSON 时 response.json() 抛 ValueError
        logger.error(
            f"搜索飞书用户响应解析失败: keyword={keyword}, error={e}",
            exc_info=True,
        )
        return []

    if data.get("code") != 0:
        logger.error(
            f"搜索飞书用户失败: keyword={keyword}, "
            f"code={data.get('code')}, msg={data.get('msg')}"
        )
        return []

    items = data.get("data", {}).get("items", [])
    logger.info(f"搜索用户 keyword={keyword}, 命中 {len(items)} 条")
    return items


def search_user_by_name(name: str) -> dict | None:
    """按姓名精确匹配飞书用户。

    在 search_user 基础上做姓名精确匹配，
    返回第一个 name 完全等于指定值的用户。
    适用于"输入姓名直接拿到唯一 open_id"的场景。

    Args:
        name: 用户姓名（精确匹配，区分大小写）

    Returns:
        匹配的用户字典（含 open_id），找不到返回 None。
    """
    name = (name or "").strip()
    if not name:
        return None

    users = search_user(name)
    for user in users:
        if user.get("name") == name:
            return user

    logger.info(f"未找到姓名精确匹配的用户: name={name}")
    return None
