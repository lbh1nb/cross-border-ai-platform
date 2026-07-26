"""库存预警判断逻辑。

根据可售天数判断预警等级：
  < 7 天  -> 紧急
  < 14 天 -> 预警
  < 21 天 -> 关注
  >= 21 天 -> 正常
"""

from __future__ import annotations


ALERT_THRESHOLD_URGENT = 7    # 紧急：可售天数 < 7
ALERT_THRESHOLD_WARNING = 14  # 预警：可售天数 < 14
ALERT_THRESHOLD_WATCH = 21    # 关注：可售天数 < 21


def get_alert_level(stock_days: int) -> str:
    """根据可售天数返回预警等级。

    Args:
        stock_days: 可售天数

    Returns:
        预警等级：紧急/预警/关注/正常
    """
    if stock_days < ALERT_THRESHOLD_URGENT:
        return "紧急"
    if stock_days < ALERT_THRESHOLD_WARNING:
        return "预警"
    if stock_days < ALERT_THRESHOLD_WATCH:
        return "关注"
    return "正常"
