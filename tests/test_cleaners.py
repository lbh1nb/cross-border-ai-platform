"""清洗器模块单元测试。"""

from __future__ import annotations

from src.pipeline.cleaners import CleanerConfig, DataCleaner
from src.pipeline.collectors import ProductInfo


def _make_product(
    asin: str = "B0TEST",
    rating: float = 4.0,
    price_min: float = 15.0,
    price_max: float = 25.0,
    bsr_rank: int = 1000,
) -> ProductInfo:
    """构造测试用商品数据。"""
    return ProductInfo(
        name="测试商品",
        asin=asin,
        category="家居收纳",
        price_min=price_min,
        price_max=price_max,
        rating=rating,
        review_count=500,
        bsr_rank=bsr_rank,
        url="https://example.com",
    )


class TestDataCleaner:
    """数据清洗器测试。"""

    def test_pass_valid_products(self) -> None:
        """合格商品全部保留。"""
        cleaner = DataCleaner()
        products = [_make_product(asin=f"B0{i:08d}") for i in range(5)]
        result = cleaner.clean(products)
        assert len(result) == 5

    def test_filter_low_rating(self) -> None:
        """低评分被过滤。"""
        cleaner = DataCleaner(CleanerConfig(min_rating=4.0))
        products = [
            _make_product(asin="B0AAA", rating=3.0),
            _make_product(asin="B0BBB", rating=4.5),
        ]
        result = cleaner.clean(products)
        assert len(result) == 1
        assert result[0].asin == "B0BBB"

    def test_filter_low_price(self) -> None:
        """低价商品被过滤。"""
        cleaner = DataCleaner(CleanerConfig(min_price=20.0))
        products = [
            _make_product(asin="B0AAA", price_min=5, price_max=10),
            _make_product(asin="B0BBB", price_min=25, price_max=35),
        ]
        result = cleaner.clean(products)
        assert len(result) == 1
        assert result[0].asin == "B0BBB"

    def test_filter_high_price(self) -> None:
        """高价商品被过滤。"""
        cleaner = DataCleaner(CleanerConfig(max_price=100.0))
        products = [
            _make_product(asin="B0AAA", price_min=50, price_max=80),
            _make_product(asin="B0BBB", price_min=150, price_max=200),
        ]
        result = cleaner.clean(products)
        assert len(result) == 1
        assert result[0].asin == "B0AAA"

    def test_filter_high_bsr(self) -> None:
        """BSR 太靠后被过滤。"""
        cleaner = DataCleaner(CleanerConfig(max_bsr_rank=10000))
        products = [
            _make_product(asin="B0AAA", bsr_rank=5000),
            _make_product(asin="B0BBB", bsr_rank=50000),
        ]
        result = cleaner.clean(products)
        assert len(result) == 1
        assert result[0].asin == "B0AAA"

    def test_deduplicate_by_asin(self) -> None:
        """相同 ASIN 去重，保留第一个。"""
        cleaner = DataCleaner()
        products = [
            _make_product(asin="B0DUP"),
            _make_product(asin="B0DUP"),
            _make_product(asin="B0UNI"),
        ]
        result = cleaner.clean(products)
        assert len(result) == 2
        asins = {p.asin for p in result}
        assert asins == {"B0DUP", "B0UNI"}

    def test_empty_input(self) -> None:
        """空列表输入返回空列表。"""
        cleaner = DataCleaner()
        result = cleaner.clean([])
        assert result == []
