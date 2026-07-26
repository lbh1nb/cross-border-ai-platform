"""品类轮换策略：按星期几选择采集品类。

周一到周五分别采集不同品类，周末不采集。
"""

from __future__ import annotations

from datetime import datetime


# 星期几 -> 品类名称（0=周一, 6=周日）
WEEKDAY_CATEGORY: dict[int, str] = {
    0: "家居收纳",
    1: "厨房用品",
    2: "户外家具",
    3: "办公家具",
    4: "卧室家具",
}


def get_today_category(now: datetime | None = None) -> str | None:
    """获取今天应该采集的品类。

    Args:
        now: 当前时间，默认 datetime.now()

    Returns:
        品类名称，周末返回 None
    """
    now = now or datetime.now()
    return WEEKDAY_CATEGORY.get(now.weekday())
