"""审批流管理服务。

封装飞书审批流 API，让 GUI 能：
1. 扫描企业内所有审批定义（业务用户在飞书审批后台创建后，GUI 自动检测）
2. 查询审批定义的表单字段 ID 和审批节点 ID
3. 一键写入 .env 配置

业务用户流程：
    飞书审批后台创建审批 → GUI 点"扫描" → 列表出现 → 点"启用" → 自动配置完成
"""

from __future__ import annotations

from typing import Any

import httpx

from src.feishu.auth import get_tenant_access_token
from src.gui.services.env_service import write_env_config
from src.observability.logger import get_logger

logger = get_logger()

_API_BASE = "https://open.feishu.cn/open-apis/approval/v4"


def list_approval_definitions() -> list[dict[str, Any]]:
    """扫描企业内所有审批定义。

    调用飞书 API 获取企业内所有已创建的审批定义列表。
    业务用户在飞书审批后台创建审批后，这里自动检测到。

    Returns:
        审批定义列表，每项含 approval_code / approval_name / status
    """
    token = get_tenant_access_token()
    if not token:
        logger.error("无法获取 tenant_access_token")
        return []

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        with httpx.Client(timeout=10) as client:
            response = client.post(
                f"{_API_BASE}/approvals",
                headers=headers,
                json={"page_size": 100},
            )
            data = response.json()

        if data.get("code") != 0:
            logger.error(
                f"扫描审批定义失败: code={data.get('code')}, msg={data.get('msg')}"
            )
            return []

        # 响应结构：{"data": {"items": [...]}}
        items = data.get("data", {}).get("items", [])
        logger.info(f"扫描到 {len(items)} 个审批定义")
        return items

    except Exception as e:
        logger.error(f"扫描审批定义异常: {e}", exc_info=True)
        return []


def query_approval_detail(approval_code: str) -> dict[str, Any]:
    """查询审批定义详情（含表单字段 ID 和审批节点 ID）。

    Args:
        approval_code: 审批定义 Code

    Returns:
        审批定义详情，含 form（JSON 字符串）和 node_list
    """
    token = get_tenant_access_token()
    if not token:
        return {}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(
                f"{_API_BASE}/approvals/{approval_code}",
                headers=headers,
            )
            data = response.json()

        if data.get("code") != 0:
            logger.error(
                f"查询审批定义详情失败: code={data.get('code')}, "
                f"msg={data.get('msg')}"
            )
            return {}

        return data.get("data", {})

    except Exception as e:
        logger.error(f"查询审批定义详情异常: {e}", exc_info=True)
        return {}


def extract_approval_config(approval_detail: dict[str, Any]) -> dict[str, Any]:
    """从审批定义详情中提取 GUI 需要的配置信息。

    Args:
        approval_detail: query_approval_detail 返回的详情

    Returns:
        配置字典，含：
        - approval_code: 审批定义 Code
        - approval_name: 审批定义名称
        - node_id: 审批节点 ID
        - field_count: 表单字段数
        - field_ids: 表单字段 ID 字典（键为字段名，值为 widget ID）
    """
    import json

    approval_code = approval_detail.get("approval_code", "")
    approval_name = approval_detail.get("approval_name", "")

    # 解析表单字段，提取字段名 → widget ID 的映射
    form_str = approval_detail.get("form", "")
    field_count = 0
    field_ids: dict[str, str] = {}
    if form_str:
        try:
            fields = json.loads(form_str)
            field_count = len(fields)
            for field in fields:
                field_name = field.get("name", "")
                widget_id = field.get("id", "")
                if field_name and widget_id:
                    field_ids[field_name] = widget_id
        except json.JSONDecodeError:
            pass

    # 找第一个"审批"类型的节点
    node_id = ""
    nodes = approval_detail.get("node_list", [])
    for node in nodes:
        node_type = node.get("type", "")
        if node_type == "APPROVER" or "审批" in node.get("name", ""):
            node_id = node.get("node_id", "")
            break

    # 如果没找到审批节点，取第一个非提交非结束的节点
    if not node_id and nodes:
        for node in nodes:
            node_type = node.get("type", "")
            if node_type not in ("START", "END"):
                node_id = node.get("node_id", "")
                break

    return {
        "approval_code": approval_code,
        "approval_name": approval_name,
        "node_id": node_id,
        "field_count": str(field_count),
        "field_ids": field_ids,
    }


def enable_approval(
    approval_code: str,
    node_id: str,
    approver_open_id: str,
) -> bool:
    """启用审批流：把审批定义配置写入 .env。

    业务用户在 GUI 点"启用"后调用本函数，自动完成配置。
    配置完成后，每天 10:00 的自动触发任务会自动扫描并创建审批实例。

    Args:
        approval_code: 审批定义 Code
        node_id: 审批节点 ID
        approver_open_id: 审批人 open_id

    Returns:
        True 表示配置成功
    """
    updates = {
        "FEISHU_APPROVAL_CODE": approval_code,
        "FEISHU_APPROVAL_NODE_ID": node_id,
        "FEISHU_APPROVAL_APPROVER_OPEN_ID": approver_open_id,
    }
    success = write_env_config(updates)
    if success:
        logger.info(
            f"审批流已启用: approval_code={approval_code}, "
            f"node_id={node_id}, approver={approver_open_id}"
        )
    return success
