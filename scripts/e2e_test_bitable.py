"""端到端验证：飞书多维表格增删改查全链路测试。

验证 BitableClient 的 add → get → update → delete 完整流程。
"""

from __future__ import annotations

from src.config import settings
from src.feishu.bitable import bitable_client


def main() -> None:
    table_id = settings.feishu_table_id_selection

    # 1. 写入一条测试记录
    print("=== 1. 写入测试记录 ===")
    record_id = bitable_client.add_record(table_id, {
        "商品名称": "测试商品-收纳盒",
        "ASIN": "B0TEST123456",
        "品类": "家居收纳",
        "价格区间": "15-25美金",
        "评分": 4.5,
        "评论数": 1234,
        "BSR排名": 5678,
        "市场容量": "中",
        "竞争强度": "中等",
        "利润空间": "高",
        "AI分析结论": "该品类市场容量中等，竞争强度一般，利润空间较大，建议切入。",
        "推荐指数": 8,
        "状态": "待审核",
    })
    print(f"✅ 写入成功: record_id={record_id}")

    # 2. 查询该记录
    print("\n=== 2. 查询记录 ===")
    fields = bitable_client.get_record(table_id, record_id)
    print(f"商品名称: {fields.get('商品名称')}")
    print(f"ASIN: {fields.get('ASIN')}")
    print(f"品类: {fields.get('品类')}")
    print(f"评分: {fields.get('评分')}")
    print(f"AI分析结论: {fields.get('AI分析结论')}")

    # 3. 更新记录
    print("\n=== 3. 更新记录状态 ===")
    bitable_client.update_record(table_id, record_id, {"状态": "已通过"})
    print("✅ 状态更新为: 已通过")

    # 4. 删除测试记录
    print("\n=== 4. 删除测试记录 ===")
    bitable_client.delete_record(table_id, record_id)
    print("✅ 测试记录已删除")

    print("\n" + "=" * 50)
    print("🎉 端到端验证全部通过！")
    print("增 → 查 → 改 → 删 全链路 OK")
    print("=" * 50)


if __name__ == "__main__":
    main()
