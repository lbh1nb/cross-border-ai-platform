"""定时任务函数定义：每个任务独立 try-except，失败不影响其他任务。

三个核心任务：
1. product_collection_task  - 选品数据采集（读取飞书采集配置表，多平台多品类循环采集）
2. inventory_check_task      - 库存预警检查
3. daily_report_task         - 日报生成（预留）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.config import settings
from src.observability.logger import logger
from src.pipeline.cleaners import CleanerConfig, DataCleaner
from src.pipeline.collectors import MockMultiPlatformCollector
from src.pipeline.writers import BitableWriter

from .inventory_alert import get_alert_level


def _extract_field_value(field_value: Any, default: str = "") -> str:
    """统一解析飞书字段值，兼容文本/单选/多选格式。

    飞书字段返回格式：
    - 多行文本：[{"text": "家居收纳", "type": "text"}]
    - 单选：    "亚马逊" 或 [{"name": "亚马逊"}]
    - 多选：    [{"name": "亚马逊"}, {"name": "沃尔玛"}]
    - 空值：    None 或 ""

    Args:
        field_value: 飞书返回的字段原始值
        default: 解析失败时的默认值

    Returns:
        字段值的字符串形式
    """
    if field_value is None:
        return default
    if isinstance(field_value, str):
        return field_value
    if isinstance(field_value, list):
        if not field_value:
            return default
        first = field_value[0]
        if isinstance(first, dict):
            # 文本格式 {"text": "...", "type": "text"} 或 单选格式 {"name": "..."}
            return first.get("text") or first.get("name") or default
        return str(first)
    return str(field_value)


def _load_collection_configs() -> list[dict[str, Any]]:
    """从飞书"采集配置"表读取所有启用的采集配置。

    Returns:
        启用状态的配置列表，每项含：品类、平台、采集数量、优先级
    """
    from src.feishu.bitable import bitable_client

    table_id = settings.feishu_table_id_collection_config
    if not table_id:
        logger.error("采集配置表 ID 未配置，请在 .env 中设置 FEISHU_TABLE_ID_COLLECTION_CONFIG")
        return []

    # 筛选启用状态的记录
    filter_condition = {
        "conjunction": "and",
        "conditions": [
            {
                "field_name": "启用状态",
                "operator": "is",
                "value": ["启用"],
            }
        ],
    }
    records = bitable_client.query_records(table_id, filter_condition=filter_condition)

    configs: list[dict[str, Any]] = []
    for record in records:
        fields = record.get("fields", {})
        category = _extract_field_value(fields.get("品类"))
        platform = _extract_field_value(fields.get("平台"), default="亚马逊")
        count = fields.get("采集数量", 5)
        priority = fields.get("优先级", 3)
        enable_status = _extract_field_value(fields.get("启用状态"))

        if enable_status != "启用":
            continue

        if not category:
            continue

        configs.append({
            "category": category,
            "platform": platform,
            "count": int(count) if count else 5,
            "priority": int(priority) if priority else 3,
        })

    # 按优先级降序排序
    configs.sort(key=lambda x: x["priority"], reverse=True)
    logger.info(f"从采集配置表读取到 {len(configs)} 条启用配置")
    return configs


def _collect_one_config(
    collector: MockMultiPlatformCollector,
    cleaner: DataCleaner,
    writer: BitableWriter,
    config: dict[str, Any],
) -> list[str]:
    """根据单条配置执行采集 → 清洗 → 写入。

    Args:
        collector: 多平台采集器
        cleaner: 数据清洗器
        writer: 飞书写入器
        config: 单条配置（含 category/platform/count）

    Returns:
        成功写入的 record_id 列表
    """
    category = config["category"]
    platform = config["platform"]
    count = config["count"]

    logger.info(f"采集 [{category}] @ [{platform}]，目标 {count} 条")

    # 采集
    raw_products = collector.collect(category, limit=count, platform=platform)
    if not raw_products:
        logger.warning(f"  [{category}] @ [{platform}] 采集到 0 条")
        return []

    # 清洗
    cleaned = cleaner.clean(raw_products)
    logger.info(
        f"  [{category}] @ [{platform}] 清洗: "
        f"原始 {len(raw_products)} 条 → 合格 {len(cleaned)} 条"
    )

    # 写入
    if not cleaned:
        return []
    record_ids = writer.write(cleaned)
    logger.info(f"  [{category}] @ [{platform}] 写入: {len(record_ids)} 条")
    return record_ids


def product_collection_task() -> int:
    """选品数据采集任务。

    读取飞书"采集配置"表中所有启用配置，循环采集多平台多品类商品。
    每条配置独立 try-except，单条失败不影响其他配置。

    Returns:
        成功写入的总记录数
    """
    logger.info("=" * 50)
    logger.info("定时任务 [选品采集] 开始执行")
    logger.info("=" * 50)

    try:
        configs = _load_collection_configs()
        if not configs:
            logger.warning("采集配置表为空或全部停用，本次不采集")
            return 0

        collector = MockMultiPlatformCollector(
            seed=int(datetime.now().timestamp()) % 10000
        )
        cleaner = DataCleaner(CleanerConfig(
            min_rating=3.8,
            min_price=10.0,
            max_price=500.0,
            max_bsr_rank=30000,
        ))
        writer = BitableWriter()

        total_written = 0
        success_count = 0
        fail_count = 0

        for config in configs:
            try:
                record_ids = _collect_one_config(
                    collector, cleaner, writer, config
                )
                total_written += len(record_ids)
                success_count += 1
            except Exception as e:
                fail_count += 1
                logger.error(
                    f"配置采集失败 [{config.get('category')}] @ "
                    f"[{config.get('platform')}]: {e}",
                    exc_info=True,
                )

        collector.close()
        logger.info(
            f"定时任务 [选品采集] 完成: "
            f"配置 {len(configs)} 条 "
            f"(成功 {success_count}/失败 {fail_count}), "
            f"总写入 {total_written} 条"
        )
        return total_written

    except Exception as e:
        logger.error(f"定时任务 [选品采集] 失败: {e}", exc_info=True)
        return 0


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
