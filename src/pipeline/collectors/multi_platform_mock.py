"""多平台模拟采集器：支持亚马逊、沃尔玛、Wayfair 三大跨境电商平台。

设计原则：
1. 平台差异化——不同平台有不同的 URL 格式、品牌池、价格分布
2. 品类开放——支持企业自定义品类，遇到未知品类生成合理默认数据
3. 可重复——相同随机种子产生相同数据，便于测试

平台特性对比：
- 亚马逊：BSR 排名体系，评论数最多，价格区间广
- 沃尔玛：无 BSR 概念（用 #N 表示），评论数中等，价格偏低
- Wayfair：家具垂直平台，评论数少，价格偏高
"""

from __future__ import annotations

import random
from typing import Any

from .base import BaseCollector, ProductInfo


# ============================================================
# 平台数据库：每个平台的 URL 模板、品牌池、价格系数、评论数系数
# ============================================================
_PLATFORM_DB: dict[str, dict[str, Any]] = {
    "亚马逊": {
        "url_template": "https://www.amazon.com/dp/{asin}",
        "id_generator": "asin",  # 10 位 B0 开头
        "brands": ["SONGMICS", "SimpleHouseware", "mDesign", "IRIS USA",
                   "Amazon Basics", "Zinus", "Walker Edison", "SHW"],
        "price_multiplier": 1.0,
        "review_multiplier": 1.0,
        "has_bsr": True,
    },
    "沃尔玛": {
        "url_template": "https://www.walmart.com/ip/{id}",
        "id_generator": "walmart_id",  # 8-12 位数字
        "brands": ["Mainstays", "Better Homes & Gardens", "Costway",
                   "Best Choice Products", "Giantex", "PatioSense",
                   "HomCom", "Lexmod"],
        "price_multiplier": 0.85,  # 沃尔玛价格普遍比亚马逊低 15%
        "review_multiplier": 0.6,  # 评论数比亚马逊少
        "has_bsr": False,
    },
    "Wayfair": {
        "url_template": "https://www.wayfair.com/furniture/pdp/{slug}-{id}.html",
        "id_generator": "wayfair_id",  # 字母+数字组合
        "brands": ["Kelly Clarkson Home", "Three Posts", "Wade Logan",
                   "Trent Austin Design", "Birch Lane", "George Oliver",
                   " Latitude Run", "Mercury Row"],
        "price_multiplier": 1.25,  # Wayfair 家具溢价 25%
        "review_multiplier": 0.3,  # 评论数最少
        "has_bsr": False,
    },
}


# ============================================================
# 品类数据库：家居跨境电商默认 5 大品类
# 企业可在飞书"采集配置"表添加自定义品类，采集器会自动适配
# ============================================================
_CATEGORY_DB: dict[str, dict[str, Any]] = {
    "家居收纳": {
        "prefixes": ["可折叠收纳箱", "多功能置物架", "抽屉式收纳柜", "床底收纳盒",
                     "衣柜分隔板", "厨房调料架", "书桌收纳盒", "鞋盒透明"],
        "price_range": (12.99, 39.99),
        "market_capacity": "中",
        "competition_level": "中等",
        "profit_margin": "高",
    },
    "厨房用品": {
        "prefixes": ["不粘煎锅", "硅胶铲套装", "不锈钢锅铲", "刀架套装",
                     "保温饭盒", "沥水篮", "调料瓶套装", "硅胶烤垫"],
        "price_range": (15.99, 59.99),
        "market_capacity": "高",
        "competition_level": "激烈",
        "profit_margin": "中",
    },
    "户外家具": {
        "prefixes": ["折叠露营椅", "庭院遮阳伞", "户外编藤沙发", "吊床支架",
                     "户外折叠桌", "庭院秋千", "阳台围栏花架", "烧烤架"],
        "price_range": (39.99, 199.99),
        "market_capacity": "中",
        "competition_level": "中等",
        "profit_margin": "高",
    },
    "办公家具": {
        "prefixes": ["升降办公桌", "人体工学椅", "电脑显示器支架", "书架置物架",
                     "文件柜", "办公桌垫", "键盘托架", "桌下走线槽"],
        "price_range": (49.99, 299.99),
        "market_capacity": "中",
        "competition_level": "中等",
        "profit_margin": "中",
    },
    "卧室家具": {
        "prefixes": ["床头柜", "床底抽屉", "衣柜挂钩", "床尾长凳",
                     "床垫保护套", "羽绒被", "记忆棉枕头", "蚊帐架"],
        "price_range": (29.99, 159.99),
        "market_capacity": "高",
        "competition_level": "中等",
        "profit_margin": "中",
    },
}


# 默认品类模板：未知品类时使用，保证企业自定义品类也能采集到数据
_DEFAULT_CATEGORY: dict[str, Any] = {
    "prefixes": ["热卖款", "爆款", "畅销型号", "经典款", "升级版",
                 "便携款", "豪华版", "经济款"],
    "price_range": (19.99, 99.99),
    "market_capacity": "中",
    "competition_level": "中等",
    "profit_margin": "中",
}


def _generate_asin(rng: random.Random) -> str:
    """生成格式合法的 ASIN（10 位字母数字，B0 开头）。"""
    chars = "ABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789"
    suffix = "".join(rng.choices(chars, k=8))
    return f"B0{suffix}"


def _generate_walmart_id(rng: random.Random) -> str:
    """生成沃尔玛商品 ID（8-12 位数字）。"""
    length = rng.randint(8, 12)
    return "".join(rng.choices("0123456789", k=length))


def _generate_wayfair_id(rng: random.Random) -> str:
    """生成 Wayfair 商品 ID（字母+数字组合，如 abc123def456）。"""
    chars = "abcdefghijklmnopqrstuvwxyz0123456789"
    slug_part = "".join(rng.choices(chars, k=8))
    id_part = "".join(rng.choices("0123456789", k=6))
    return f"{slug_part}-{id_part}"


def _generate_id(rng: random.Random, id_type: str) -> str:
    """根据平台生成对应的商品 ID。"""
    if id_type == "asin":
        return _generate_asin(rng)
    if id_type == "walmart_id":
        return _generate_walmart_id(rng)
    if id_type == "wayfair_id":
        return _generate_wayfair_id(rng)
    return _generate_asin(rng)


def _generate_rating(rng: random.Random) -> float:
    """评分集中在 3.8-4.8，符合真实分布。"""
    return round(rng.uniform(3.8, 4.8), 1)


def _generate_review_count(
    rng: random.Random, bsr_rank: int, multiplier: float
) -> int:
    """评论数与 BSR 排名负相关，受平台系数影响。"""
    base = max(100, 5000 - bsr_rank * 2)
    variation = rng.randint(-200, 500)
    return max(20, int((base + variation) * multiplier))


def _generate_bsr_rank(rng: random.Random) -> int:
    """生成 BSR 排名（仅亚马逊使用）。"""
    return rng.randint(200, 30000)


class MockMultiPlatformCollector(BaseCollector):
    """多平台模拟采集器。

    支持亚马逊、沃尔玛、Wayfair 三大跨境电商平台。
    支持企业自定义品类——遇到未知品类时使用默认模板生成合理数据。

    Usage:
        collector = MockMultiPlatformCollector(seed=42)
        # 亚马逊的家居收纳
        products = collector.collect("家居收纳", limit=5, platform="亚马逊")
        # Wayfair 的自定义品类
        products = collector.collect("蓝牙耳机", limit=5, platform="Wayfair")
        collector.close()
    """

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def collect(
        self, category: str, limit: int = 20, platform: str = "亚马逊"
    ) -> list[ProductInfo]:
        """采集指定品类+平台的模拟商品数据。

        Args:
            category: 品类名称，支持默认品类和企业自定义品类
            limit: 采集数量
            platform: 来源平台（亚马逊/沃尔玛/Wayfair）

        Returns:
            商品信息列表
        """
        # 未知品类用默认模板，保证企业自定义品类也能工作
        cat_data = _CATEGORY_DB.get(category, _DEFAULT_CATEGORY)
        platform_data = _PLATFORM_DB.get(platform, _PLATFORM_DB["亚马逊"])

        products: list[ProductInfo] = []

        for _ in range(limit):
            prefix = self._rng.choice(cat_data["prefixes"])
            brand = self._rng.choice(platform_data["brands"])
            name = f"{brand} {prefix}"

            # 应用平台价格系数
            price_min_raw = self._rng.uniform(*cat_data["price_range"])
            price_min = round(price_min_raw * platform_data["price_multiplier"], 2)
            price_max = round(price_min + self._rng.uniform(5, 20), 2)

            rating = _generate_rating(self._rng)

            # BSR 排名仅亚马逊有
            if platform_data["has_bsr"]:
                bsr_rank = _generate_bsr_rank(self._rng)
            else:
                # 沃尔玛/Wayfair 用 0 表示不适用
                bsr_rank = 0

            review_count = _generate_review_count(
                self._rng,
                bsr_rank if bsr_rank > 0 else 5000,
                platform_data["review_multiplier"],
            )

            # 生成平台对应的商品 ID 和 URL
            product_id = _generate_id(self._rng, platform_data["id_generator"])
            url = platform_data["url_template"].format(
                asin=product_id, id=product_id, slug=product_id.split("-")[0]
            )

            # ASIN 字段统一存商品 ID（跨平台通用）
            asin_field = product_id if platform == "亚马逊" else f"{platform[:2]}-{product_id}"

            products.append(ProductInfo(
                name=name,
                asin=asin_field,
                category=category,
                price_min=price_min,
                price_max=price_max,
                rating=rating,
                review_count=review_count,
                bsr_rank=bsr_rank,
                url=url,
                platform=platform,
                market_capacity=cat_data["market_capacity"],
                competition_level=cat_data["competition_level"],
                profit_margin=cat_data["profit_margin"],
                raw_data={
                    "source": "mock_multi_platform",
                    "brand": brand,
                    "platform": platform,
                    "category": category,
                },
            ))

        return products
