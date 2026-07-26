"""飞书 Webhook 机器人手动测试脚本。

测试三种消息类型是否能正常发送到飞书群：
1. 文本消息
2. 富文本消息
3. 交互卡片消息（库存预警卡片）

调用方式：
    本脚本由 IT/运维人员用于验证 Webhook 配置是否正确。
    业务用户无需手动执行。

    python scripts/test_bot.py
"""

from __future__ import annotations

import os
import sys

# 把项目根目录加入 sys.path（与 start_scheduler.py 保持一致）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)
sys.path.insert(0, project_root)

from src.feishu.card_templates import build_inventory_alert_card
from src.feishu.feishu_bot import feishu_bot


def test_text_message() -> bool:
    """测试1：发送纯文本消息。"""
    print("\n[测试 1] 发送纯文本消息...")
    text = "【AI 运营中台测试】这是一条库存预警测试消息，请忽略。"
    return feishu_bot.send_text(text)


def test_rich_text_message() -> bool:
    """测试2：发送富文本消息。

    注意：飞书 Webhook 富文本只支持 text/a/at 三种标签，不支持 b（加粗）。
    要加粗效果需用交互卡片的 lark_md 格式。
    """
    print("\n[测试 2] 发送富文本消息...")
    return feishu_bot.send_rich_text(
        title="【AI 运营中台】库存预警测试通知",
        content=[
            [{"tag": "text", "text": "测试商品A "}],
            [
                {"tag": "text", "text": "可售天数：5 天，预警等级：紧急"},
            ],
            [
                {"tag": "text", "text": "详情请查看 "},
                {"tag": "a", "text": "飞书多维表格", "href": "https://feishu.cn"},
            ],
        ],
    )


def test_card_message() -> bool:
    """测试3：发送库存预警交互卡片。"""
    print("\n[测试 3] 发送库存预警交互卡片...")
    card = build_inventory_alert_card(
        asin="B08TEST123",
        product_name="测试商品 - 户外折叠椅",
        sku="TEST-CHAIR-001",
        platform="亚马逊",
        stock_days=5,
        alert_level="紧急",
        current_stock=25,
        daily_sales=5.0,
        suggested_purchase=100,
    )
    return feishu_bot.send_card(card)


def main() -> None:
    """主入口：依次测试三种消息类型。"""
    print("=" * 60)
    print("飞书 Webhook 机器人手动测试")
    print("=" * 60)

    if not feishu_bot.is_configured:
        print("\n[错误] Webhook URL 未配置！")
        print("       请先在 .env 文件中设置 FEISHU_WEBHOOK_URL")
        print("       获取方式：飞书群设置 → 群机器人 → 添加自定义机器人 → 复制 Webhook 地址")
        return

    print(f"\nWebhook URL 已配置: {feishu_bot._webhook_url[:50]}...")

    results = [
        ("纯文本消息", test_text_message()),
        ("富文本消息", test_rich_text_message()),
        ("交互卡片消息", test_card_message()),
    ]

    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    for name, success in results:
        status = "✅ 成功" if success else "❌ 失败"
        print(f"  {name}: {status}")

    success_count = sum(1 for _, s in results if s)
    print(f"\n总计: {success_count}/{len(results)} 成功")

    if success_count == len(results):
        print("\n🎉 全部测试通过！Webhook 机器人配置正确。")
    else:
        print("\n⚠️  部分测试失败，请检查：")
        print("   1. Webhook URL 是否正确")
        print("   2. 消息是否包含安全关键词（库存/预警/选品/日报/AI/告警）")
        print("   3. 网络是否能访问 open.feishu.cn")
        print("   4. 查看 logs/app.log 获取详细错误信息")


if __name__ == "__main__":
    main()
