"""采集器模块：统一导出。"""

from .base import BaseCollector, ProductInfo
from .amazon_mock import MockAmazonCollector
from .amazon_real import RealAmazonCollector

__all__ = [
    "BaseCollector",
    "ProductInfo",
    "MockAmazonCollector",
    "RealAmazonCollector",
]
