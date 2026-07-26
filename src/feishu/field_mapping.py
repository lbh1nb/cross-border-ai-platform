"""字段映射配置：集中管理飞书表格字段名，避免硬编码。

设计理念：
- 字段名集中在配置文件中管理，未来改字段名只改这里
- 提供 ProductInfo -> 飞书记录的转换函数
- 提供"主键字段"配置，用于增量同步去重判断
"""

from __future__ import annotations

from typing import Any

from src.pipeline.collectors import ProductInfo


# ============================================================
# 选品池表字段映射
# ============================================================
# 主键字段：用于增量同步去重判断
# 当这些字段的组合已存在时，认为是同一条记录，执行更新而非新增
SELECTION_PRIMARY_KEYS = ["ASIN", "来源平台"]

# 选品池字段名配置
SELECTION_FIELDS = {
    "name": "商品名称",
    "asin": "ASIN",
    "category": "品类",
    "platform": "来源平台",
    "price_range": "价格区间",
    "rating": "评分",
    "review_count": "评论数",
    "bsr_rank": "BSR排名",
    "market_capacity": "市场容量",
    "competition_level": "竞争强度",
    "profit_margin": "利润空间",
    "url": "商品链接",
}


# ============================================================
# 库存预警表字段映射
# ============================================================
# 主键字段：库存按 SKU 去重
INVENTORY_PRIMARY_KEYS = ["SKU"]

INVENTORY_FIELDS = {
    "asin": "ASIN",
    "name": "商品名称",
    "sku": "SKU",
    "platform": "平台",
    "current_stock": "当前库存",
    "daily_sales": "日均销量",
    "stock_days": "可售天数",
    "alert_level": "预警等级",
    "suggested_purchase": "建议采购量",
    "estimated_cost": "预估采购金额",
    "approval_status": "审批状态",
}


# ============================================================
# 销售日报表字段映射
# ============================================================
# 日报按 日期+平台 去重（同一天同平台只有一条日报）
DAILY_REPORT_PRIMARY_KEYS = ["日期", "平台"]

DAILY_REPORT_FIELDS = {
    "date": "日期",
    "platform": "平台",
    "sales": "销售额",
    "orders": "订单数",
    "ad_cost": "广告花费",
    "acos": "ACoS",
    "returns": "退货数",
    "stock_days": "库存天数",
    "ai_insight": "AI洞察",
    "anomaly": "异常标记",
}


# ============================================================
# 转换函数
# ============================================================
def product_to_record(product: ProductInfo) -> dict[str, Any]:
    """将 ProductInfo 转换为飞书选品池记录格式。

    Args:
        product: 商品信息对象

    Returns:
        飞书表格字段字典
    """
    return {
        SELECTION_FIELDS["name"]: product.name,
        SELECTION_FIELDS["asin"]: product.asin,
        SELECTION_FIELDS["category"]: product.category,
        SELECTION_FIELDS["platform"]: product.platform,
        SELECTION_FIELDS["price_range"]: f"{product.price_min}-{product.price_max}美金",
        SELECTION_FIELDS["rating"]: product.rating,
        SELECTION_FIELDS["review_count"]: product.review_count,
        SELECTION_FIELDS["bsr_rank"]: product.bsr_rank,
        SELECTION_FIELDS["market_capacity"]: product.market_capacity,
        SELECTION_FIELDS["competition_level"]: product.competition_level,
        SELECTION_FIELDS["profit_margin"]: product.profit_margin,
        SELECTION_FIELDS["url"]: {"link": product.url, "text": product.name},
    }


def extract_primary_values(
    record_fields: dict[str, Any], primary_keys: list[str]
) -> tuple[Any, ...]:
    """从飞书记录字段中提取主键值。

    飞书多行文本字段返回 [{"text": "..."}] 格式，需要提取纯文本。

    Args:
        record_fields: 飞书记录的 fields 字典
        primary_keys: 主键字段名列表

    Returns:
        主键值元组，可用于字典 key 去重
    """
    values = []
    for key in primary_keys:
        value = record_fields.get(key)
        values.append(_extract_text(value))
    return tuple(values)


def _extract_text(value: Any) -> str:
    """从飞书字段值中提取纯文本。

    飞书字段类型与返回格式对应关系：
    - 多行文本: [{"text": "..."}]
    - 单选: {"name": "..."} 或 直接字符串
    - 数字: 直接数字
    - 超链接: {"link": "...", "text": "..."}
    """
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, (int, float)):
        return str(value)
    if isinstance(value, list) and value:
        first = value[0]
        if isinstance(first, dict):
            return first.get("text", "")
        return str(first)
    if isinstance(value, dict):
        # 单选字段
        if "name" in value:
            return str(value["name"])
        # 超链接字段
        if "text" in value:
            return str(value["text"])
        # 日期时间戳
        if "date" in value:
            return str(value["date"])
    return str(value)
