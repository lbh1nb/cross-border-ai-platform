"""多维表格初始化脚本：创建四张业务表。

用法：
    python -m src.feishu.init_tables

前置条件：
    1. .env 中已配置 FEISHU_BITABLE_APP_TOKEN
    2. 已创建一张空的多维表格（飞书 > 新建 > 多维表格）
    3. 从多维表格 URL 中提取 App Token 填入 .env
"""

from __future__ import annotations

from src.feishu.bitable import bitable_client
from src.observability.logger import get_logger

logger = get_logger()


def main() -> None:
    """创建四张业务表并输出 table_id。"""
    print("=" * 60)
    print("开始创建多维表格数据表...")
    print("=" * 60)

    result = bitable_client.create_all_tables()

    print("\n" + "=" * 60)
    print("✅ 所有数据表创建成功！")
    print("=" * 60)
    print("\n请将以下 table_id 填入 .env 文件：\n")

    env_mapping = {
        "选品池": "FEISHU_TABLE_ID_SELECTION",
        "Listing库": "FEISHU_TABLE_ID_LISTING",
        "销售日报": "FEISHU_TABLE_ID_DAILY_REPORT",
        "库存预警": "FEISHU_TABLE_ID_INVENTORY",
    }

    for table_name, table_id in result.items():
        env_key = env_mapping.get(table_name, "")
        print(f"  {table_name}: {table_id}")
        if env_key:
            print(f"    → .env: {env_key}={table_id}")

    print("\n下一步：将这些 table_id 复制到 .env 文件中。")


if __name__ == "__main__":
    main()
