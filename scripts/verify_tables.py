"""验证多维表格中的数据表列表。"""
from src.feishu.bitable import bitable_client

tables = bitable_client.list_tables()
print(f"多维表格中共有 {len(tables)} 张数据表：\n")
for t in tables:
    print(f"  表名: {t['name']}")
    print(f"  table_id: {t['table_id']}")
    print()

print("多维表格访问链接：")
print("https://ocndodd7lmyr.feishu.cn/base/ZZf6bIeiQav5QLs3UAfcHqBPnWg")
