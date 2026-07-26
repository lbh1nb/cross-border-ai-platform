"""定时任务函数定义：每个任务独立 try-except，失败不影响其他任务。

三个核心任务：
1. product_collection_task  - 选品数据采集
2. inventory_check_task      - 库存预警检查
3. daily_report_task         - 日报生成（预留）
"""

from __future__ import annotations

from datetime import datetime

from src.config import settings
from src.observability.logger import logger
from src.pipeline import DataPipeline
from src.pipeline.cleaners import CleanerConfig, DataCleaner
from src.pipeline.collectors import MockAmazonCollector
from src.pipeline.writers import BitableWriter

from .category_strategy import get_today_category
from .inventory_alert import get_alert_level


def product_collection_task() -> str | None:
    """选品数据采集任务。

    根据今天是星期几选择对应品类，采集数据写入飞书选品池。
    周末不执行。

    Returns:
        写入的记录数，或 None（周末跳过）
    """
    logger.info("=" * 50)
    logger.info("定时任务 [选品采集] 开始执行")
    logger.info("=" * 50)

    try:
        category = get_today_category()
        if category is None:
            logger.info("今天是周末，跳过采集")
            return None

        logger.info(f"今日采集品类: {category}")

        collector = MockAmazonCollector(seed=int(datetime.now().timestamp()) % 10000)
        cleaner = DataCleaner(CleanerConfig(
            min_rating=3.8,
            min_price=10.0,
            max_price=300.0,
            max_bsr_rank=30000,
        ))
        writer = BitableWriter()
        pipeline = DataPipeline(collector, cleaner, writer)

        record_ids = pipeline.run(category, limit=10)
        logger.info(f"定时任务 [选品采集] 完成: 写入 {len(record_ids)} 条")

        collector.close()
        return category

    except Exception as e:
        logger.error(f"定时任务 [选品采集] 失败: {e}", exc_info=True)
        return None


def inventory_check_task() -> int:
    """库存预警检查任务。

    读取飞书库存预警表，根据可售天数更新预警等级。

    Returns:
        检查的记录数
    """
    logger.info("=" * 50)
    logger.info("定时任务 [库存检查] 开始执行")
    logger.info("=" * 50)

    try:
        from src.feishu.bitable import bitable_client

        table_id = settings.feishu_table_id_inventory
        records = bitable_client.query_records(table_id)

        if not records:
            logger.info("库存预警表为空，跳过检查")
            return 0

        updated_count = 0
        for record in records:
            record_id = record.get("record_id")
            fields = record.get("fields", {})

            # 获取可售天数
            stock_days = fields.get("可售天数")
            if stock_days is None:
                continue

            # 计算预警等级
            alert_level = get_alert_level(int(stock_days))
            current_level = fields.get("预警等级")

            # 等级变化才更新
            if current_level != alert_level:
                bitable_client.update_record(table_id, record_id, {
                    "预警等级": alert_level,
                    "更新时间": int(datetime.now().timestamp() * 1000),
                })
                updated_count += 1
                logger.info(
                    f"库存预警更新: ASIN={fields.get('ASIN', 'N/A')}, "
                    f"可售{stock_days}天 -> {alert_level}"
                )

        logger.info(f"定时任务 [库存检查] 完成: 检查 {len(records)} 条, 更新 {updated_count} 条")
        return len(records)

    except Exception as e:
        logger.error(f"定时任务 [库存检查] 失败: {e}", exc_info=True)
        return 0


def daily_report_task() -> None:
    """日报生成任务（预留）。

    第4周实现：从多维表格拉取昨日销售数据 → AI 生成日报 → 推送飞书群。
    """
    logger.info("定时任务 [日报生成] 预留，第4周实现")
