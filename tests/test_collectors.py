"""采集器模块单元测试。"""

from __future__ import annotations

import pytest

from src.pipeline.collectors import (
    BaseCollector,
    MockAmazonCollector,
    ProductInfo,
    RealAmazonCollector,
)


class TestProductInfo:
    """ProductInfo 数据结构测试。"""

    def test_to_bitable_record(self) -> None:
        """测试转换为飞书记录格式。"""
        product = ProductInfo(
            name="测试商品",
            asin="B0TEST123",
            category="家居收纳",
            price_min=15.99,
            price_max=25.99,
            rating=4.5,
            review_count=1000,
            bsr_rank=500,
            url="https://www.amazon.com/dp/B0TEST123",
        )
        record = product.to_bitable_record()

        assert record["商品名称"] == "测试商品"
        assert record["ASIN"] == "B0TEST123"
        assert record["品类"] == "家居收纳"
        assert record["价格区间"] == "15.99-25.99美金"
        assert record["评分"] == 4.5
        assert record["评论数"] == 1000
        assert record["BSR排名"] == 500
        assert record["商品链接"]["link"] == "https://www.amazon.com/dp/B0TEST123"

    def test_default_values(self) -> None:
        """测试默认值。"""
        product = ProductInfo(
            name="x", asin="x", category="x",
            price_min=10, price_max=20, rating=4.0,
            review_count=100, bsr_rank=1000, url="x",
        )
        assert product.market_capacity == "中"
        assert product.competition_level == "中等"
        assert product.profit_margin == "中"
        assert product.raw_data == {}


class TestMockAmazonCollector:
    """模拟采集器测试。"""

    def test_collect_returns_correct_count(self) -> None:
        """测试采集数量正确。"""
        collector = MockAmazonCollector(seed=42)
        products = collector.collect("家居收纳", limit=10)
        assert len(products) == 10
        collector.close()

    def test_same_seed_same_result(self) -> None:
        """测试相同种子产生相同数据。"""
        c1 = MockAmazonCollector(seed=42)
        c2 = MockAmazonCollector(seed=42)
        p1 = c1.collect("厨房用品", limit=5)
        p2 = c2.collect("厨房用品", limit=5)

        assert len(p1) == len(p2) == 5
        for a, b in zip(p1, p2):
            assert a.asin == b.asin
            assert a.name == b.name
            assert a.price_min == b.price_min

    def test_different_seed_different_result(self) -> None:
        """测试不同种子产生不同数据。"""
        c1 = MockAmazonCollector(seed=1)
        c2 = MockAmazonCollector(seed=999)
        p1 = c1.collect("家居收纳", limit=5)
        p2 = c2.collect("家居收纳", limit=5)

        asins1 = {p.asin for p in p1}
        asins2 = {p.asin for p in p2}
        assert asins1 != asins2

    def test_category_affects_price_range(self) -> None:
        """测试不同品类价格区间不同。"""
        collector = MockAmazonCollector(seed=42)
        home = collector.collect("家居收纳", limit=20)
        outdoor = collector.collect("户外家具", limit=20)

        avg_home = sum((p.price_min + p.price_max) / 2 for p in home) / len(home)
        avg_outdoor = sum((p.price_min + p.price_max) / 2 for p in outdoor) / len(outdoor)

        # 户外家具价格区间(39.99-199.99) 高于 家居收纳(12.99-39.99)
        assert avg_outdoor > avg_home

    def test_rating_in_valid_range(self) -> None:
        """测试评分在 3.8-4.8 范围内。"""
        collector = MockAmazonCollector(seed=42)
        products = collector.collect("家居收纳", limit=50)
        for p in products:
            assert 3.8 <= p.rating <= 4.8

    def test_asin_format(self) -> None:
        """测试 ASIN 格式正确（B0 开头，10 位）。"""
        collector = MockAmazonCollector(seed=42)
        products = collector.collect("家居收纳", limit=10)
        for p in products:
            assert p.asin.startswith("B0")
            assert len(p.asin) == 10

    def test_url_contains_asin(self) -> None:
        """测试商品链接包含 ASIN。"""
        collector = MockAmazonCollector(seed=42)
        products = collector.collect("家居收纳", limit=5)
        for p in products:
            assert p.asin in p.url

    def test_unknown_category_falls_back(self) -> None:
        """测试未知品类回退到'其他'。"""
        collector = MockAmazonCollector(seed=42)
        products = collector.collect("不存在的品类", limit=5)
        assert len(products) == 5
        assert all(p.category == "不存在的品类" for p in products)


class TestRealAmazonCollector:
    """真实采集器测试（预留接口）。"""

    def test_not_implemented(self) -> None:
        """测试未实现时抛出异常。"""
        collector = RealAmazonCollector()
        with pytest.raises(NotImplementedError):
            collector.collect("家居收纳")
