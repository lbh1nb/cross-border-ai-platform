"""批量发送 5 张审批卡片到飞书群，用于测试审批闭环。

使用库存预警表里真实的 ASIN，每张金额和业务类型不同，覆盖多种测试场景。
"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.feishu.application_bot import application_bot
from src.feishu.bitable import bitable_client
from src.feishu.card_templates import build_approval_card
from src.config import settings


def main() -> None:
    # 查询库存预警表前 5 条真实记录
    records = bitable_client.query_records(settings.feishu_table_id_inventory)
    print(f"库存预警表共 {len(records)} 条记录，取前 5 条发送审批卡片\n")

    # 5 种测试场景：金额不同、业务类型不同
    scenarios = [
        {"amount": 8500.0, "biz_type": "选品采购", "title": "户外折叠椅采购审批", "desc": "该选品预估采购金额超过 5000 美金，需审批后才能下单采购。"},
        {"amount": 12000.0, "biz_type": "库存补货", "title": "热卖商品紧急补货", "desc": "库存预警等级为'紧急'，需立即补货避免断货。"},
        {"amount": 3200.0, "biz_type": "选品采购", "title": "新品试销采购", "desc": "新品小批量试销，金额未超阈值但需主管确认。"},
        {"amount": 15600.0, "biz_type": "库存补货", "title": "Prime Day 备货审批", "desc": "Prime Day 大促前备货，采购金额较大，需财务审批。"},
        {"amount": 6800.0, "biz_type": "选品采购", "title": "夏季新品采购审批", "desc": "夏季新品上市，预估采购金额超阈值，需审批。"},
    ]

    success_count = 0
    for i, (record, scenario) in enumerate(zip(records[:5], scenarios), 1):
        fields = record.get("fields", {})
        asin = fields.get("ASIN", "")
        if isinstance(asin, list) and asin:
            asin = asin[0].get("text", "") if isinstance(asin[0], dict) else str(asin[0])

        card = build_approval_card(
            biz_type=scenario["biz_type"],
            biz_id=asin,
            title=scenario["title"],
            amount=scenario["amount"],
            description=scenario["desc"],
            operator="系统自动触发",
        )
        result = application_bot.send_card(card)
        status = "✓ 成功" if result else "✗ 失败"
        print(f"卡片 {i}: ASIN={asin}, 金额=${scenario['amount']:,.2f}, 类型={scenario['biz_type']} → {status}")
        if result:
            success_count += 1

    print(f"\n发送完成: {success_count}/5 张卡片成功")
    print("请在飞书群查看审批卡片，点击'通过'或'拒绝'按钮测试闭环。")


if __name__ == "__main__":
    main()
