"""审批流自动触发任务。

业务场景：
    选品池中出现金额 > 5000 美金的采购需求时，
    自动调用飞书审批流 API 创建审批实例，
    主管在飞书审批中心通过/拒绝后回写多维表格"审批状态"字段。

触发条件：
    每天上午 10:00 扫描选品池表，
    筛选"采购金额 > 阈值且审批状态为空或未触发"的记录，
    为每条记录创建一个飞书审批实例。

与 08-05 卡片审批的区别：
    - 08-05 卡片审批：群内点按钮即通过，适合轻量场景
    - 08-06 审批流：飞书审批中心走完整流程，可多级审批、有审批历史
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from src.config import settings
from src.observability.logger import get_logger
from src.scheduler.tasks import _extract_field_value

logger = get_logger()


def _extract_amount(field_value: Any) -> float:
    """从飞书字段值中提取采购金额（兼容数字、文本、列表格式）。

    飞书金额字段返回格式：
    - 数字：8500.0
    - 文本：[{"text": "8500"}]
    - 空值：None

    Args:
        field_value: 飞书返回的字段原始值

    Returns:
        金额浮点数，解析失败返回 0.0
    """
    if field_value is None:
        return 0.0
    if isinstance(field_value, (int, float)):
        return float(field_value)
    if isinstance(field_value, str):
        try:
            return float(field_value)
        except ValueError:
            return 0.0
    if isinstance(field_value, list):
        if not field_value:
            return 0.0
        first = field_value[0]
        if isinstance(first, dict):
            text = first.get("text") or first.get("name") or ""
            try:
                return float(text)
            except (ValueError, TypeError):
                return 0.0
        try:
            return float(first)
        except (ValueError, TypeError):
            return 0.0
    return 0.0


def auto_approval_trigger_task() -> int:
    """审批流自动触发任务。

    扫描选品池表，筛选金额超过阈值且未触发过审批的记录，
    为每条记录创建一个飞书审批实例。

    Returns:
        成功创建的审批实例数量
    """
    logger.info("=" * 50)
    logger.info("定时任务 [审批流自动触发] 开始执行")
    logger.info("=" * 50)

    try:
        from src.feishu.approval import approval_client
        from src.feishu.bitable import bitable_client

        # 检查审批流是否已配置
        if not approval_client.is_configured:
            logger.warning(
                "审批流未完整配置，跳过自动触发。"
                "请在 .env 中设置 FEISHU_APPROVAL_CODE / "
                "FEISHU_APPROVAL_APPROVER_OPEN_ID / FEISHU_APPROVAL_NODE_ID"
            )
            return 0

        table_id = settings.feishu_table_id_inventory
        if not table_id:
            logger.error("库存预警表 ID 未配置，无法扫描")
            return 0

        threshold = settings.purchase_approval_threshold
        logger.info(f"扫描选品池，筛选金额 > ${threshold:,.2f} 的记录")

        # 查询所有库存预警记录
        records = bitable_client.query_records(table_id)
        if not records:
            logger.info("库存预警表为空，本次不触发审批")
            return 0

        triggered_count = 0
        skipped_count = 0

        for record in records:
            try:
                fields = record.get("fields", {})
                asin = _extract_field_value(fields.get("ASIN"))
                product_name = _extract_field_value(
                    fields.get("商品名称"), default="未命名商品"
                )
                amount = _extract_amount(fields.get("采购金额"))
                current_status = _extract_field_value(fields.get("审批状态"))

                # 跳过金额不足阈值的记录
                if amount <= threshold:
                    continue

                # 跳过已触发过审批的记录（避免重复创建）
                if current_status and current_status != "未触发":
                    skipped_count += 1
                    continue

                if not asin:
                    logger.warning(f"记录缺少 ASIN，跳过: record_id={record.get('record_id')}")
                    continue

                # 创建飞书审批实例
                description = (
                    f"自动触发：采购金额 ${amount:,.2f} 超过阈值 ${threshold:,.2f}。"
                    f"商品：{product_name}（ASIN: {asin}）"
                )

                instance_code = approval_client.create_approval_instance(
                    asin=asin,
                    product_name=product_name,
                    amount=amount,
                    biz_type="选品采购",
                    description=description,
                )

                if instance_code:
                    triggered_count += 1
                    logger.info(
                        f"已创建审批实例: ASIN={asin}, 金额=${amount:,.2f}, "
                        f"instance_code={instance_code}"
                    )

                    # 把审批实例 Code 回写到多维表格，便于后续关联查询
                    bitable_client.update_record(
                        table_id,
                        record.get("record_id"),
                        {
                            "审批状态": "审批中",
                            "更新时间": int(datetime.now().timestamp() * 1000),
                        }
                    )
                else:
                    logger.error(f"创建审批实例失败: ASIN={asin}")

            except Exception as e:
                logger.error(
                    f"处理记录失败 record_id={record.get('record_id')}: {e}",
                    exc_info=True,
                )

        logger.info(
            f"定时任务 [审批流自动触发] 完成: "
            f"扫描 {len(records)} 条, 触发 {triggered_count} 条, "
            f"跳过已审批 {skipped_count} 条"
        )
        return triggered_count

    except Exception as e:
        logger.error(f"定时任务 [审批流自动触发] 失败: {e}", exc_info=True)
        return 0
