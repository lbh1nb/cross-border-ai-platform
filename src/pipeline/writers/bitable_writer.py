"""飞书多维表格写入器：将商品数据写入选品池表。"""

from __future__ import annotations

from src.config import settings
from src.feishu.bitable import bitable_client
from src.pipeline.collectors import ProductInfo


class BitableWriter:
    """将商品数据批量写入飞书多维表格选品池。"""

    def __init__(self, table_id: str | None = None) -> None:
        self._table_id = table_id or settings.feishu_table_id_selection

    def write(self, products: list[ProductInfo]) -> list[str]:
        """批量写入商品数据到选品池表。

        Args:
            products: 商品信息列表

        Returns:
            成功写入的 record_id 列表
        """
        if not products:
            return []

        records = [p.to_bitable_record() for p in products]
        record_ids = bitable_client.batch_add_records(self._table_id, records)
        return record_ids

    def write_one(self, product: ProductInfo) -> str:
        """写入单条商品数据。"""
        return bitable_client.add_record(
            self._table_id, product.to_bitable_record()
        )
