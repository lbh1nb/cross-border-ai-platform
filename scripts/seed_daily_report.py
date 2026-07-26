"""生成销售日报模拟数据（7天 × 3平台 = 21条记录）。

用途：
    第4周 AI 日报功能上线前，用模拟数据填充飞书销售日报表，
    让销售日报卡片有数据可看，验证端到端流程。

数据策略：
    - 生成最近 7 天的数据
    - 每天 3 个平台（亚马逊/沃尔玛/Wayfair）
    - 共 21 条记录
    - 按主键"日期+平台"去重，重复运行不会产生重复数据
    - 含 2 条异常记录（销量下跌/ACoS过高）用于测试异常卡片展示

用法：
    python scripts/seed_daily_report.py

注意：
    第4周 AI 日报上线后，真实数据会按主键去重覆盖这些模拟数据。
"""

from __future__ import annotations

import random
import sys
from datetime import datetime, timedelta
from pathlib import Path

# 把项目根目录加入 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.config import settings
from src.feishu.bitable import bitable_client
from src.feishu.field_mapping import DAILY_REPORT_PRIMARY_KEYS
from src.feishu.sync_service import SyncResult, create_daily_report_sync_service
from src.observability.logger import get_logger

logger = get_logger()


# 3 个平台的基础数据（用于生成合理的模拟数据）
_PLATFORM_PROFILES = {
    "亚马逊": {
        "sales_range": (8000, 15000),    # 日销售额范围（美金）
        "orders_range": (80, 150),        # 日订单数范围
        "acos_range": (0.15, 0.25),       # ACoS 范围（15%-25%）
        "return_rate": (0.02, 0.05),      # 退货率范围
    },
    "沃尔玛": {
        "sales_range": (3000, 6000),
        "orders_range": (30, 60),
        "acos_range": (0.10, 0.20),
        "return_rate": (0.03, 0.06),
    },
    "Wayfair": {
        "sales_range": (2000, 4500),
        "orders_range": (15, 40),
        "acos_range": (0.08, 0.18),
        "return_rate": (0.01, 0.04),
    },
}

# AI 洞察模板（随机选一条）
_AI_INSIGHTS = [
    "销售额环比增长 8%，主要由家居收纳品类驱动。",
    "ACoS 控制在合理区间，广告投放效率良好。",
    "退货率略高于行业平均，建议关注产品质量。",
    "户外家具品类表现突出，建议增加库存。",
    "订单量稳定，无异常波动。",
    "建议优化关键词匹配方式，降低广告成本。",
    "Wayfair 平台增长潜力大，可考虑加大投入。",
]


def _generate_one_record(date: datetime, platform: str, force_abnormal: str = "") -> dict:
    """生成单条销售日报记录。

    Args:
        date: 日期
        platform: 平台名
        force_abnormal: 强制异常类型（空字符串=正常）

    Returns:
        飞书表格字段 dict
    """
    profile = _PLATFORM_PROFILES[platform]
    sales = round(random.uniform(*profile["sales_range"]), 2)
    orders = random.randint(*profile["orders_range"])
    acos = round(random.uniform(*profile["acos_range"]), 4)
    ad_spend = round(sales * acos, 2)
    returns = int(orders * random.uniform(*profile["return_rate"]))

    # 异常标记
    if force_abnormal == "销量下跌":
        sales = round(sales * 0.5, 2)  # 销量减半
        orders = int(orders * 0.6)
        abnormal = "销量下跌"
        ai_insight = f"⚠️ {platform} 销量异常下跌 50%，建议排查关键词排名和广告投放。"
    elif force_abnormal == "ACoS过高":
        acos = round(random.uniform(0.35, 0.45), 4)  # ACoS 飙升到 35%-45%
        ad_spend = round(sales * acos, 2)
        abnormal = "ACoS过高"
        ai_insight = f"⚠️ {platform} ACoS 异常升高至 {acos*100:.1f}%，建议优化广告关键词。"
    else:
        abnormal = "正常"
        ai_insight = random.choice(_AI_INSIGHTS)

    # 日期转毫秒时间戳（飞书 DATETIME 字段格式）
    date_timestamp = int(datetime(date.year, date.month, date.day).timestamp() * 1000)

    return {
        "日期": date_timestamp,
        "平台": platform,
        "销售额": sales,
        "订单数": orders,
        "广告花费": ad_spend,
        "ACoS": acos,
        "退货数": returns,
        "库存天数": random.randint(15, 60),
        "AI洞察": ai_insight,
        "异常标记": abnormal,
    }


def generate_daily_report_data(days: int = 7) -> list[dict]:
    """生成最近 N 天的销售日报数据。

    Args:
        days: 生成多少天的数据

    Returns:
        飞书表格记录列表
    """
    records: list[dict] = []
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)

    for day_offset in range(days):
        date = today - timedelta(days=day_offset)
        for platform in _PLATFORM_PROFILES:
            # 第 3 天的亚马逊强制异常（销量下跌）
            if day_offset == 2 and platform == "亚马逊":
                record = _generate_one_record(date, platform, force_abnormal="销量下跌")
            # 第 5 天的沃尔玛强制异常（ACoS过高）
            elif day_offset == 4 and platform == "沃尔玛":
                record = _generate_one_record(date, platform, force_abnormal="ACoS过高")
            else:
                record = _generate_one_record(date, platform)
            records.append(record)

    return records


def main() -> None:
    """主函数：生成 7 天模拟数据并同步到飞书销售日报表。"""
    print("=" * 60)
    print("  销售日报模拟数据生成器")
    print("=" * 60)

    # 检查配置
    table_id = settings.feishu_table_id_daily_report
    if not table_id:
        print("[错误] 销售日报表 ID 未配置，请在 .env 中设置 FEISHU_TABLE_ID_DAILY_REPORT")
        return

    print(f"  目标表格 ID: {table_id}")
    print(f"  生成数据: 最近 7 天 × 3 平台 = 21 条记录")
    print(f"  含 2 条异常记录（销量下跌 + ACoS过高）")
    print()

    # 生成数据
    records = generate_daily_report_data(days=7)
    print(f"  已生成 {len(records)} 条模拟数据")

    # 用增量同步服务写入（按"日期+平台"主键去重）
    print("  正在同步到飞书表格...")
    sync_service = create_daily_report_sync_service()
    result: SyncResult = sync_service.sync_records(
        records, primary_keys=DAILY_REPORT_PRIMARY_KEYS
    )

    print()
    print("=" * 60)
    print("  同步结果")
    print("=" * 60)
    print(f"  新增: {result.new_count} 条")
    print(f"  更新: {result.update_count} 条")
    print(f"  跳过: {result.skip_count} 条")
    print(f"  失败: {result.fail_count} 条")
    print(f"  总计: {result.total} 条")
    print()

    if result.fail_count == 0:
        print("  ✅ 全部同步成功！")
        print()
        print("  下一步：")
        print("  1. 打开飞书销售日报表 → 切换到'销售总览'视图查看数据")
        print("  2. 运行 python scripts/test_cards.py 重新发送销售日报卡片")
        print("  3. 点击卡片'查看销售日报'按钮，应有数据可看")
    else:
        print("  ❌ 部分同步失败，请查看日志：logs/app.log")


if __name__ == "__main__":
    main()
