"""ERP 数据模拟器：生成库存数据写入飞书库存预警表。

生成逼真的库存数据：
- 从选品池已有商品中抽样
- 随机生成库存数量和日均销量
- 计算可售天数
- 写入飞书库存预警表
"""

from __future__ import annotations

import random
from datetime import datetime
from typing import Any

from src.config import settings
from src.feishu.bitable import bitable_client
from src.observability.logger import get_logger

logger = get_logger()


class MockERP:
    """ERP 数据模拟器。

    从飞书选品池抽样商品，生成库存数据写入库存预警表。

    Usage:
        erp = MockERP(seed=42)
        erp.generate_inventory_data(count=10)
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def generate_inventory_data(self, count: int = 10) -> list[str]:
        """生成库存数据并写入飞书库存预警表。

        Args:
            count: 生成的库存记录数量

        Returns:
            写入的 record_id 列表
        """
        # 1. 从选品池抽样商品
        products = self._sample_products(count)
        if not products:
            logger.warning("选品池为空，无法生成库存数据")
            return []

        # 2. 生成库存记录
        records = [self._build_inventory_record(p) for p in products]

        # 3. 写入飞书
        table_id = settings.feishu_table_id_inventory
        record_ids = bitable_client.batch_add_records(table_id, records)
        logger.info(f"库存数据生成完成: {len(record_ids)} 条写入飞书")
        return record_ids

    def _sample_products(self, count: int) -> list[dict[str, Any]]:
        """从飞书选品池抽样商品。"""
        table_id = settings.feishu_table_id_selection
        all_products = bitable_client.query_records(table_id)

        if not all_products:
            return []

        # 抽样（不重复）
        sample_size = min(count, len(all_products))
        return self._rng.sample(all_products, sample_size)

    def _build_inventory_record(self, product_record: dict[str, Any]) -> dict[str, Any]:
        """根据选品池商品构建库存预警记录。"""
        fields = product_record.get("fields", {})

        asin = self._extract_text(fields.get("ASIN", ""))
        name = self._extract_text(fields.get("商品名称", ""))
        category = self._extract_text(fields.get("品类", "其他"))

        # 生成 SKU
        sku = f"SKU-{asin[-6:]}" if len(asin) >= 6 else f"SKU-{asin}"

        # 随机库存数据
        current_stock = self._rng.randint(50, 500)
        daily_sales = round(self._rng.uniform(5.0, 50.0), 1)
        stock_days = int(current_stock / daily_sales)

        # 计算建议采购量（库存低于 100 时建议采购）
        suggested_purchase = 0
        if current_stock < 100:
            suggested_purchase = self._rng.choice([100, 200, 300, 500])

        # 采购金额估算（单价 5-30 美金）
        unit_cost = round(self._rng.uniform(5.0, 30.0), 2)
        estimated_cost = round(suggested_purchase * unit_cost, 2)

        # 平台随机
        platform = self._rng.choice(["亚马逊", "沃尔玛", "Wayfair"])

        # 预警等级
        from src.scheduler.inventory_alert import get_alert_level
        alert_level = get_alert_level(stock_days)

        return {
            "ASIN": asin,
            "商品名称": name,
            "SKU": sku,
            "平台": platform,
            "当前库存": current_stock,
            "日均销量": daily_sales,
            "可售天数": stock_days,
            "预警等级": alert_level,
            "建议采购量": suggested_purchase,
            "预估采购金额": estimated_cost,
            "审批状态": "未触发",
            "更新时间": int(datetime.now().timestamp() * 1000),
        }

    @staticmethod
    def _extract_text(value: Any) -> str:
        """从飞书字段值中提取纯文本。

        飞书多行文本字段返回 [{"text": "..."}] 格式。
        """
        if isinstance(value, str):
            return value
        if isinstance(value, list) and value:
            first = value[0]
            if isinstance(first, dict):
                return first.get("text", "")
            return str(first)
        return str(value)
