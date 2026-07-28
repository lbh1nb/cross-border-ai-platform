"""硬规则异常检测器（v0.6.1 新增）。

设计思想：
- 不依赖 LLM，用确定性规则检测业务异常
- 检测维度：销量跌幅 > 30%、ACoS > 50%、库存可售天数 ≤ 7
- 检测结果同时供 LLM 分析（作为补充上下文）和预警卡片使用
- 与 LLM 分析互补：硬规则抓确定事实，LLM 做深度归因

为什么需要硬规则检测：
- LLM 可能漏判或夸大异常，硬规则提供可靠的兜底
- 速度快、成本低，无需调用 API
- 异常预警卡片可以独立于 LLM 推送，LLM 失败时也能告警

使用方式：
    from src.ai.agents.anomaly_detector import detect_anomalies

    anomalies = detect_anomalies(today_sales, yesterday_sales)
    if anomalies:
        # 自动推送红色预警卡片
"""

from __future__ import annotations

from typing import Any

from src.observability.logger import get_logger

logger = get_logger()


# ============ 阈值常量（业务规则） ============
SALES_DROP_THRESHOLD = 0.30  # 销量跌幅超过 30% 视为异常
ACOS_HIGH_THRESHOLD = 0.50   # ACoS 超过 50% 视为低效
INVENTORY_CRITICAL_DAYS = 7  # 可售天数 ≤ 7 视为紧急


def detect_anomalies(
    current_sales: list[dict[str, Any]],
    previous_sales: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """检测业务异常（销量跌幅/ACoS过高）。

    Args:
        current_sales: 当天销售记录列表，每条含 平台/销售额/订单数/ACoS 等字段
        previous_sales: 前一天销售记录列表（可选，用于环比跌幅检测）

    Returns:
        异常列表，每条含：
        - type: 异常类型（sales_drop / acos_high）
        - platform: 平台名
        - detail: 详细描述
        - severity: 严重程度（warning / critical）
        - metric: 关键指标值
    """
    if not current_sales:
        return []

    anomalies: list[dict[str, Any]] = []

    # 构建前一天 平台 -> 销售额 映射，用于环比计算
    prev_map: dict[str, float] = {}
    if previous_sales:
        for r in previous_sales:
            platform = _safe_str(r.get("平台"))
            sales = _safe_float(r.get("销售额"))
            if platform and sales > 0:
                prev_map[platform] = sales

    for r in current_sales:
        platform = _safe_str(r.get("平台"))
        if not platform:
            continue

        sales = _safe_float(r.get("销售额"))
        orders = _safe_int(r.get("订单数"))
        acos = _safe_float(r.get("ACoS"))

        # 1. 销量跌幅检测：销售额环比下跌 > 30%
        prev_sales = prev_map.get(platform, 0.0)
        if prev_sales > 0 and sales > 0:
            drop_pct = (prev_sales - sales) / prev_sales
            if drop_pct >= SALES_DROP_THRESHOLD:
                anomalies.append({
                    "type": "sales_drop",
                    "platform": platform,
                    "detail": (
                        f"{platform} 销售额从 ${prev_sales:.2f} 跌至 ${sales:.2f}，"
                        f"环比下跌 {drop_pct*100:.1f}%（阈值 {SALES_DROP_THRESHOLD*100:.0f}%）"
                    ),
                    "severity": "critical" if drop_pct >= 0.5 else "warning",
                    "metric": {
                        "previous_sales": prev_sales,
                        "current_sales": sales,
                        "drop_pct": round(drop_pct, 4),
                    },
                })
                logger.warning(
                    f"异常检测：{platform} 销量跌幅 {drop_pct*100:.1f}%"
                )

        # 2. ACoS 过高检测：ACoS > 50%
        if acos > ACOS_HIGH_THRESHOLD:
            anomalies.append({
                "type": "acos_high",
                "platform": platform,
                "detail": (
                    f"{platform} ACoS={acos*100:.1f}%（阈值 {ACOS_HIGH_THRESHOLD*100:.0f}%），"
                    f"广告投放效率低，建议优化关键词"
                ),
                "severity": "warning",
                "metric": {"acos": acos},
            })
            logger.warning(
                f"异常检测：{platform} ACoS={acos*100:.1f}% 过高"
            )

    logger.info(
        f"异常检测完成：扫描 {len(current_sales)} 条销售记录，"
        f"发现 {len(anomalies)} 条异常"
    )
    return anomalies


def detect_inventory_anomalies(
    inventory_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    """检测库存异常（可售天数 ≤ 7 紧急断货风险）。

    与销售异常检测分离，因为输入数据源不同（库存预警表 vs 销售日报表）。

    Args:
        inventory_records: 库存预警记录列表

    Returns:
        库存异常列表，每条含 type=inventory_critical
    """
    anomalies: list[dict[str, Any]] = []
    for r in inventory_records:
        platform = _safe_str(r.get("平台"))
        asin = _safe_str(r.get("ASIN"))
        days = _safe_int(r.get("可售天数"))
        if days <= INVENTORY_CRITICAL_DAYS:
            anomalies.append({
                "type": "inventory_critical",
                "platform": platform,
                "asin": asin,
                "detail": (
                    f"{platform} / {asin} 可售天数仅 {days} 天，"
                    f"紧急断货风险（阈值 {INVENTORY_CRITICAL_DAYS} 天）"
                ),
                "severity": "critical",
                "metric": {"days": days},
            })
    return anomalies


# ============ 辅助函数 ============
def _safe_float(value: Any) -> float:
    """安全转 float，失败返回 0。"""
    try:
        if value is None:
            return 0.0
        return float(value)
    except (TypeError, ValueError):
        return 0.0


def _safe_int(value: Any) -> int:
    """安全转 int，失败返回 0。"""
    try:
        if value is None:
            return 0
        return int(float(value))
    except (TypeError, ValueError):
        return 0


def _safe_str(value: Any) -> str:
    """安全转 str，处理飞书多行文本/单选等格式。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, list) and value:
        # 飞书单选字段返回 [{"text": "亚马逊"}]
        first = value[0]
        if isinstance(first, dict):
            return str(first.get("text") or first.get("name") or "").strip()
        return str(first).strip()
    if isinstance(value, dict):
        return str(value.get("text") or value.get("name") or "").strip()
    return str(value).strip()
