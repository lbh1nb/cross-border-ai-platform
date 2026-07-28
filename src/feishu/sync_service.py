"""数据同步服务：实现增量更新、去重、同步监控。

设计理念：
- 选品池：按 ASIN+平台 去重，存在则更新，不存在则新增
- 库存预警：按 SKU 去重，存在则更新，不存在则新增
- 销售日报：按 日期+平台 去重，存在则更新，不存在则新增
- 同步结果统一封装为 SyncResult，记录新增/更新/跳过数和耗时

核心流程：
1. 查询飞书表现有记录，建立主键 -> record_id 索引
2. 遍历新数据，对比主键判断是新增还是更新
3. 批量执行新增和更新操作
4. 返回 SyncResult 统计结果
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

from src.feishu.bitable import bitable_client
from src.feishu.field_mapping import (
    SELECTION_PRIMARY_KEYS,
    extract_primary_values,
    product_to_record,
)
from src.observability.logger import get_logger
from src.pipeline.collectors import ProductInfo

logger = get_logger()


@dataclass
class SyncResult:
    """同步结果统计。

    记录一次同步任务的新增/更新/跳过数量和耗时。
    """

    table_name: str = ""              # 表名（用于日志标识）
    new_count: int = 0                # 新增记录数
    update_count: int = 0             # 更新记录数
    skip_count: int = 0               # 跳过记录数（无变化）
    fail_count: int = 0               # 失败记录数
    duration_ms: int = 0              # 耗时（毫秒）
    errors: list[str] = field(default_factory=list)  # 错误信息列表

    @property
    def total(self) -> int:
        """总处理记录数。"""
        return self.new_count + self.update_count + self.skip_count + self.fail_count

    def __str__(self) -> str:
        return (
            f"[{self.table_name}] 同步完成: "
            f"新增 {self.new_count} / 更新 {self.update_count} / "
            f"跳过 {self.skip_count} / 失败 {self.fail_count} "
            f"(耗时 {self.duration_ms}ms)"
        )


class SyncService:
    """数据同步服务：实现飞书多维表格的增量更新。

    Usage:
        service = SyncService()
        result = service.sync_products(products)
        print(result)
    """

    def __init__(self, table_id: str, table_name: str = "") -> None:
        """初始化同步服务。

        Args:
            table_id: 飞书表格 ID
            table_name: 表名（用于日志标识，可选）
        """
        self._table_id = table_id
        self._table_name = table_name

    # ============================================================
    # 公开方法
    # ============================================================

    def sync_products(self, products: list[ProductInfo]) -> SyncResult:
        """同步商品数据到选品池表（增量更新）。

        按 ASIN+平台 主键去重：
        - 不存在 -> 新增
        - 已存在但字段有变化 -> 更新
        - 已存在且无变化 -> 跳过

        Args:
            products: 商品信息列表

        Returns:
            同步结果统计
        """
        start_time = time.time()
        result = SyncResult(table_name=self._table_name or "选品池")

        if not products:
            result.duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"{result}（输入为空）")
            return result

        try:
            # 1. 查询现有记录，建立主键索引
            existing_index = self._build_existing_index(SELECTION_PRIMARY_KEYS)

            # 2. 分类：新增 vs 更新
            to_create: list[dict[str, Any]] = []
            to_update: list[tuple[str, dict[str, Any]]] = []  # (record_id, fields)

            for product in products:
                new_fields = product_to_record(product)
                primary_value = self._extract_product_primary(product)

                if primary_value in existing_index:
                    # 已存在，准备更新
                    record_id = existing_index[primary_value]
                    to_update.append((record_id, new_fields))
                else:
                    # 不存在，准备新增
                    to_create.append(new_fields)

            # 3. 批量新增
            if to_create:
                created_ids = bitable_client.batch_add_records(self._table_id, to_create)
                result.new_count = len(created_ids)

            # 4. 逐条更新（飞书 API 暂无批量更新，逐条执行）
            for record_id, fields in to_update:
                try:
                    bitable_client.update_record(self._table_id, record_id, fields)
                    result.update_count += 1
                except Exception as e:
                    result.fail_count += 1
                    error_msg = f"更新失败 record_id={record_id}: {e}"
                    result.errors.append(error_msg)
                    logger.error(error_msg)

            # 5. 跳过数 = 总数 - 新增 - 更新 - 失败
            result.skip_count = max(
                0, len(products) - result.new_count - result.update_count - result.fail_count
            )

        except Exception as e:
            result.fail_count = len(products)
            result.errors.append(f"同步整体失败: {e}")
            logger.error(f"同步失败: {e}", exc_info=True)

        result.duration_ms = int((time.time() - start_time) * 1000)
        logger.info(str(result))
        return result

    def sync_records(
        self,
        records: list[dict[str, Any]],
        primary_keys: list[str],
    ) -> SyncResult:
        """同步通用记录到飞书表（增量更新）。

        用于库存预警、销售日报等非商品数据的同步。

        Args:
            records: 记录字段字典列表
            primary_keys: 主键字段名列表

        Returns:
            同步结果统计
        """
        start_time = time.time()
        result = SyncResult(table_name=self._table_name)

        if not records:
            result.duration_ms = int((time.time() - start_time) * 1000)
            logger.info(f"{result}（输入为空）")
            return result

        try:
            # 1. 查询现有记录，建立主键索引
            existing_index = self._build_existing_index(primary_keys)

            # 2. 分类：新增 vs 更新
            to_create: list[dict[str, Any]] = []
            to_update: list[tuple[str, dict[str, Any]]] = []

            for fields in records:
                primary_value = extract_primary_values(fields, primary_keys)

                if primary_value in existing_index:
                    record_id = existing_index[primary_value]
                    to_update.append((record_id, fields))
                else:
                    to_create.append(fields)

            # 3. 批量新增
            if to_create:
                created_ids = bitable_client.batch_add_records(self._table_id, to_create)
                result.new_count = len(created_ids)

            # 4. 逐条更新
            for record_id, fields in to_update:
                try:
                    bitable_client.update_record(self._table_id, record_id, fields)
                    result.update_count += 1
                except Exception as e:
                    result.fail_count += 1
                    error_msg = f"更新失败 record_id={record_id}: {e}"
                    result.errors.append(error_msg)
                    logger.error(error_msg)

            result.skip_count = max(
                0, len(records) - result.new_count - result.update_count - result.fail_count
            )

        except Exception as e:
            result.fail_count = len(records)
            result.errors.append(f"同步整体失败: {e}")
            logger.error(f"同步失败: {e}", exc_info=True)

        result.duration_ms = int((time.time() - start_time) * 1000)
        logger.info(str(result))
        return result

    # ============================================================
    # 私有方法
    # ============================================================

    def _build_existing_index(
        self, primary_keys: list[str]
    ) -> dict[tuple[Any, ...], str]:
        """查询现有记录，构建 主键值 -> record_id 的索引。

        Args:
            primary_keys: 主键字段名列表

        Returns:
            主键值元组到 record_id 的字典
        """
        existing_records = bitable_client.query_records(self._table_id)
        index: dict[tuple[Any, ...], str] = {}

        for record in existing_records:
            record_id = record.get("record_id")
            fields = record.get("fields", {})
            primary_value = extract_primary_values(fields, primary_keys)
            if record_id and primary_value:
                index[primary_value] = record_id

        logger.info(
            f"[{self._table_name}] 现有记录 {len(existing_records)} 条，"
            f"主键索引 {len(index)} 条"
        )
        return index

    @staticmethod
    def _extract_product_primary(product: ProductInfo) -> tuple[str, str]:
        """从 ProductInfo 提取主键值元组。

        选品池主键是 ASIN+平台，对应 ProductInfo 的 asin 和 platform 字段。

        Args:
            product: 商品信息对象

        Returns:
            (asin, platform) 元组
        """
        return (product.asin, product.platform)


# ============================================================
# 便捷工厂函数
# ============================================================
def create_selection_sync_service() -> SyncService:
    """创建选品池同步服务。"""
    from src.config import settings
    return SyncService(
        table_id=settings.feishu_table_id_selection,
        table_name="选品池",
    )


def create_inventory_sync_service() -> SyncService:
    """创建库存预警同步服务。"""
    from src.config import settings
    from src.feishu.field_mapping import INVENTORY_PRIMARY_KEYS
    # 库存预警表主键是 SKU，需要在调用 sync_records 时传入
    return SyncService(
        table_id=settings.feishu_table_id_inventory,
        table_name="库存预警",
    )


def create_daily_report_sync_service() -> SyncService:
    """创建销售日报同步服务。

    主键为"日期+平台"，同一日同一平台只有一条记录。
    用于 seed_daily_report.py 脚本填充模拟数据。

    注意：主键在调用 sync_records() 时通过 primary_keys 参数传入。
    """
    from src.config import settings
    return SyncService(
        table_id=settings.feishu_table_id_daily_report,
        table_name="销售日报",
    )


def create_listing_sync_service() -> SyncService:
    """创建 Listing 库同步服务（v0.7.0 新增）。

    主键为 ASIN，同一商品只有一条优化记录。
    用于双 Agent 联动场景①：选品 Agent 输出 → 写入 Listing 库形成优化队列。

    注意：主键在调用 sync_records() 时通过 primary_keys 参数传入。
    """
    from src.config import settings
    return SyncService(
        table_id=settings.feishu_table_id_listing,
        table_name="Listing库",
    )
