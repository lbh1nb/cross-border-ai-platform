"""验证脚本：查询库存预警表所有记录的审批状态。"""
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from src.feishu.bitable import bitable_client
from src.config import settings


def main() -> None:
    records = bitable_client.query_records(settings.feishu_table_id_inventory)
    print(f"库存预警表共 {len(records)} 条记录\n")
    print(f"{'ASIN':<15} {'审批状态':<10} {'record_id'}")
    print("-" * 50)
    for r in records:
        fields = r.get("fields", {})
        asin = fields.get("ASIN", "")
        if isinstance(asin, list) and asin:
            asin = asin[0].get("text", "") if isinstance(asin[0], dict) else str(asin[0])
        status = fields.get("审批状态", "")
        if isinstance(status, dict):
            status = status.get("name", "")
        print(f"{asin:<15} {status:<10} {r.get('record_id', '')}")


if __name__ == "__main__":
    main()
