"""采集器基类：定义统一接口，所有采集器都实现这个接口。

策略模式：上层代码只依赖 BaseCollector 接口，不关心具体数据源。
未来替换为真实采集器时，只需新建一个实现类，无需改动其他代码。
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any


@dataclass
class ProductInfo:
    """商品信息标准数据结构，所有采集器输出统一格式。"""

    name: str                        # 商品名称
    asin: str                        # 亚马逊 ASIN
    category: str                    # 品类
    price_min: float                 # 最低价格（美金）
    price_max: float                 # 最高价格（美金）
    rating: float                    # 评分（1-5）
    review_count: int                # 评论数
    bsr_rank: int                    # Best Seller Rank
    url: str                         # 商品链接
    platform: str = "亚马逊"         # 来源平台：亚马逊/沃尔玛/Wayfair/TikTok Shop/独立站
    market_capacity: str = "中"      # 市场容量：高/中/低
    competition_level: str = "中等"  # 竞争强度：激烈/中等/蓝海
    profit_margin: str = "中"        # 利润空间：高/中/低
    raw_data: dict[str, Any] = field(default_factory=dict)  # 原始数据，供调试

    def to_bitable_record(self) -> dict[str, Any]:
        """转换为飞书多维表格选品池记录格式。"""
        return {
            "商品名称": self.name,
            "ASIN": self.asin,
            "品类": self.category,
            "来源平台": self.platform,
            "价格区间": f"{self.price_min}-{self.price_max}美金",
            "评分": self.rating,
            "评论数": self.review_count,
            "BSR排名": self.bsr_rank,
            "市场容量": self.market_capacity,
            "竞争强度": self.competition_level,
            "利润空间": self.profit_margin,
            "商品链接": {"link": self.url, "text": self.name},
        }


class BaseCollector(ABC):
    """采集器抽象基类。

    子类必须实现 collect() 方法。
    可选实现 close() 方法释放资源（如 HTTP 连接池）。
    """

    @abstractmethod
    def collect(
        self, category: str, limit: int = 20, platform: str = "亚马逊"
    ) -> list[ProductInfo]:
        """采集指定品类+平台的商品数据。

        Args:
            category: 品类关键词，如 "家居收纳" 或企业自定义品类
            limit: 采集数量上限
            platform: 来源平台，如 "亚马逊"/"沃尔玛"/"Wayfair"

        Returns:
            商品信息列表
        """
        ...

    def close(self) -> None:
        """释放资源，默认空实现。"""
        return
