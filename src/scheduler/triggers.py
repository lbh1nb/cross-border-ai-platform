"""触发器配置：集中管理所有定时任务的 cron 表达式。

APScheduler cron 表达式格式：
  minute hour day month day_of_week
  0-59   0-23 1-31 1-12 0-6 (0=周一, 6=周日)

参考：https://apscheduler.readthedocs.io/en/stable/modules/triggers/cron.html
"""

from __future__ import annotations


# 选品采集：周一到周五 09:00
COLLECTION_TRIGGER = {
    "trigger": "cron",
    "day_of_week": "mon-fri",  # 0-4 (周一到周五)
    "hour": 9,
    "minute": 0,
    "id": "product_collection",
    "name": "选品数据采集",
}

# 库存预警检查：每 30 分钟
INVENTORY_CHECK_TRIGGER = {
    "trigger": "cron",
    "minute": "*/30",  # 每 30 分钟
    "id": "inventory_check",
    "name": "库存预警检查",
}

# 日报生成：每天 18:00（第4周实现，先预留）
DAILY_REPORT_TRIGGER = {
    "trigger": "cron",
    "hour": 18,
    "minute": 0,
    "id": "daily_report",
    "name": "日报生成",
}

# 数据清理：每三天凌晨 2 点执行
# 防止飞书表格数据过多导致业务用户查看困难
DATA_CLEANUP_TRIGGER = {
    "trigger": "cron",
    "day": "*/3",  # 每 3 天
    "hour": 2,
    "minute": 0,
    "id": "data_cleanup",
    "name": "数据清理",
}

# 审批流自动触发：每天 10:00 扫描选品池
# 金额超过阈值的记录自动创建飞书审批实例
APPROVAL_TRIGGER_TRIGGER = {
    "trigger": "cron",
    "hour": 10,
    "minute": 0,
    "id": "approval_trigger",
    "name": "审批流自动触发",
}

# 所有触发器汇总
ALL_TRIGGERS = [
    COLLECTION_TRIGGER,
    INVENTORY_CHECK_TRIGGER,
    DAILY_REPORT_TRIGGER,
    DATA_CLEANUP_TRIGGER,
    APPROVAL_TRIGGER_TRIGGER,
]
