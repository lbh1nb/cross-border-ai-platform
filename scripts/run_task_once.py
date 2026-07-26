"""手动触发任务脚本：不等待定时触发，立即执行一次。

用法：
    python -m scripts.run_task_once collect          # 手动触发选品采集
    python -m scripts.run_task_once inventory_check   # 手动触发库存检查
    python -m scripts.run_task_once generate_inventory # 生成 Mock 库存数据
"""

from __future__ import annotations

import sys


def main() -> None:
    if len(sys.argv) < 2:
        print("用法：")
        print("  python -m scripts.run_task_once collect           # 选品采集")
        print("  python -m scripts.run_task_once inventory_check    # 库存检查")
        print("  python -m scripts.run_task_once generate_inventory # 生成Mock库存")
        sys.exit(1)

    command = sys.argv[1]

    if command == "collect":
        from src.scheduler.tasks import product_collection_task
        print("手动触发：选品采集任务")
        result = product_collection_task()
        print(f"\n任务完成，采集品类: {result}")

    elif command == "inventory_check":
        from src.scheduler.tasks import inventory_check_task
        print("手动触发：库存预警检查任务")
        count = inventory_check_task()
        print(f"\n任务完成，检查记录数: {count}")

    elif command == "generate_inventory":
        from src.mock import MockERP
        print("手动触发：生成 Mock 库存数据")
        erp = MockERP(seed=42)
        record_ids = erp.generate_inventory_data(count=10)
        print(f"\n任务完成，写入记录数: {len(record_ids)}")

    else:
        print(f"未知命令: {command}")
        sys.exit(1)


if __name__ == "__main__":
    main()
