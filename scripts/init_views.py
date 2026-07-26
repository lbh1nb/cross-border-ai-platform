"""一键脚本：为飞书多维表格创建业务视图。

创建三张专用视图：
1. 销售总览视图（在销售日报表上）：重点显示销售额/订单数/异常标记/AI洞察
2. 预警看板视图（在库存预警表上）：重点显示可售天数/预警等级/建议采购量
3. 选品决策视图（在选品池表上）：重点显示评分/利润空间/推荐指数

飞书视图 API 限制：
- 可以创建视图，但筛选/排序配置 API 较复杂
- 字段显示/隐藏通过单独 API 控制
- 本脚本采用渐进式策略：先创建视图，再隐藏非关键字段

调用方式：
    本脚本由 scripts/install.ps1 自动调用，业务用户无需手动执行。
    IT/运维人员如需单独运行，可执行：python scripts/init_views.py
"""

from __future__ import annotations

import sys
import os

# 把项目根目录加入 sys.path，确保能找到 src 包
# （python scripts/xxx.py 时默认只把 scripts/ 目录加入 sys.path）
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
os.chdir(project_root)
sys.path.insert(0, project_root)

from src.config import settings
from src.feishu.bitable import bitable_client
from src.observability.logger import get_logger

logger = get_logger()


# ============================================================
# 视图配置：每张表的视图名 + 关键字段（其他字段隐藏）
# ============================================================
VIEW_CONFIGS = [
    {
        "table_name": "销售日报",
        "table_id_key": "feishu_table_id_daily_report",
        "view_name": "销售总览",
        "visible_fields": ["日期", "平台", "销售额", "订单数", "ACoS", "异常标记", "AI洞察"],
    },
    {
        "table_name": "库存预警",
        "table_id_key": "feishu_table_id_inventory",
        "view_name": "预警看板",
        "visible_fields": ["ASIN", "商品名称", "SKU", "平台", "可售天数", "预警等级", "建议采购量", "预估采购金额", "审批状态"],
    },
    {
        "table_name": "选品池",
        "table_id_key": "feishu_table_id_selection",
        "view_name": "选品决策",
        "visible_fields": ["商品名称", "ASIN", "品类", "来源平台", "价格区间", "评分", "评论数", "市场容量", "竞争强度", "利润空间", "推荐指数", "状态"],
    },
]


def apply_field_visibility(table_id: str, view_id: str, visible_fields: list[str]) -> None:
    """配置视图的字段可见性，隐藏非关键字段。

    飞书 API 通过 PATCH /views/{view_id} 接口的 property.hidden_fields 字段
    一次性传入要隐藏的字段 ID 列表（最多 100 个）。

    Args:
        table_id: 飞书表格 ID
        view_id: 视图 ID
        visible_fields: 要显示的字段名列表（其他字段隐藏）
    """
    try:
        all_fields = bitable_client.list_fields(table_id)
        print(f"  配置字段显示: 显示 {len(visible_fields)} 个关键字段，隐藏其他 {len(all_fields) - len(visible_fields)} 个字段")

        # 收集要隐藏的字段 ID
        hidden_field_ids: list[str] = []
        for field in all_fields:
            field_id = field.get("field_id")
            field_name = field.get("field_name")
            if field_name not in visible_fields and field_id:
                hidden_field_ids.append(field_id)

        if not hidden_field_ids:
            print(f"  ✅ 字段配置完成: 无需隐藏字段")
            return

        # 一次性传入所有要隐藏的字段 ID（飞书 API 限制单次最多 100 个）
        settings_payload = {
            "property": {
                "hidden_fields": hidden_field_ids[:100]
            }
        }
        bitable_client.patch_view(table_id, view_id, settings_payload)
        print(f"  ✅ 字段配置完成: 已隐藏 {len(hidden_field_ids[:100])} 个字段")
    except Exception as e:
        print(f"  ⚠️  字段配置部分失败: {e}")


def create_view_for_table(table_id: str, table_name: str, view_name: str, visible_fields: list[str]) -> str | None:
    """为单张表创建视图并配置字段显示。

    若视图已存在，仍会重新应用字段隐藏配置（修复历史残缺视图）。

    Args:
        table_id: 飞书表格 ID
        table_name: 表名（用于日志）
        view_name: 视图名称
        visible_fields: 要显示的字段名列表（其他字段隐藏）

    Returns:
        视图 ID，失败返回 None
    """
    print(f"\n[{table_name}] 处理视图: {view_name}")

    # 1. 检查视图是否已存在
    view_id: str | None = None
    existing_views = bitable_client.list_views(table_id)
    for v in existing_views:
        if v.get("view_name") == view_name:
            view_id = v.get("view_id")
            print(f"  ℹ️  视图已存在: view_id={view_id}，重新应用字段配置")
            break

    # 2. 视图不存在则创建
    if not view_id:
        try:
            view_id = bitable_client.create_view(table_id, view_name, view_type="grid")
            print(f"  ✅ 视图创建成功: view_id={view_id}")
        except Exception as e:
            print(f"  ❌ 视图创建失败: {e}")
            return None

    # 3. 无论新建还是已存在，都应用字段可见性配置
    if view_id:
        apply_field_visibility(table_id, view_id, visible_fields)

    return view_id


def main() -> None:
    """主入口：创建所有业务视图。"""
    print("=" * 60)
    print("为飞书多维表格创建业务视图")
    print("=" * 60)

    success_count = 0
    fail_count = 0

    for config in VIEW_CONFIGS:
        table_name = config["table_name"]
        table_id_key = config["table_id_key"]
        view_name = config["view_name"]
        visible_fields = config["visible_fields"]

        table_id = getattr(settings, table_id_key, "")
        if not table_id:
            print(f"\n[{table_name}] 未配置 table_id ({table_id_key})，跳过")
            fail_count += 1
            continue

        view_id = create_view_for_table(table_id, table_name, view_name, visible_fields)
        if view_id:
            success_count += 1
        else:
            fail_count += 1

    print("\n" + "=" * 60)
    print(f"视图创建完成: 成功 {success_count} / 失败 {fail_count}")
    print("=" * 60)
    print("\n打开飞书多维表格，切换到对应视图查看效果：")
    print("  - 销售日报表 -> '销售总览'视图")
    print("  - 库存预警表 -> '预警看板'视图")
    print("  - 选品池表   -> '选品决策'视图")
    print("\n注意：如需进一步配置筛选/排序，可在飞书网页端手动调整。")


if __name__ == "__main__":
    main()
