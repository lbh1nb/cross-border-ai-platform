"""定时任务函数定义：每个任务独立 try-except，失败不影响其他任务。

四个核心任务：
1. product_collection_task  - 选品数据采集（增量同步，按ASIN+平台去重）
2. inventory_check_task      - 库存预警检查
3. daily_report_task         - 日报生成（预留）
4. data_cleanup_task         - 数据清理（每三天执行，防止数据堆积）
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.config import settings
from src.feishu.sync_service import SyncResult, create_selection_sync_service
from src.observability.logger import logger
from src.pipeline.cleaners import CleanerConfig, DataCleaner
from src.pipeline.collectors import MockMultiPlatformCollector

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
    sync_service,
    config: dict[str, Any],
) -> SyncResult:
    """根据单条配置执行采集 → 清洗 → 同步写入。

    使用增量同步：按 ASIN+平台 去重，存在则更新，不存在则新增。

    Args:
        collector: 多平台采集器
        cleaner: 数据清洗器
        sync_service: 飞书同步服务（支持增量更新）
        config: 单条配置（含 category/platform/count）

    Returns:
        同步结果统计
    """
    category = config["category"]
    platform = config["platform"]
    count = config["count"]

    logger.info(f"采集 [{category}] @ [{platform}]，目标 {count} 条")

    # 采集
    raw_products = collector.collect(category, limit=count, platform=platform)
    if not raw_products:
        logger.warning(f"  [{category}] @ [{platform}] 采集到 0 条")
        return SyncResult(table_name="选品池")

    # 清洗
    cleaned = cleaner.clean(raw_products)
    logger.info(
        f"  [{category}] @ [{platform}] 清洗: "
        f"原始 {len(raw_products)} 条 → 合格 {len(cleaned)} 条"
    )

    # 增量同步写入
    if not cleaned:
        return SyncResult(table_name="选品池")
    result = sync_service.sync_products(cleaned)
    logger.info(
        f"  [{category}] @ [{platform}] 同步: "
        f"新增 {result.new_count} / 更新 {result.update_count} / "
        f"跳过 {result.skip_count} / 失败 {result.fail_count}"
    )
    return result


def product_collection_task() -> int:
    """选品数据采集任务（增量同步版）。

    读取飞书"采集配置"表中所有启用配置，循环采集多平台多品类商品。
    按 ASIN+平台 主键去重，已存在的商品会更新而非重复新增。
    每条配置独立 try-except，单条失败不影响其他配置。

    Returns:
        成功处理的记录数（新增+更新）
    """
    logger.info("=" * 50)
    logger.info("定时任务 [选品采集] 开始执行（增量同步模式）")
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
        sync_service = create_selection_sync_service()

        total_new = 0
        total_update = 0
        success_count = 0
        fail_count = 0

        for config in configs:
            try:
                result = _collect_one_config(
                    collector, cleaner, sync_service, config
                )
                total_new += result.new_count
                total_update += result.update_count
                success_count += 1
            except Exception as e:
                fail_count += 1
                logger.error(
                    f"配置采集失败 [{config.get('category')}] @ "
                    f"[{config.get('platform')}]: {e}",
                    exc_info=True,
                )

        collector.close()
        total_processed = total_new + total_update
        logger.info(
            f"定时任务 [选品采集] 完成: "
            f"配置 {len(configs)} 条 "
            f"(成功 {success_count}/失败 {fail_count}), "
            f"新增 {total_new} / 更新 {total_update} / "
            f"总处理 {total_processed} 条"
        )
        return total_processed

    except Exception as e:
        logger.error(f"定时任务 [选品采集] 失败: {e}", exc_info=True)
        return 0


def _extract_inventory_field(field_value: Any, default: Any = None) -> Any:
    """统一解析飞书库存字段值，兼容文本/单选/数字格式。

    Args:
        field_value: 飞书返回的字段原始值
        default: 解析失败时的默认值

    Returns:
        字段值的原始形式
    """
    if field_value is None:
        return default
    if isinstance(field_value, list):
        if not field_value:
            return default
        first = field_value[0]
        if isinstance(first, dict):
            return first.get("text") or first.get("name") or default
        return first
    return field_value


def _process_one_inventory_record(
    table_id: str,
    record: dict,
) -> tuple[bool, str | None]:
    """处理单条库存记录：更新预警等级，必要时触发机器人告警。

    Args:
        table_id: 库存预警表 ID
        record: 飞书记录，含 record_id 和 fields

    Returns:
        (是否更新了预警等级, 新预警等级)
    """
    from src.feishu.bitable import bitable_client
    from src.feishu.card_templates import build_inventory_alert_card
    from src.feishu.feishu_bot import feishu_bot

    record_id = record.get("record_id")
    fields = record.get("fields", {})

    stock_days = fields.get("可售天数")
    if stock_days is None:
        return False, None

    alert_level = get_alert_level(int(stock_days))
    current_level = _extract_inventory_field(fields.get("预警等级"))

    # 等级未变化，无需处理
    if current_level == alert_level:
        return False, alert_level

    # 等级变化，更新飞书表格
    bitable_client.update_record(table_id, record_id, {
        "预警等级": alert_level,
        "更新时间": int(datetime.now().timestamp() * 1000),
    })
    logger.info(
        f"库存预警更新: ASIN={fields.get('ASIN', 'N/A')}, "
        f"可售{stock_days}天 -> {alert_level}"
    )

    # 仅"紧急"和"预警"等级触发机器人告警（避免告警疲劳）
    if alert_level in ("紧急", "预警") and feishu_bot.is_configured:
        asin = _extract_inventory_field(fields.get("ASIN"), default="N/A")
        product_name = _extract_inventory_field(fields.get("商品名称"), default="未命名商品")
        sku = _extract_inventory_field(fields.get("SKU"), default="N/A")
        platform = _extract_inventory_field(fields.get("平台"), default="未知平台")
        current_stock = int(fields.get("当前库存") or 0)
        daily_sales = float(fields.get("日均销量") or 0.0)
        suggested_purchase = int(fields.get("建议采购量") or 0)

        card = build_inventory_alert_card(
            asin=str(asin),
            product_name=str(product_name),
            sku=str(sku),
            platform=str(platform),
            stock_days=int(stock_days),
            alert_level=alert_level,
            current_stock=current_stock,
            daily_sales=daily_sales,
            suggested_purchase=suggested_purchase,
        )
        success = feishu_bot.send_card(card)
        if success:
            logger.info(f"已发送{alert_level}告警到飞书群: ASIN={asin}")
        else:
            logger.warning(f"告警发送失败: ASIN={asin}")

    return True, alert_level


def inventory_check_task() -> int:
    """库存预警检查任务。

    读取飞书库存预警表，根据可售天数更新预警等级。
    当等级变为"紧急"或"预警"时，自动发送飞书机器人告警卡片到告警群。

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
        alert_sent_count = 0
        for record in records:
            try:
                updated, new_level = _process_one_inventory_record(table_id, record)
                if updated:
                    updated_count += 1
                    if new_level in ("紧急", "预警"):
                        alert_sent_count += 1
            except Exception as e:
                logger.error(
                    f"处理库存记录失败 record_id={record.get('record_id')}: {e}",
                    exc_info=True,
                )

        logger.info(
            f"定时任务 [库存检查] 完成: 检查 {len(records)} 条, "
            f"更新 {updated_count} 条, 发送告警 {alert_sent_count} 条"
        )
        return len(records)

    except Exception as e:
        logger.error(f"定时任务 [库存检查] 失败: {e}", exc_info=True)
        return 0


def daily_report_task() -> None:
    """日报生成任务（预留）。

    第4周实现：从多维表格拉取昨日销售数据 → AI 生成日报 → 推送飞书群。
    """
    logger.info("定时任务 [日报生成] 预留，第4周实现")


def data_cleanup_task() -> dict[str, dict[str, int]]:
    """数据清理任务：清理飞书表格中超过保留期的旧数据。

    每三天凌晨 2 点自动执行，删除超过保留期的旧数据。
    默认保留 3 天，可通过环境变量 DATA_RETENTION_DAYS 配置。

    清理范围：
    - 选品池（按"分析时间"判断）
    - 库存预警（按"更新时间"判断）
    - 销售日报（按"日期"判断）

    不清理：
    - 采集配置（企业长期配置）
    - Listing 库（保留优化历史）
    """
    # 延迟导入避免循环依赖
    from .cleanup_task import data_cleanup_task as _cleanup
    return _cleanup()
