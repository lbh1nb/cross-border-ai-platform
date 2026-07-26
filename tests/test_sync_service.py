"""同步服务单元测试：覆盖 SyncResult、SyncService、字段映射。

测试覆盖：
1. SyncResult 数据类的属性和方法
2. product_to_record 转换函数
3. extract_primary_values 主键提取
4. _extract_text 各种飞书字段格式解析
5. SyncService.sync_products 增量同步逻辑（mock bitable_client）
"""

from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest

from src.feishu.field_mapping import (
    SELECTION_PRIMARY_KEYS,
    INVENTORY_PRIMARY_KEYS,
    _extract_text,
    extract_primary_values,
    product_to_record,
)
from src.feishu.sync_service import SyncResult, SyncService
from src.pipeline.collectors import ProductInfo


# ============================================================
# SyncResult 数据类测试
# ============================================================
class TestSyncResult:
    """SyncResult 统计结果测试。"""

    def test_default_values(self):
        """默认值全为 0。"""
        result = SyncResult()
        assert result.new_count == 0
        assert result.update_count == 0
        assert result.skip_count == 0
        assert result.fail_count == 0
        assert result.total == 0
        assert result.errors == []

    def test_total_property(self):
        """total 属性应等于各项之和。"""
        result = SyncResult(
            new_count=10,
            update_count=5,
            skip_count=3,
            fail_count=2,
        )
        assert result.total == 20

    def test_str_representation(self):
        """__str__ 应包含表名和各项统计。"""
        result = SyncResult(
            table_name="选品池",
            new_count=10,
            update_count=5,
            skip_count=3,
            fail_count=2,
            duration_ms=1500,
        )
        s = str(result)
        assert "选品池" in s
        assert "新增 10" in s
        assert "更新 5" in s
        assert "跳过 3" in s
        assert "失败 2" in s
        assert "1500ms" in s


# ============================================================
# 字段映射函数测试
# ============================================================
class TestFieldMapping:
    """字段映射转换函数测试。"""

    def test_product_to_record_contains_all_fields(self):
        """product_to_record 应包含所有选品池字段。"""
        product = ProductInfo(
            name="测试商品",
            asin="B0TEST1234",
            category="家居收纳",
            platform="亚马逊",
            price_min=15.99,
            price_max=29.99,
            rating=4.5,
            review_count=500,
            bsr_rank=1000,
            url="https://www.amazon.com/dp/B0TEST1234",
            market_capacity="高",
            competition_level="中等",
            profit_margin="高",
        )

        record = product_to_record(product)

        assert record["商品名称"] == "测试商品"
        assert record["ASIN"] == "B0TEST1234"
        assert record["品类"] == "家居收纳"
        assert record["来源平台"] == "亚马逊"
        assert record["价格区间"] == "15.99-29.99美金"
        assert record["评分"] == 4.5
        assert record["评论数"] == 500
        assert record["BSR排名"] == 1000
        assert record["市场容量"] == "高"
        assert record["竞争强度"] == "中等"
        assert record["利润空间"] == "高"
        # 商品链接是 URL 字段，含 link 和 text
        assert record["商品链接"]["link"] == "https://www.amazon.com/dp/B0TEST1234"
        assert record["商品链接"]["text"] == "测试商品"

    def test_extract_primary_values_text_field(self):
        """从多行文本字段提取主键值。"""
        fields = {
            "ASIN": [{"text": "B0TEST1234", "type": "text"}],
            "来源平台": "亚马逊",
        }
        result = extract_primary_values(fields, ["ASIN", "来源平台"])
        assert result == ("B0TEST1234", "亚马逊")

    def test_extract_primary_values_single_select(self):
        """从单选字段提取主键值。"""
        fields = {
            "ASIN": "B0ABC",
            "来源平台": {"name": "沃尔玛"},
        }
        result = extract_primary_values(fields, ["ASIN", "来源平台"])
        assert result == ("B0ABC", "沃尔玛")

    def test_extract_primary_values_missing_field(self):
        """字段缺失时返回空字符串。"""
        fields = {"ASIN": "B0ABC"}
        result = extract_primary_values(fields, ["ASIN", "来源平台"])
        assert result == ("B0ABC", "")

    def test_extract_text_string(self):
        """_extract_text 解析字符串。"""
        assert _extract_text("hello") == "hello"

    def test_extract_text_number(self):
        """_extract_text 解析数字。"""
        assert _extract_text(42) == "42"
        assert _extract_text(3.14) == "3.14"

    def test_extract_text_text_field_list(self):
        """_extract_text 解析多行文本字段。"""
        value = [{"text": "hello", "type": "text"}]
        assert _extract_text(value) == "hello"

    def test_extract_text_single_select_dict(self):
        """_extract_text 解析单选字段（{"name": "..."}）。"""
        value = {"name": "亚马逊"}
        assert _extract_text(value) == "亚马逊"

    def test_extract_text_url_field(self):
        """_extract_text 解析超链接字段。"""
        value = {"link": "https://example.com", "text": "示例链接"}
        assert _extract_text(value) == "示例链接"

    def test_extract_text_none(self):
        """_extract_text 处理 None。"""
        assert _extract_text(None) == ""

    def test_primary_keys_config(self):
        """主键配置正确。"""
        assert SELECTION_PRIMARY_KEYS == ["ASIN", "来源平台"]
        assert INVENTORY_PRIMARY_KEYS == ["SKU"]


# ============================================================
# SyncService 增量同步逻辑测试（mock bitable_client）
# ============================================================
class TestSyncService:
    """SyncService 增量同步逻辑测试。"""

    @patch("src.feishu.sync_service.bitable_client")
    def test_sync_products_all_new(self, mock_client):
        """全部新增：现有表为空，所有商品都是新增。"""
        # 现有记录为空
        mock_client.query_records.return_value = []
        mock_client.batch_add_records.return_value = ["rec1", "rec2", "rec3"]

        service = SyncService(table_id="tbl1", table_name="选品池")
        products = [
            ProductInfo(name=f"商品{i}", asin=f"B0{i}", platform="亚马逊",
                       category="家居收纳",
                       price_min=10, price_max=20, rating=4.0, review_count=100,
                       bsr_rank=1000, url=f"https://a.com/{i}")
            for i in range(3)
        ]

        result = service.sync_products(products)

        assert result.new_count == 3
        assert result.update_count == 0
        assert result.skip_count == 0
        assert result.fail_count == 0
        mock_client.batch_add_records.assert_called_once()

    @patch("src.feishu.sync_service.bitable_client")
    def test_sync_products_all_update(self, mock_client):
        """全部更新：所有商品已存在。"""
        # 现有记录包含所有商品的主键
        mock_client.query_records.return_value = [
            {"record_id": "rec1", "fields": {
                "ASIN": "B0A", "来源平台": "亚马逊"
            }},
            {"record_id": "rec2", "fields": {
                "ASIN": "B0B", "来源平台": "亚马逊"
            }},
        ]
        mock_client.update_record.return_value = "rec_x"

        service = SyncService(table_id="tbl1", table_name="选品池")
        products = [
            ProductInfo(name="商品A", asin="B0A", platform="亚马逊",
                       category="家居收纳",
                       price_min=10, price_max=20, rating=4.0, review_count=100,
                       bsr_rank=1000, url="https://a.com"),
            ProductInfo(name="商品B", asin="B0B", platform="亚马逊",
                       category="家居收纳",
                       price_min=10, price_max=20, rating=4.0, review_count=100,
                       bsr_rank=1000, url="https://b.com"),
        ]

        result = service.sync_products(products)

        assert result.new_count == 0
        assert result.update_count == 2
        assert result.skip_count == 0
        assert result.fail_count == 0
        # batch_add 不应被调用
        mock_client.batch_add_records.assert_not_called()
        # update 应被调用 2 次
        assert mock_client.update_record.call_count == 2

    @patch("src.feishu.sync_service.bitable_client")
    def test_sync_products_mixed(self, mock_client):
        """混合：部分新增部分更新。"""
        mock_client.query_records.return_value = [
            {"record_id": "rec_existing", "fields": {
                "ASIN": "B0EXISTING", "来源平台": "亚马逊"
            }},
        ]
        mock_client.batch_add_records.return_value = ["rec_new1", "rec_new2"]

        service = SyncService(table_id="tbl1", table_name="选品池")
        products = [
            ProductInfo(name="已存在", asin="B0EXISTING", platform="亚马逊",
                       category="家居收纳",
                       price_min=10, price_max=20, rating=4.0, review_count=100,
                       bsr_rank=1000, url="https://e.com"),
            ProductInfo(name="新商品1", asin="B0NEW1", platform="亚马逊",
                       category="家居收纳",
                       price_min=10, price_max=20, rating=4.0, review_count=100,
                       bsr_rank=1000, url="https://n1.com"),
            ProductInfo(name="新商品2", asin="B0NEW2", platform="亚马逊",
                       category="家居收纳",
                       price_min=10, price_max=20, rating=4.0, review_count=100,
                       bsr_rank=1000, url="https://n2.com"),
        ]

        result = service.sync_products(products)

        assert result.new_count == 2  # 2 个新增
        assert result.update_count == 1  # 1 个更新

    @patch("src.feishu.sync_service.bitable_client")
    def test_sync_products_empty_input(self, mock_client):
        """空输入应直接返回，不查询飞书。"""
        service = SyncService(table_id="tbl1", table_name="选品池")
        result = service.sync_products([])

        assert result.new_count == 0
        assert result.total == 0
        mock_client.query_records.assert_not_called()

    @patch("src.feishu.sync_service.bitable_client")
    def test_sync_products_update_failure_recorded(self, mock_client):
        """更新失败时计入 fail_count 并记录错误。"""
        mock_client.query_records.return_value = [
            {"record_id": "rec1", "fields": {
                "ASIN": "B0A", "来源平台": "亚马逊"
            }},
        ]
        mock_client.update_record.side_effect = RuntimeError("网络错误")

        service = SyncService(table_id="tbl1", table_name="选品池")
        products = [
            ProductInfo(name="商品A", asin="B0A", platform="亚马逊",
                       category="家居收纳",
                       price_min=10, price_max=20, rating=4.0, review_count=100,
                       bsr_rank=1000, url="https://a.com"),
        ]

        result = service.sync_products(products)

        assert result.fail_count == 1
        assert len(result.errors) == 1
        assert "网络错误" in result.errors[0]

    @patch("src.feishu.sync_service.bitable_client")
    def test_sync_records_with_custom_primary_keys(self, mock_client):
        """sync_records 支持自定义主键（用于库存表等）。"""
        mock_client.query_records.return_value = [
            {"record_id": "inv1", "fields": {"SKU": "SKU-001"}},
        ]
        mock_client.batch_add_records.return_value = ["inv_new"]

        service = SyncService(table_id="tbl_inv", table_name="库存预警")
        records = [
            {"SKU": "SKU-001", "当前库存": 200},  # 已存在，更新
            {"SKU": "SKU-002", "当前库存": 100},  # 不存在，新增
        ]

        result = service.sync_records(records, primary_keys=["SKU"])

        assert result.new_count == 1
        assert result.update_count == 1


# ============================================================
# 数据清理任务测试
# ============================================================
class TestCleanupTask:
    """数据清理任务测试。"""

    def test_extract_record_timestamp_int(self):
        """时间戳为整数时正常解析。"""
        from src.scheduler.cleanup_task import _extract_record_timestamp
        fields = {"更新时间": 1753420800000}
        result = _extract_record_timestamp(fields, "更新时间")
        assert result == 1753420800000

    def test_extract_record_timestamp_dict_with_int(self):
        """飞书日期字段格式（字典含整数 date）。"""
        from src.scheduler.cleanup_task import _extract_record_timestamp
        fields = {"更新时间": {"date": 1753420800000, "type": 0}}
        result = _extract_record_timestamp(fields, "更新时间")
        assert result == 1753420800000

    def test_extract_record_timestamp_dict_with_string(self):
        """飞书日期字段格式（字典含字符串 date）。"""
        from src.scheduler.cleanup_task import _extract_record_timestamp
        fields = {"日期": {"date": "2026-07-25", "type": 0}}
        result = _extract_record_timestamp(fields, "日期")
        assert result is not None
        assert result > 0

    def test_extract_record_timestamp_missing(self):
        """字段缺失返回 None。"""
        from src.scheduler.cleanup_task import _extract_record_timestamp
        fields = {"其他字段": "value"}
        result = _extract_record_timestamp(fields, "更新时间")
        assert result is None

    def test_extract_record_timestamp_invalid_string(self):
        """无效字符串返回 None。"""
        from src.scheduler.cleanup_task import _extract_record_timestamp
        fields = {"更新时间": "not-a-date"}
        result = _extract_record_timestamp(fields, "更新时间")
        assert result is None

    @patch("src.scheduler.cleanup_task.bitable_client")
    def test_cleanup_table_deletes_old_records(self, mock_client):
        """清理任务应删除超过保留期的记录。"""
        from datetime import datetime, timedelta
        from src.scheduler.cleanup_task import cleanup_table

        # 构造测试数据：1 条新记录 + 1 条旧记录
        old_timestamp = int((datetime.now() - timedelta(days=10)).timestamp() * 1000)
        new_timestamp = int(datetime.now().timestamp() * 1000)

        mock_client.query_records.return_value = [
            {"record_id": "rec_old", "fields": {"更新时间": old_timestamp}},
            {"record_id": "rec_new", "fields": {"更新时间": new_timestamp}},
        ]
        mock_client.batch_delete_records.return_value = 1

        result = cleanup_table("tbl1", "测试表", "更新时间", retention_days=3)

        assert result["total"] == 2
        assert result["deleted"] == 1
        assert result["kept"] == 1
        # 应删除旧记录
        mock_client.batch_delete_records.assert_called_once_with("tbl1", ["rec_old"])

    @patch("src.scheduler.cleanup_task.bitable_client")
    def test_cleanup_table_empty_table(self, mock_client):
        """空表无需清理。"""
        from src.scheduler.cleanup_task import cleanup_table

        mock_client.query_records.return_value = []

        result = cleanup_table("tbl1", "测试表", "更新时间", retention_days=3)

        assert result["total"] == 0
        assert result["deleted"] == 0
        mock_client.batch_delete_records.assert_not_called()

    @patch("src.scheduler.cleanup_task.bitable_client")
    def test_cleanup_table_keeps_no_time_field_records(self, mock_client):
        """没有时间字段的记录应保留（安全策略）。"""
        from src.scheduler.cleanup_task import cleanup_table

        mock_client.query_records.return_value = [
            {"record_id": "rec_no_time", "fields": {"其他字段": "value"}},
        ]

        result = cleanup_table("tbl1", "测试表", "更新时间", retention_days=3)

        assert result["deleted"] == 0
        assert result["kept"] == 1
        assert result["no_time_field"] == 1
