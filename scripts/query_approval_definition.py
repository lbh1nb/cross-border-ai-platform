"""查询飞书审批定义的表单结构和审批流程节点。

用途：
    创建审批实例时需要知道表单字段的 id 和 type（飞书自动生成的 widget_xxx），
    本脚本通过 API 获取并打印出来，供编码时填写 form 参数。

前置条件：
    1. 飞书应用已开通 approval:approval 权限
    2. 应用已发布新版本并通过审核
    3. .env 已配置 FEISHU_APP_ID 和 FEISHU_APP_SECRET
    4. 已在飞书审批后台创建审批定义，并获取 approval_code

用法：
    python scripts/query_approval_definition.py

    或指定 approval_code：
    python scripts/query_approval_definition.py 5458BD3D-F35F-4A34-A518-7CF8DED3EE6D
"""

from __future__ import annotations

import sys
from pathlib import Path

# 把项目根目录加入 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

import httpx

from src.config import settings
from src.feishu.auth import get_tenant_access_token
from src.observability.logger import get_logger

logger = get_logger()

# 默认 approval_code（用户已创建的审批定义）
DEFAULT_APPROVAL_CODE = "5458BD3D-F35F-4A34-A518-7CF8DED3EE6D"


def query_approval_definition(approval_code: str) -> dict:
    """查询审批定义详情。

    API 文档：GET /open-apis/approval/v4/approvals/{approval_code}
    需要权限：approval:approval

    Args:
        approval_code: 审批定义 Code

    Returns:
        审批定义详情 JSON
    """
    token = get_tenant_access_token()
    if not token:
        logger.error("无法获取 tenant_access_token，请检查应用凭证")
        return {}

    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    url = f"https://open.feishu.cn/open-apis/approval/v4/approvals/{approval_code}"

    try:
        with httpx.Client(timeout=10) as client:
            response = client.get(url, headers=headers)
            data = response.json()
    except Exception as e:
        print(f"  [异常] 调用飞书 API 失败: {e}")
        import traceback
        traceback.print_exc()
        return {}

    if data.get("code") != 0:
        print()
        print(f"  [飞书 API 返回错误]")
        print(f"  HTTP 状态码: {response.status_code}")
        print(f"  业务错误码: {data.get('code')}")
        print(f"  错误消息: {data.get('msg')}")
        print(f"  完整响应: {data}")
        print()
        print("  常见错误码：")
        print("  - 1390001: approval_code 无效或审批定义已被删除")
        print("  - 1390015: 审批定义未激活（需在审批后台点击 启用）")
        print("  - 99991663: 权限不足（需开通 approval:approval 并发布版本）")
        print("  - 99991668: 无权访问该审批定义（应用不是审批定义的所属应用）")
        return {}

    # 响应结构：{"code": 0, "data": {"approval_name": "...", "form": "...", "node_list": [...]}}
    # data 字段直接就是审批定义对象，不需要再嵌套 .get("approval")
    return data.get("data", {})


def print_form_fields(approval: dict) -> None:
    """打印审批定义的表单字段结构。"""
    form = approval.get("form", "")
    if not form:
        print("  [表单为空]")
        return

    # form 是 JSON 字符串，需要解析
    import json

    try:
        fields = json.loads(form)
    except json.JSONDecodeError as e:
        print(f"  [表单解析失败: {e}]")
        print(f"  原始内容: {form[:500]}")
        return

    print(f"  表单字段数：{len(fields)}")
    print()
    print(f"  {'序号':<4} {'字段ID':<35} {'类型':<12} {'名称':<15} {'是否必填'}")
    print("  " + "-" * 90)
    for i, field in enumerate(fields, 1):
        field_id = field.get("id", "")
        field_type = field.get("type", "")
        field_name = field.get("name", "")
        required = field.get("required", False)
        req_text = "是" if required else "否"
        print(f"  {i:<4} {field_id:<35} {field_type:<12} {field_name:<15} {req_text}")


def print_approval_nodes(approval: dict) -> None:
    """打印审批流程节点。"""
    nodes = approval.get("node_list", [])
    if not nodes:
        print("  [无审批节点]")
        return

    print(f"  审批节点数：{len(nodes)}")
    print()
    print(f"  {'序号':<4} {'节点ID':<35} {'类型':<15} {'名称'}")
    print("  " + "-" * 80)
    for i, node in enumerate(nodes, 1):
        node_id = node.get("node_id", "")
        node_type = node.get("type", "")
        node_name = node.get("name", "")
        print(f"  {i:<4} {node_id:<35} {node_type:<15} {node_name}")


def main() -> None:
    """主函数：查询并打印审批定义详情。"""
    # 从命令行参数或默认值获取 approval_code
    approval_code = sys.argv[1] if len(sys.argv) > 1 else DEFAULT_APPROVAL_CODE

    print("=" * 70)
    print("  飞书审批定义查询工具")
    print("=" * 70)
    print()
    print(f"  应用 App ID: {settings.feishu_app_id}")
    print(f"  审批定义 Code: {approval_code}")
    print()
    print("  正在调用飞书 API 查询审批定义...")
    print()

    approval = query_approval_definition(approval_code)

    if not approval:
        print("  [查询失败，请按上方提示排查]")
        return

    print("=" * 70)
    print("  审批定义基本信息")
    print("=" * 70)
    print(f"  审批名称: {approval.get('approval_name', '')}")
    print(f"  审批 Code: {approval.get('approval_code', '')}")
    print(f"  状态: {approval.get('status', '')} (1=启用, 2=停用)")
    print(f"  发起人范围: {approval.get('start_range', '')}")
    print()

    print("=" * 70)
    print("  表单字段结构（创建审批实例时需按此填写 form 参数）")
    print("=" * 70)
    print_form_fields(approval)
    print()

    print("=" * 70)
    print("  审批流程节点（创建审批实例时需按此指定审批人）")
    print("=" * 70)
    print_approval_nodes(approval)
    print()

    print("=" * 70)
    print("  下一步")
    print("=" * 70)
    print()
    print("  请把上面输出完整截图或复制给我，我会根据字段结构编写")
    print("  approval.py 模块（创建审批实例 + 查询审批状态 + 回写表格）")


if __name__ == "__main__":
    main()
