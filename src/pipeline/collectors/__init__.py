"""采集器模块：统一导出。"""

from .base import BaseCollector, ProductInfo
from .amazon_mock import MockAmazonCollector
from .amazon_real import RealAmazonCollector
from .multi_platform_mock import MockMultiPlatformCollector

__all__ = [
    "BaseCollector",
    "ProductInfo",
    "MockAmazonCollector",
    "MockMultiPlatformCollector",
    "RealAmazonCollector",
]
