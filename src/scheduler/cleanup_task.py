"""数据清理任务：定期删除飞书表格中的旧数据。

设计理念：
- 每三天凌晨 2 点自动清理一次
- 选品池、库存预警、销售日报表都参与清理
- 采集配置表不参与清理（是企业长期配置）
- Listing 库表不参与清理（保留优化历史）
- 保留最近 N 天的数据，N 之前的数据全部删除
- 通过环境变量 DATA_RETENTION_DAYS 可配置保留天数

为什么需要清理：
- 防止数据过多导致业务用户查看表格时眼花
- 飞书多维表格单表上限 50000 条，避免触达上限
- 历史趋势数据通过销售日报表的"日期"字段保留，无需重复堆积
"""

from __future__ import annotations

from datetime import datetime, timedelta
from typing import Any

from src.config import settings
from src.feishu.bitable import bitable_client
from src.feishu.field_mapping import _extract_text
from src.observability.logger import get_logger

logger = get_logger()


# 默认保留天数（可通过环境变量 DATA_RETENTION_DAYS 覆盖）
DEFAULT_RETENTION_DAYS = 3

# 参与清理的表配置：表名 + 时间字段名（用于判断"旧数据"）
# 注意：采集配置和 Listing 库不在此列表
CLEANUP_TABLES: list[dict[str, str]] = [
    {
        "name": "选品池",
        "table_id_key": "feishu_table_id_selection",
        "time_field": "分析时间",  # 选品池用"分析时间"判断
    },
    {
        "name": "库存预警",
        "table_id_key": "feishu_table_id_inventory",
        "time_field": "更新时间",  # 库存预警用"更新时间"判断
    },
    {
        "name": "销售日报",
        "table_id_key": "feishu_table_id_daily_report",
        "time_field": "日期",  # 销售日报用"日期"判断
    },
]


def _get_retention_days() -> int:
    """获取数据保留天数（从环境变量读取，失败则用默认值）。"""
    value = getattr(settings, "data_retention_days", None)
    if value and isinstance(value, int) and value > 0:
        return value
    return DEFAULT_RETENTION_DAYS


def _extract_record_timestamp(fields: dict[str, Any], time_field: str) -> int | None:
    """从飞书记录字段中提取时间戳（毫秒）。

    飞书日期字段返回格式：
    - {"date": "2026-07-26", "type": 0}  (type=0 表示日期)
    - 或 {"date": 1753420800000, "type": 0}  (毫秒时间戳)

    Args:
        fields: 飞书记录字段字典
        time_field: 时间字段名

    Returns:
        毫秒时间戳，无法解析时返回 None
    """
    value = fields.get(time_field)
    if value is None:
        return None

    # 格式1: 数字时间戳
    if isinstance(value, (int, float)):
        return int(value)

    # 格式2: 字典 {"date": ...}
    if isinstance(value, dict):
        date_val = value.get("date")
        if isinstance(date_val, (int, float)):
            return int(date_val)
        if isinstance(date_val, str):
            try:
                # 解析 "2026-07-26" 或 "2026-07-26 10:00:00"
                dt = datetime.fromisoformat(date_val.replace("Z", "+00:00"))
                return int(dt.timestamp() * 1000)
            except ValueError:
                return None

    # 格式3: 字符串
    if isinstance(value, str):
        try:
            dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
            return int(dt.timestamp() * 1000)
        except ValueError:
            return None

    return None


def cleanup_table(
    table_id: str, table_name: str, time_field: str, retention_days: int
) -> dict[str, int]:
    """清理单个表的旧数据。

    Args:
        table_id: 飞书表格 ID
        table_name: 表名（用于日志）
        time_field: 时间字段名（用于判断保留还是删除）
        retention_days: 保留最近多少天的数据

    Returns:
        清理统计字典：{"total": N, "deleted": M, "kept": K}
    """
    cutoff_time = datetime.now() - timedelta(days=retention_days)
    cutoff_ms = int(cutoff_time.timestamp() * 1000)

    logger.info(
        f"[{table_name}] 开始清理: 保留 {retention_days} 天数据 "
        f"(删除 {cutoff_time.strftime('%Y-%m-%d')} 之前的记录)"
    )

    # 查询全部记录
    records = bitable_client.query_records(table_id)
    total = len(records)

    if not records:
        logger.info(f"[{table_name}] 表为空，无需清理")
        return {"total": 0, "deleted": 0, "kept": 0}

    # 分类：保留 vs 删除
    to_delete: list[str] = []
    kept_count = 0
    no_time_field_count = 0

    for record in records:
        record_id = record.get("record_id")
        fields = record.get("fields", {})

        timestamp = _extract_record_timestamp(fields, time_field)

        if timestamp is None:
            # 没有时间字段，保留（安全策略，不删未知数据）
            no_time_field_count += 1
            kept_count += 1
            continue

        if timestamp < cutoff_ms:
            to_delete.append(record_id)
        else:
            kept_count += 1

    # 执行批量删除
    deleted_count = 0
    if to_delete:
        deleted_count = bitable_client.batch_delete_records(table_id, to_delete)

    result = {
        "total": total,
        "deleted": deleted_count,
        "kept": kept_count,
        "no_time_field": no_time_field_count,
    }

    logger.info(
        f"[{table_name}] 清理完成: 总 {total} 条 / 删除 {deleted_count} 条 / "
        f"保留 {kept_count} 条 (其中 {no_time_field_count} 条无时间字段保留)"
    )
    return result


def data_cleanup_task() -> dict[str, dict[str, int]]:
    """数据清理任务：清理所有业务表的旧数据。

    每三天凌晨 2 点自动执行，删除超过保留期的旧数据。
    通过环境变量 DATA_RETENTION_DAYS 配置保留天数（默认 3 天）。

    Returns:
        各表的清理统计字典
    """
    logger.info("=" * 50)
    logger.info("定时任务 [数据清理] 开始执行")
    logger.info("=" * 50)

    retention_days = _get_retention_days()
    logger.info(f"数据保留策略: 最近 {retention_days} 天")

    results: dict[str, dict[str, int]] = {}

    try:
        for table_config in CLEANUP_TABLES:
            table_name = table_config["name"]
            table_id_key = table_config["table_id_key"]
            time_field = table_config["time_field"]

            # 从 settings 动态获取 table_id
            table_id = getattr(settings, table_id_key, "")
            if not table_id:
                logger.warning(f"[{table_name}] 未配置 table_id ({table_id_key})，跳过")
                continue

            try:
                result = cleanup_table(table_id, table_name, time_field, retention_days)
                results[table_name] = result
            except Exception as e:
                logger.error(
                    f"[{table_name}] 清理失败: {e}",
                    exc_info=True,
                )
                results[table_name] = {"error": 1, "message": str(e)}

        # 汇总日志
        total_deleted = sum(r.get("deleted", 0) for r in results.values())
        total_kept = sum(r.get("kept", 0) for r in results.values())
        logger.info(
            f"定时任务 [数据清理] 完成: "
            f"共清理 {len(results)} 张表, "
            f"删除 {total_deleted} 条, 保留 {total_kept} 条"
        )
        return results

    except Exception as e:
        logger.error(f"定时任务 [数据清理] 失败: {e}", exc_info=True)
        return results
