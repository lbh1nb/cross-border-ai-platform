"""一次性脚本：给现有选品池表添加"来源平台"字段。

背景：
旧版选品池表创建时没有"来源平台"字段，新版数据结构需要该字段。
本脚本检查选品池表是否已有该字段，没有则添加。

用法：
    python -m scripts.add_platform_field
"""

from __future__ import annotations

from src.config import settings
from src.feishu.bitable import bitable_client
from src.feishu.table_schema import FieldType


def main() -> None:
    table_id = settings.feishu_table_id_selection
    print(f"选品池表 ID: {table_id}")

    # 1. 查询现有字段
    fields = bitable_client.list_fields(table_id)
    field_names = [f.get("field_name") for f in fields]
    print(f"\n现有字段: {field_names}")

    # 2. 检查是否已有"来源平台"字段
    if "来源平台" in field_names:
        print("\n✅ 选品池表已有'来源平台'字段，无需添加")
        return

    # 3. 添加"来源平台"字段
    print("\n正在添加'来源平台'字段...")
    field_def = {
        "field_name": "来源平台",
        "type": FieldType.SINGLE_SELECT,
        "property": {
            "options": [
                {"name": "亚马逊"},
                {"name": "沃尔玛"},
                {"name": "Wayfair"},
                {"name": "TikTok Shop"},
                {"name": "独立站"},
            ]
        },
    }
    field_id = bitable_client.add_field(table_id, field_def)
    print(f"\n✅ '来源平台'字段添加成功: field_id={field_id}")
    print("\n说明：历史记录的'来源平台'字段为空，新采集的记录会自动填入平台信息")


if __name__ == "__main__":
    main()
