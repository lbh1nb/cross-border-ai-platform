"""数据管道编排器：串联 采集 → 清洗 → 写入 完整流程。

用法：
    from src.pipeline import DataPipeline
    from src.pipeline.collectors import MockAmazonCollector

    pipeline = DataPipeline(MockAmazonCollector(seed=42))
    record_ids = pipeline.run("家居收纳", limit=10)
"""

from __future__ import annotations

from src.observability.logger import logger
from src.pipeline.cleaners import DataCleaner
from src.pipeline.collectors import BaseCollector, ProductInfo
from src.pipeline.writers import BitableWriter


class DataPipeline:
    """数据管道：采集 → 清洗 → 写入。

    编排逻辑：
    1. 调用采集器获取原始数据
    2. 调用清洗器过滤去重
    3. 调用写入器写入飞书多维表格
    """

    def __init__(
        self,
        collector: BaseCollector,
        cleaner: DataCleaner | None = None,
        writer: BitableWriter | None = None,
    ) -> None:
        self._collector = collector
        self._cleaner = cleaner or DataCleaner()
        self._writer = writer or BitableWriter()

    def run(self, category: str, limit: int = 20) -> list[str]:
        """执行完整管道：采集 → 清洗 → 写入。

        Args:
            category: 品类名称
            limit: 采集数量

        Returns:
            成功写入的 record_id 列表
        """
        # 1. 采集
        raw_products = self._collect(category, limit)
        if not raw_products:
            logger.warning(f"品类 [{category}] 采集到 0 条数据")
            return []

        # 2. 清洗
        cleaned = self._clean(raw_products)
        logger.info(
            f"清洗完成: 原始 {len(raw_products)} 条 → "
            f"合格 {len(cleaned)} 条"
        )

        # 3. 写入
        record_ids = self._write(cleaned)
        logger.info(f"写入飞书多维表格成功: {len(record_ids)} 条记录")
        return record_ids

    def _collect(self, category: str, limit: int) -> list[ProductInfo]:
        """采集阶段。"""
        logger.info(f"开始采集品类 [{category}]，目标 {limit} 条")
        products = self._collector.collect(category, limit)
        logger.info(f"采集完成: {len(products)} 条")
        return products

    def _clean(self, products: list[ProductInfo]) -> list[ProductInfo]:
        """清洗阶段。"""
        return self._cleaner.clean(products)

    def _write(self, products: list[ProductInfo]) -> list[str]:
        """写入阶段。"""
        if not products:
            return []
        return self._writer.write(products)
