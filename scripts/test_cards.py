"""端到端测试：发送各种带按钮的卡片到飞书群。

测试内容：
1. 选品报告卡片（含"查看选品池"按钮，url 跳转）
2. 销售日报卡片（含"查看销售日报"按钮，url 跳转）
3. 审批卡片（含"通过/拒绝"回调按钮，触发 card.action.trigger）

用法：
    python scripts/test_cards.py

注意：
    审批卡片的回调按钮需要配置飞书应用机器人 + ngrok 才能真正接收回调。
    若仅配置了 Webhook 自定义机器人，按钮点击会提示"应用未配置"。
    选品报告和日报卡片的 url 按钮可正常跳转，无需回调服务。

前置条件：
    - .env 已配置 FEISHU_WEBHOOK_URL
    - .env 已配置 FEISHU_TENANT_DOMAIN
"""

from __future__ import annotations

import sys
from datetime import datetime
from pathlib import Path

# 把项目根目录加入 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.feishu.card_templates import (
    build_approval_card,
    build_daily_report_card,
    build_inventory_alert_card,
    build_selection_report_card,
    build_table_url,
)
from src.feishu.feishu_bot import feishu_bot


def test_selection_report_card() -> bool:
    """测试1：发送选品报告卡片。"""
    print("\n[测试 1] 发送选品报告卡片...")
    today = datetime.now().strftime("%Y-%m-%d")
    card = build_selection_report_card(
        date=today,
        total_configs=15,
        new_count=60,
        update_count=15,
        skip_count=0,
        fail_count=0,
        top_categories=["家居收纳", "厨房用品", "户外家具"],
    )
    return feishu_bot.send_card(card)


def test_daily_report_card_normal() -> bool:
    """测试2：发送正常销售日报卡片。"""
    print("\n[测试 2] 发送正常销售日报卡片（绿色标题）...")
    today = datetime.now().strftime("%Y-%m-%d")
    card = build_daily_report_card(
        date=today,
        total_sales=12500.50,
        total_orders=120,
        avg_acos=18.5,
        abnormal_count=0,
    )
    return feishu_bot.send_card(card)


def test_daily_report_card_abnormal() -> bool:
    """测试3：发送异常销售日报卡片。"""
    print("\n[测试 3] 发送异常销售日报卡片（橙色标题）...")
    today = datetime.now().strftime("%Y-%m-%d")
    card = build_daily_report_card(
        date=today,
        total_sales=9800.0,
        total_orders=95,
        avg_acos=25.0,
        abnormal_count=3,
        ai_insight="今日 ACoS 异常升高，主要由户外家具品类广告投放效率下降导致。建议优化关键词匹配方式。",
    )
    return feishu_bot.send_card(card)


def test_approval_card() -> bool:
    """测试4：发送审批卡片（带回调按钮）。

    注意：此卡片的"通过/拒绝"按钮使用 value 字段触发回调，
    需要飞书应用机器人 + ngrok 配置才能真正接收回调。
    仅 Webhook 自定义机器人时，点击会提示"应用未配置"。
    """
    print("\n[测试 4] 发送审批卡片（带回调按钮）...")
    print("  注意：审批按钮需要飞书应用机器人 + ngrok 才能接收回调")
    print("        若仅 Webhook 机器人，按钮点击会提示应用未配置")
    table_url = build_table_url()
    card = build_approval_card(
        biz_type="选品采购",
        biz_id="B08X4ABC",
        title="户外折叠椅采购审批",
        amount=8500.0,
        description="单笔采购金额 8500 美金，超过 5000 美金阈值，需审批后下单",
        operator="系统自动触发",
        table_url=table_url,
    )
    return feishu_bot.send_card(card)


def test_inventory_alert_card() -> bool:
    """测试5：发送库存预警卡片（对照，08-04 已实现）。"""
    print("\n[测试 5] 发送库存预警卡片（对照）...")
    card = build_inventory_alert_card(
        asin="B08X4ABC",
        product_name="测试商品 - 户外折叠椅",
        sku="CHAIR-001",
        platform="亚马逊",
        stock_days=5,
        alert_level="紧急",
        current_stock=25,
        daily_sales=5.0,
        suggested_purchase=100,
    )
    return feishu_bot.send_card(card)


def main() -> None:
    """主函数：发送 5 张测试卡片。"""
    print("=" * 60)
    print("  飞书卡片端到端测试")
    print("=" * 60)

    if not feishu_bot.is_configured:
        print("\n[错误] Webhook URL 未配置！")
        print("  请在 .env 文件中设置 FEISHU_WEBHOOK_URL")
        return

    results = [
        ("选品报告卡片", test_selection_report_card()),
        ("销售日报卡片（正常）", test_daily_report_card_normal()),
        ("销售日报卡片（异常）", test_daily_report_card_abnormal()),
        ("审批卡片（带回调按钮）", test_approval_card()),
        ("库存预警卡片（对照）", test_inventory_alert_card()),
    ]

    print()
    print("=" * 60)
    print("  测试结果")
    print("=" * 60)
    for name, success in results:
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {status}  {name}")

    success_count = sum(1 for _, s in results if s)
    print()
    print(f"  总计: {success_count}/{len(results)} 成功")

    if success_count == len(results):
        print()
        print("  ✅ 所有卡片发送成功！")
        print()
        print("  下一步验证：")
        print("  - 选品报告/日报/预警卡片的按钮：点击后应直接在飞书内打开多维表格")
        print("  - 审批卡片的通过/拒绝按钮：")
        print("    若已配置飞书应用机器人 + ngrok，点击后查看 callback_server 日志")
        print("    若仅 Webhook 机器人，点击会提示应用未配置（正常现象）")
    else:
        print()
        print("  ❌ 部分卡片发送失败，请检查 logs/app.log 排查原因")
        print("  常见问题：")
        print("  - 11232: 频率限制（5次/秒），等 1 分钟后重试")
        print("  - 9499: 安全关键词不匹配，确认消息含 '库存 预警 选品 日报 AI 告警'")


if __name__ == "__main__":
    main()
