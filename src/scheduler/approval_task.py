"""审批流事件驱动触发器（08-07 重构）。

旧版（08-06）是定时任务，每天 10:00 扫描选品池，只能配一个审批流。
新版（08-07）改成事件驱动：业务任务（选品采集/库存预警）完成后，
直接调用 trigger_approval_for_records()，传入刚处理的记录列表，
由 approval_rules_service.match_and_trigger() 匹配所有启用的规则，
匹配条件的记录自动创建审批实例。

支持多审批流：每个规则可绑定不同的飞书审批定义和触发条件。

保留 auto_approval_trigger_task() 作为兜底定时任务（每天 10:00），
扫描选品池补触发遗漏的记录（如手动添加的、规则新增后历史记录未触发的）。
"""

from __future__ import annotations

from src.observability.logger import get_logger

logger = get_logger()


def trigger_approval_for_records(
    event_type: str,
    records: list[dict],
) -> int:
    """事件驱动审批触发（业务任务调用入口）。

    选品采集任务 / 库存预警任务完成后调用本函数，
    自动匹配所有启用的审批规则，符合条件的记录创建飞书审批实例。

    Args:
        event_type: 触发事件类型
            - "product_collected"：选品采集完成
            - "inventory_alert"：库存预警触发
        records: 触发事件的记录列表（飞书表格记录格式，含 fields）

    Returns:
        成功创建的审批实例数量

    示例：
        # 选品采集完成后
        trigger_approval_for_records("product_collected", new_records)

        # 库存预警检查完成后，对紧急/预警的记录
        trigger_approval_for_records("inventory_alert", alert_records)
    """
    if not records:
        return 0

    try:
        from src.gui.services.approval_rules_service import match_and_trigger

        triggered = match_and_trigger(event_type, records)
        if triggered > 0:
            logger.info(
                f"事件驱动审批触发: 事件={event_type}, "
                f"记录数={len(records)}, 创建审批={triggered} 条"
            )
        return triggered
    except Exception as e:
        logger.error(
            f"事件驱动审批触发失败: 事件={event_type}, 错误={e}",
            exc_info=True,
        )
        return 0


def auto_approval_trigger_task() -> int:
    """兜底定时审批触发任务（每天 10:00）。

    扫描选品池 + 库存预警表，对每条记录检查所有启用的审批规则，
    匹配条件且未触发过审批的记录创建审批实例。

    作用：补触发事件驱动遗漏的记录（如手动添加的、规则新增后历史记录）。

    Returns:
        成功创建的审批实例数量
    """
    logger.info("=" * 50)
    logger.info("兜底任务 [审批流定时扫描] 开始执行")
    logger.info("=" * 50)

    try:
        from src.config import settings
        from src.feishu.bitable import bitable_client
        from src.gui.services.approval_rules_service import (
            EVENT_INVENTORY_ALERT,
            EVENT_PRODUCT_COLLECTED,
            match_and_trigger,
        )

        total_triggered = 0

        # 1. 扫描选品池表
        selection_table_id = settings.feishu_table_id_selection
        if selection_table_id:
            records = bitable_client.query_records(selection_table_id)
            if records:
                triggered = match_and_trigger(EVENT_PRODUCT_COLLECTED, records)
                total_triggered += triggered
                logger.info(f"选品池扫描: {len(records)} 条记录, 触发 {triggered} 条审批")

        # 2. 扫描库存预警表
        inventory_table_id = settings.feishu_table_id_inventory
        if inventory_table_id:
            records = bitable_client.query_records(inventory_table_id)
            if records:
                triggered = match_and_trigger(EVENT_INVENTORY_ALERT, records)
                total_triggered += triggered
                logger.info(f"库存预警扫描: {len(records)} 条记录, 触发 {triggered} 条审批")

        logger.info(
            f"兜底任务 [审批流定时扫描] 完成: 共触发 {total_triggered} 条审批"
        )
        return total_triggered

    except Exception as e:
        logger.error(f"兜底任务 [审批流定时扫描] 失败: {e}", exc_info=True)
        return 0
