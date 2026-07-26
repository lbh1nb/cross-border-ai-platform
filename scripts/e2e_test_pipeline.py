"""端到端验证：数据管道 采集 → 清洗 → 写入飞书。

验证 MockAmazonCollector + DataCleaner + BitableWriter 完整链路。
"""

from __future__ import annotations

from src.observability.logger import logger
from src.pipeline import DataPipeline
from src.pipeline.cleaners import CleanerConfig, DataCleaner
from src.pipeline.collectors import MockAmazonCollector
from src.pipeline.writers import BitableWriter


def main() -> None:
    logger.info("=" * 60)
    logger.info("数据管道端到端验证：采集 → 清洗 → 写入飞书")
    logger.info("=" * 60)

    # 组装管道
    collector = MockAmazonCollector(seed=42)
    cleaner = DataCleaner(CleanerConfig(
        min_rating=3.8,
        min_price=10.0,
        max_price=300.0,
        max_bsr_rank=30000,
    ))
    writer = BitableWriter()
    pipeline = DataPipeline(collector, cleaner, writer)

    # 执行：采集家居收纳 10 条
    logger.info("场景1：采集「家居收纳」10 条")
    record_ids_1 = pipeline.run("家居收纳", limit=10)
    logger.info(f"写入成功 {len(record_ids_1)} 条: {record_ids_1}")

    # 执行：采集厨房用品 8 条
    logger.info("")
    logger.info("场景2：采集「厨房用品」8 条")
    record_ids_2 = pipeline.run("厨房用品", limit=8)
    logger.info(f"写入成功 {len(record_ids_2)} 条: {record_ids_2}")

    # 汇总
    logger.info("")
    logger.info("=" * 60)
    logger.info(f"验证完成！共写入 {len(record_ids_1) + len(record_ids_2)} 条记录")
    logger.info("请打开飞书多维表格查看选品池数据：")
    logger.info("https://ocndodd7lmyr.feishu.cn/base/ZZf6bIeiQav5QLs3UAfcHqBPnWg")
    logger.info("=" * 60)

    collector.close()


if __name__ == "__main__":
    main()
