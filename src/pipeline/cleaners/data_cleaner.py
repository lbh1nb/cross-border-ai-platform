"""数据清洗器：过滤、去重、标准化。

负责将采集器输出的原始数据进行质量清洗：
1. 价格区间过滤（过低可能是劣质品，过高可能利润率低）
2. 评分过滤（低于 3.5 的商品不值得做）
3. ASIN 去重（同一批采集可能有重复）
4. BSR 排名过滤（太靠后说明销量差）
"""

from __future__ import annotations

from dataclasses import dataclass

from src.pipeline.collectors import ProductInfo


@dataclass
class CleanerConfig:
    """清洗器配置。"""

    min_rating: float = 3.5         # 最低评分
    min_price: float = 9.99         # 最低价格
    max_price: float = 500.00       # 最高价格
    max_bsr_rank: int = 50000       # 最大 BSR 排名


class DataCleaner:
    """数据清洗器：过滤不合格商品，去重。"""

    def __init__(self, config: CleanerConfig | None = None) -> None:
        self._config = config or CleanerConfig()

    def clean(self, products: list[ProductInfo]) -> list[ProductInfo]:
        """清洗商品数据：过滤 + 去重。

        Args:
            products: 原始商品列表

        Returns:
            清洗后的商品列表
        """
        filtered = self._filter(products)
        deduplicated = self._deduplicate(filtered)
        return deduplicated

    def _filter(self, products: list[ProductInfo]) -> list[ProductInfo]:
        """过滤不合格商品。"""
        result: list[ProductInfo] = []
        for p in products:
            avg_price = (p.price_min + p.price_max) / 2
            if p.rating < self._config.min_rating:
                continue
            if avg_price < self._config.min_price:
                continue
            if avg_price > self._config.max_price:
                continue
            if p.bsr_rank > self._config.max_bsr_rank:
                continue
            result.append(p)
        return result

    def _deduplicate(self, products: list[ProductInfo]) -> list[ProductInfo]:
        """ASIN 去重，保留第一个。"""
        seen: set[str] = set()
        result: list[ProductInfo] = []
        for p in products:
            if p.asin in seen:
                continue
            seen.add(p.asin)
            result.append(p)
        return result
