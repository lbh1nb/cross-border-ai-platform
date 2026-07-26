"""数据管道层：采集器 → 清洗器 → 写入器。"""

from .pipeline import DataPipeline

__all__ = ["DataPipeline"]
