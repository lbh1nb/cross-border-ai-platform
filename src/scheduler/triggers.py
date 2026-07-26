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

# 审批流兜底扫描：每小时整点扫描一次
# 主触发方式是事件驱动（选品采集完成/库存预警触发后立即匹配规则），
# 这个定时任务只是兜底，补触发事件驱动遗漏的记录（如手动添加的、规则新增后历史记录）
APPROVAL_TRIGGER_TRIGGER = {
    "trigger": "cron",
    "minute": 0,  # 每小时整点
    "id": "approval_trigger",
    "name": "审批流兜底扫描",
}

# 所有触发器汇总
ALL_TRIGGERS = [
    COLLECTION_TRIGGER,
    INVENTORY_CHECK_TRIGGER,
    DAILY_REPORT_TRIGGER,
    DATA_CLEANUP_TRIGGER,
    APPROVAL_TRIGGER_TRIGGER,
]
