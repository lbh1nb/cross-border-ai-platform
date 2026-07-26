"""亚马逊模拟采集器：生成逼真的商品数据用于演示和测试。

设计原则：
1. 数据合理且多样——价格、评分、评论数符合真实分布
2. 品类关联——不同品类有不同的价格区间和商品名称特征
3. 可重复——相同随机种子产生相同数据，便于测试
"""

from __future__ import annotations

import random
from typing import Any

from .base import BaseCollector, ProductInfo


# ============================================================
# 品类数据库：每个品类的名称片段、价格区间、容量、竞争强度
# ============================================================
_CATEGORY_DB: dict[str, dict[str, Any]] = {
    "家居收纳": {
        "prefixes": ["可折叠收纳箱", "多功能置物架", "抽屉式收纳柜", "床底收纳盒",
                     "衣柜分隔板", "厨房调料架", "书桌收纳盒", "鞋盒透明"],
        "brands": ["SONGMICS", "SimpleHouseware", "mDesign", "IRIS USA",
                   "StorageWorks", "BINO", "Greenco"],
        "price_range": (12.99, 39.99),
        "market_capacity": "中",
        "competition_level": "中等",
        "profit_margin": "高",
    },
    "厨房用品": {
        "prefixes": ["不粘煎锅", "硅胶铲套装", "不锈钢锅铲", "刀架套装",
                     "保温饭盒", "沥水篮", "调料瓶套装", "硅胶烤垫"],
        "brands": ["T-fal", "Calphalon", "OXO", "Rachael Ray",
                   "Cuisinart", "Ninja", "Carote"],
        "price_range": (15.99, 59.99),
        "market_capacity": "高",
        "competition_level": "激烈",
        "profit_margin": "中",
    },
    "户外家具": {
        "prefixes": ["折叠露营椅", "庭院遮阳伞", "户外编藤沙发", "吊床支架",
                     "户外折叠桌", "庭院秋千", "阳台围栏花架", "烧烤架"],
        "brands": ["OUTBOUND", "PatioSense", "Best Choice Products",
                   "Giantex", "Keter", "Phi Villa", "Anthelion"],
        "price_range": (39.99, 199.99),
        "market_capacity": "中",
        "competition_level": "中等",
        "profit_margin": "高",
    },
    "办公家具": {
        "prefixes": ["升降办公桌", "人体工学椅", "电脑显示器支架", "书架置物架",
                     "文件柜", "办公桌垫", "键盘托架", "桌下走线槽"],
        "brands": ["SHW", "Ergohuman", "VIVO", "FlexiSpot",
                   "SEDETA", "Mr Ironstone", "ApexDesk"],
        "price_range": (49.99, 299.99),
        "market_capacity": "中",
        "competition_level": "中等",
        "profit_margin": "中",
    },
    "卧室家具": {
        "prefixes": ["床头柜", "床底抽屉", "衣柜挂钩", "床尾长凳",
                     "床垫保护套", "羽绒被", "记忆棉枕头", "蚊帐架"],
        "brands": ["Zinus", "Walker Edison", "Amazon Basics",
                   "LUCID", "Linenspa", "Olee Sleep", "Classic Brands"],
        "price_range": (29.99, 159.99),
        "market_capacity": "高",
        "competition_level": "中等",
        "profit_margin": "中",
    },
    "其他": {
        "prefixes": ["多功能置物架", "可折叠收纳箱", "防水储物袋", "墙面挂钩",
                     "门后挂架", "抽屉分隔板", "旋转调料架", "折叠晾衣架"],
        "brands": ["Amazon Basics", "SimpleHouseware", "mDesign",
                   "SONGMICS", "OXO", "IRIS USA", "Greenco"],
        "price_range": (9.99, 49.99),
        "market_capacity": "中",
        "competition_level": "中等",
        "profit_margin": "中",
    },
}


def _generate_asin(rng: random.Random) -> str:
    """生成格式合法的 ASIN（10 位字母数字，B0 开头）。"""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    suffix = "".join(rng.choices(chars, k=8))
    return f"B0{suffix}"


def _generate_rating(rng: random.Random) -> float:
    """评分集中在 3.8-4.8，符合真实分布。"""
    return round(rng.uniform(3.8, 4.8), 1)


def _generate_review_count(rng: random.Random, bsr_rank: int) -> int:
    """评论数与 BSR 排名负相关——排名越靠前评论越多。"""
    base = max(100, 5000 - bsr_rank * 2)
    variation = rng.randint(-200, 500)
    return max(50, base + variation)


def _generate_bsr_rank(rng: random.Random, category: str) -> int:
    """BSR 排名按品类分层，热门品类排名数字更大。"""
    if category in ("厨房用品", "卧室家具"):
        return rng.randint(500, 50000)
    return rng.randint(200, 20000)


class MockAmazonCollector(BaseCollector):
    """亚马逊模拟采集器。

    生成逼真的 Best Seller 商品数据，用于演示和测试。
    相同随机种子产生相同数据，便于测试复现。

    Usage:
        collector = MockAmazonCollector(seed=42)
        products = collector.collect("家居收纳", limit=10)
        collector.close()
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def collect(self, category: str, limit: int = 20) -> list[ProductInfo]:
        """采集指定品类的模拟商品数据。

        Args:
            category: 品类名称，必须在 _CATEGORY_DB 中
            limit: 采集数量

        Returns:
            商品信息列表
        """
        cat_data = _CATEGORY_DB.get(category, _CATEGORY_DB["其他"])
        products: list[ProductInfo] = []

        for _ in range(limit):
            prefix = self._rng.choice(cat_data["prefixes"])
            brand = self._rng.choice(cat_data["brands"])
            name = f"{brand} {prefix}"

            price_min = round(
                self._rng.uniform(*cat_data["price_range"]), 2
            )
            price_max = round(price_min + self._rng.uniform(5, 20), 2)
            bsr_rank = _generate_bsr_rank(self._rng, category)
            rating = _generate_rating(self._rng)
            review_count = _generate_review_count(self._rng, bsr_rank)
            asin = _generate_asin(self._rng)

            products.append(ProductInfo(
                name=name,
                asin=asin,
                category=category,
                price_min=price_min,
                price_max=price_max,
                rating=rating,
                review_count=review_count,
                bsr_rank=bsr_rank,
                url=f"https://www.amazon.com/dp/{asin}",
                market_capacity=cat_data["market_capacity"],
                competition_level=cat_data["competition_level"],
                profit_margin=cat_data["profit_margin"],
                raw_data={"source": "mock", "brand": brand},
            ))

        return products
