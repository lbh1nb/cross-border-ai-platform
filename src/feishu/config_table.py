"""采集配置表初始化：创建表 + 写入默认 15 条家具采集配置。

用法：
    python -m src.feishu.config_table

功能：
1. 在飞书多维表格中创建"采集配置"表（含字段：品类/平台/采集数量/优先级/启用状态/备注/更新时间）
2. 写入 15 条默认配置（5 个家具品类 × 3 个跨境电商平台）
3. 输出 table_id 提示用户填入 .env

企业自定义流程：
- 家具企业：直接使用默认 15 条配置
- 非家具企业：在飞书表格中停用默认配置，添加自己的品类（如"蓝牙耳机"/"美妆"等）
"""

from __future__ import annotations

from datetime import datetime

from src.feishu.bitable import bitable_client
from src.feishu.table_schema import COLLECTION_CONFIG_TABLE_FIELDS
from src.observability.logger import get_logger

logger = get_logger()


# ============================================================
# 默认采集配置：5 个家具品类 × 3 个平台 = 15 条
# 家具跨境电商企业可直接使用；非家具企业可在飞书表格中自定义
# ============================================================
DEFAULT_CONFIG_RECORDS: list[dict] = [
    # 家居收纳品类
    {"品类": "家居收纳", "平台": "亚马逊", "采集数量": 5, "优先级": 5,
     "启用状态": "启用", "备注": "家具企业核心品类"},
    {"品类": "家居收纳", "平台": "沃尔玛", "采集数量": 5, "优先级": 4,
     "启用状态": "启用", "备注": ""},
    {"品类": "家居收纳", "平台": "Wayfair", "采集数量": 5, "优先级": 4,
     "启用状态": "启用", "备注": ""},

    # 厨房用品品类
    {"品类": "厨房用品", "平台": "亚马逊", "采集数量": 5, "优先级": 4,
     "启用状态": "启用", "备注": ""},
    {"品类": "厨房用品", "平台": "沃尔玛", "采集数量": 5, "优先级": 3,
     "启用状态": "启用", "备注": ""},
    {"品类": "厨房用品", "平台": "Wayfair", "采集数量": 5, "优先级": 3,
     "启用状态": "启用", "备注": ""},

    # 户外家具品类
    {"品类": "户外家具", "平台": "亚马逊", "采集数量": 5, "优先级": 5,
     "启用状态": "启用", "备注": "Wayfair 强项品类"},
    {"品类": "户外家具", "平台": "沃尔玛", "采集数量": 5, "优先级": 4,
     "启用状态": "启用", "备注": ""},
    {"品类": "户外家具", "平台": "Wayfair", "采集数量": 5, "优先级": 5,
     "启用状态": "启用", "备注": "Wayfair 主营品类，重点采集"},

    # 办公家具品类
    {"品类": "办公家具", "平台": "亚马逊", "采集数量": 5, "优先级": 4,
     "启用状态": "启用", "备注": ""},
    {"品类": "办公家具", "平台": "沃尔玛", "采集数量": 5, "优先级": 3,
     "启用状态": "启用", "备注": ""},
    {"品类": "办公家具", "平台": "Wayfair", "采集数量": 5, "优先级": 4,
     "启用状态": "启用", "备注": ""},

    # 卧室家具品类
    {"品类": "卧室家具", "平台": "亚马逊", "采集数量": 5, "优先级": 5,
     "启用状态": "启用", "备注": ""},
    {"品类": "卧室家具", "平台": "沃尔玛", "采集数量": 5, "优先级": 4,
     "启用状态": "启用", "备注": ""},
    {"品类": "卧室家具", "平台": "Wayfair", "采集数量": 5, "优先级": 5,
     "启用状态": "启用", "备注": ""},
]


def create_collection_config_table() -> str:
    """创建采集配置表。

    Returns:
        新创建的 table_id
    """
    logger.info("开始创建采集配置表...")
    table_id = bitable_client.create_table(
        table_name="采集配置",
        fields=COLLECTION_CONFIG_TABLE_FIELDS,
    )
    return table_id


def write_default_config(table_id: str) -> list[str]:
    """写入默认 15 条家具采集配置。

    Args:
        table_id: 采集配置表 ID

    Returns:
        新创建的 record_id 列表
    """
    now_ms = int(datetime.now().timestamp() * 1000)

    # 给每条记录加上更新时间
    records = []
    for record in DEFAULT_CONFIG_RECORDS:
        record_with_time = {**record, "更新时间": now_ms}
        records.append(record_with_time)

    logger.info(f"正在写入 {len(records)} 条默认采集配置...")
    record_ids = bitable_client.batch_add_records(table_id, records)
    logger.info(f"默认配置写入完成: {len(record_ids)} 条")
    return record_ids


def main() -> None:
    """创建采集配置表 + 写入默认配置。"""
    print("=" * 60)
    print("开始创建采集配置表并写入默认家具采集配置...")
    print("=" * 60)

    # 1. 创建表
    table_id = create_collection_config_table()
    print(f"\n✅ 采集配置表创建成功: {table_id}")

    # 2. 写入默认配置
    record_ids = write_default_config(table_id)
    print(f"✅ 默认配置写入成功: {len(record_ids)} 条")

    print("\n" + "=" * 60)
    print("✅ 全部完成！")
    print("=" * 60)
    print(f"\n请将以下 table_id 填入 .env 文件：")
    print(f"  FEISHU_TABLE_ID_COLLECTION_CONFIG={table_id}")
    print(f"\n飞书表格中可看到 15 条默认配置：")
    print(f"  - 5 个家具品类（家居收纳/厨房用品/户外家具/办公家具/卧室家具）")
    print(f"  - 3 个平台（亚马逊/沃尔玛/Wayfair）")
    print(f"\n企业自定义说明：")
    print(f"  - 非家具企业：在飞书表格中停用默认配置，添加自己的品类")
    print(f"  - 调整采集数量：直接修改飞书表格中的'采集数量'字段")
    print(f"  - 临时停用某条：将'启用状态'改为'停用'")


if __name__ == "__main__":
    main()
