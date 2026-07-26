"""飞书多维表格 Bitable API 封装。

提供数据表管理、记录增删改查功能。
API 文档：https://open.feishu.cn/document/server-docs/docs/bitable-v1/bitable-overview

核心能力：
- 创建数据表（含字段定义）
- 新增记录（单条/批量）
- 查询记录（按条件/全量）
- 更新记录
- 删除记录
"""

from __future__ import annotations

import time
from typing import Any

import httpx

from src.config import settings
from src.feishu.auth import FEISHU_BASE_URL, feishu_auth
from src.feishu.table_schema import ALL_TABLES
from src.observability.logger import get_logger

logger = get_logger()


class BitableClient:
    """飞书多维表格客户端。

    封装 Bitable REST API，统一处理认证、错误重试、分页。
    """

    def __init__(self) -> None:
        self._app_token = settings.feishu_bitable_app_token

    def _headers(self) -> dict[str, str]:
        """构建请求头，附带 tenant_access_token。"""
        return {
            "Authorization": f"Bearer {feishu_auth.get_token()}",
            "Content-Type": "application/json; charset=utf-8",
        }

    def _request(
        self, method: str, path: str, json: dict | None = None, params: dict | None = None
    ) -> dict:
        """统一请求方法，含错误处理和重试。

        Args:
            method: HTTP 方法（GET/POST/PUT/DELETE）
            path: API 路径（不含 base_url）
            json: 请求体
            params: URL 参数

        Returns:
            飞书 API 响应的 data 字段内容

        Raises:
            RuntimeError: 飞书 API 返回错误
        """
        url = f"{FEISHU_BASE_URL}{path}"
        max_retries = 3

        for attempt in range(max_retries):
            try:
                response = httpx.request(
                    method, url, headers=self._headers(), json=json, params=params, timeout=30
                )
                response.raise_for_status()
                data = response.json()

                if data.get("code") != 0:
                    msg = f"飞书 API 错误: code={data.get('code')}, msg={data.get('msg')}"
                    logger.error(msg)
                    raise RuntimeError(msg)

                return data.get("data", {})

            except httpx.HTTPError as e:
                if attempt < max_retries - 1:
                    wait = 2 ** attempt
                    logger.warning(f"请求失败，{wait}秒后重试: {e}")
                    time.sleep(wait)
                else:
                    logger.error(f"请求最终失败（已重试{max_retries}次）: {e}")
                    raise

        # 理论上不会走到这里
        raise RuntimeError("请求失败，已耗尽重试次数")

    # ============================================================
    # 数据表管理
    # ============================================================

    def create_table(self, table_name: str, fields: list[dict]) -> str:
        """在多维表格中创建一张数据表。

        Args:
            table_name: 表名（如"选品池"）
            fields: 字段定义列表，参考 table_schema.py

        Returns:
            新创建的 table_id
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables"
        payload = {
            "table": {
                "name": table_name,
                "default_view_name": f"{table_name}视图",
                "fields": fields,
            }
        }

        logger.info(f"正在创建多维表格数据表: {table_name}")
        data = self._request("POST", path, json=payload)
        table_id = data["table_id"]
        logger.info(f"数据表创建成功: {table_name} -> {table_id}")
        return table_id

    def create_all_tables(self) -> dict[str, str]:
        """批量创建所有预定义数据表。

        Returns:
            表名到 table_id 的映射字典
        """
        result = {}
        for table_name, fields in ALL_TABLES.items():
            table_id = self.create_table(table_name, fields)
            result[table_name] = table_id
        return result

    def list_tables(self) -> list[dict]:
        """获取多维表格中所有数据表列表。

        Returns:
            数据表信息列表，每项含 table_id, name 等
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables"
        data = self._request("GET", path)
        return data.get("items", [])

    def list_fields(self, table_id: str) -> list[dict]:
        """获取数据表中所有字段列表。

        Args:
            table_id: 数据表 ID

        Returns:
            字段信息列表，每项含 field_id, field_name, type 等
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/fields"
        data = self._request("GET", path)
        return data.get("items", [])

    def list_views(self, table_id: str) -> list[dict]:
        """获取数据表中所有视图列表。

        Args:
            table_id: 数据表 ID

        Returns:
            视图信息列表，每项含 view_id, view_name, view_type 等
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/views"
        data = self._request("GET", path)
        return data.get("items", [])

    def create_view(self, table_id: str, view_name: str, view_type: str = "grid") -> str:
        """在数据表中创建一个新视图。

        飞书视图类型：
        - grid: 网格视图（默认）
        - kanban: 看板视图
        - gallery: 画册视图
        - gantt: 甘特图视图
        - form: 表单视图

        Args:
            table_id: 数据表 ID
            view_name: 视图名称
            view_type: 视图类型，默认 grid

        Returns:
            新创建的 view_id
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/views"
        payload = {"view_name": view_name, "view_type": view_type}

        data = self._request("POST", path, json=payload)
        # 飞书 API 返回结构: {"view": {"view_id": "vewxxx", ...}}
        view_id = data.get("view", {}).get("view_id", "")
        logger.info(
            f"视图创建成功: table={table_id}, "
            f"view_name={view_name}, view_id={view_id}"
        )
        return view_id

    def patch_view(
        self, table_id: str, view_id: str, settings: dict
    ) -> bool:
        """更新视图配置（如隐藏字段、设置筛选条件）。

        飞书 API 限制：通过 patch 可以更新视图的属性，包括字段配置、筛选条件、排序等。
        具体配置格式参考飞书 Bitable View API 文档。

        Args:
            table_id: 数据表 ID
            view_id: 视图 ID
            settings: 视图配置字典

        Returns:
            是否更新成功
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/views/{view_id}"
        self._request("PATCH", path, json=settings)
        logger.info(f"视图更新成功: table={table_id}, view_id={view_id}")
        return True

    def add_field(self, table_id: str, field: dict) -> str:
        """向现有数据表添加一个新字段。

        Args:
            table_id: 数据表 ID
            field: 字段定义，参考 table_schema.py

        Returns:
            新创建的 field_id
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/fields"
        data = self._request("POST", path, json=field)
        field_id = data.get("field_id", "")
        logger.info(
            f"字段添加成功: table={table_id}, "
            f"field_name={field.get('field_name')}, field_id={field_id}"
        )
        return field_id

    # ============================================================
    # 记录管理
    # ============================================================

    def add_record(self, table_id: str, fields: dict[str, Any]) -> str:
        """向数据表新增一条记录。

        Args:
            table_id: 数据表 ID
            fields: 字段值字典，key 为字段名，value 为字段值

        Returns:
            新创建的记录 ID（record_id）
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/records"
        payload = {"fields": fields}
        data = self._request("POST", path, json=payload)
        record_id = data["record"]["record_id"]
        logger.info(f"记录新增成功: table={table_id}, record_id={record_id}")
        return record_id

    def batch_add_records(self, table_id: str, records: list[dict[str, Any]]) -> list[str]:
        """批量新增记录。

        Args:
            table_id: 数据表 ID
            records: 字段值字典列表

        Returns:
            新创建的 record_id 列表
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/records/batch_create"
        payload = {"records": [{"fields": r} for r in records]}
        data = self._request("POST", path, json=payload)
        record_ids = [r["record_id"] for r in data.get("records", [])]
        logger.info(f"批量新增记录成功: table={table_id}, count={len(record_ids)}")
        return record_ids

    def get_record(self, table_id: str, record_id: str) -> dict[str, Any]:
        """查询单条记录。

        Args:
            table_id: 数据表 ID
            record_id: 记录 ID

        Returns:
            记录的字段值字典
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/records/{record_id}"
        data = self._request("GET", path)
        return data["record"]["fields"]

    def query_records(
        self, table_id: str, filter_condition: dict | None = None, page_size: int = 100
    ) -> list[dict]:
        """查询数据表中的记录（支持条件和分页）。

        Args:
            table_id: 数据表 ID
            filter_condition: 筛选条件（参考飞书 API 文档 filter 参数）
            page_size: 每页数量，最大 500

        Returns:
            记录列表，每项含 record_id 和 fields
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/records/search"
        all_records: list[dict] = []
        page_token: str | None = None

        while True:
            payload: dict[str, Any] = {"page_size": page_size}
            if page_token:
                payload["page_token"] = page_token
            if filter_condition:
                payload["filter"] = filter_condition

            data = self._request("POST", path, json=payload)
            all_records.extend(data.get("items", []))

            if not data.get("has_more"):
                break
            page_token = data.get("page_token", "")

        logger.info(f"查询记录完成: table={table_id}, 共 {len(all_records)} 条")
        return all_records

    def update_record(self, table_id: str, record_id: str, fields: dict[str, Any]) -> str:
        """更新单条记录。

        Args:
            table_id: 数据表 ID
            record_id: 记录 ID
            fields: 要更新的字段值

        Returns:
            记录 ID
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/records/{record_id}"
        payload = {"fields": fields}
        data = self._request("PUT", path, json=payload)
        logger.info(f"记录更新成功: table={table_id}, record_id={record_id}")
        return data["record"]["record_id"]

    def delete_record(self, table_id: str, record_id: str) -> bool:
        """删除单条记录。

        Args:
            table_id: 数据表 ID
            record_id: 记录 ID

        Returns:
            是否删除成功
        """
        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/records/{record_id}"
        self._request("DELETE", path)
        logger.info(f"记录删除成功: table={table_id}, record_id={record_id}")
        return True

    def batch_delete_records(self, table_id: str, record_ids: list[str]) -> int:
        """批量删除记录。

        飞书 API 单次最多删除 500 条，超过会自动分批。

        Args:
            table_id: 数据表 ID
            record_ids: 要删除的记录 ID 列表

        Returns:
            成功删除的记录数
        """
        if not record_ids:
            return 0

        path = f"/bitable/v1/apps/{self._app_token}/tables/{table_id}/records/batch_delete"
        total_deleted = 0
        batch_size = 500  # 飞书 API 限制

        for i in range(0, len(record_ids), batch_size):
            batch = record_ids[i:i + batch_size]
            payload = {"records": batch}
            self._request("POST", path, json=payload)
            total_deleted += len(batch)

        logger.info(f"批量删除记录成功: table={table_id}, count={total_deleted}")
        return total_deleted


# 全局单例
bitable_client = BitableClient()
