"""健康检查服务：检测系统配置是否正确完整。

GUI 启动时或业务用户主动触发时，逐项检查系统各组件是否可用：
1. 飞书凭证是否有效（能否拿到 tenant_access_token）
2. 多维表格是否可访问（能否列出数据表）
3. 5 张业务表的 table_id 是否都已配置
4. 多维表格权限是否设置为"组织内可编辑"
5. 卡片回调服务是否在运行（本地 8000 端口健康检查）
6. Cloudflare 隧道是否在运行（公网 URL 可达）

每个检查函数返回 CheckResult 对象，统一入口 run_all_checks() 按顺序执行所有检查。
所有异常均被捕获，不会向上抛出，便于 GUI 安全调用。
"""

from __future__ import annotations

from dataclasses import dataclass

import httpx

from src.config import settings
from src.feishu.auth import FEISHU_BASE_URL, feishu_auth
from src.feishu.bitable import bitable_client
from src.gui.services.env_service import read_env_config
from src.observability.logger import get_logger

logger = get_logger()

# 回调服务本地健康检查地址
_CALLBACK_HEALTH_URL = "http://127.0.0.1:8000/health"

# Cloudflare 隧道公网 URL 在 .env 中的配置键名
_TUNNEL_URL_ENV_KEY = "CLOUDFLARE_TUNNEL_URL"

# HTTP 请求统一超时时间（秒）
_HTTP_TIMEOUT = 5

# 5 张业务表的配置键与中文名映射（settings 属性名 / 中文名 / .env 变量名）
_BUSINESS_TABLES: list[tuple[str, str, str]] = [
    ("feishu_table_id_selection", "选品池", "FEISHU_TABLE_ID_SELECTION"),
    ("feishu_table_id_listing", "Listing库", "FEISHU_TABLE_ID_LISTING"),
    ("feishu_table_id_daily_report", "销售日报", "FEISHU_TABLE_ID_DAILY_REPORT"),
    ("feishu_table_id_inventory", "库存预警", "FEISHU_TABLE_ID_INVENTORY"),
    ("feishu_table_id_collection_config", "采集配置", "FEISHU_TABLE_ID_COLLECTION_CONFIG"),
]


@dataclass
class CheckResult:
    """单项健康检查结果。

    Attributes:
        name: 检查项名称（中文）
        success: 是否通过
        message: 简短结果描述
        detail: 详细信息（如缺失项列表、错误堆栈等）
    """

    name: str
    success: bool
    message: str
    detail: str = ""

    def __repr__(self) -> str:
        """友好显示，便于日志输出。"""
        status = "✅" if self.success else "❌"
        return f"{status} {self.name}: {self.message}"


# ============================================================
# 单项检查函数
# ============================================================


def check_credentials() -> CheckResult:
    """检查飞书凭证是否有效：尝试获取 tenant_access_token。

    Returns:
        CheckResult: 成功时 detail 含 token 前缀（脱敏），失败时 message 含错误原因
    """
    try:
        token = feishu_auth.get_token()
        if not token:
            return CheckResult(
                name="飞书凭证",
                success=False,
                message="获取 token 返回空值",
                detail="feishu_auth.get_token() 返回空字符串",
            )
        # 脱敏：只显示前 10 位，避免完整 token 泄露到日志
        masked = token[:10] + "..." if len(token) > 10 else "***"
        return CheckResult(
            name="飞书凭证",
            success=True,
            message="凭证有效，token 获取成功",
            detail=f"token 前缀: {masked}（长度 {len(token)}）",
        )
    except RuntimeError as e:
        # 凭证未配置或飞书 API 返回错误
        return CheckResult(
            name="飞书凭证",
            success=False,
            message="凭证未配置或无效",
            detail=str(e),
        )
    except Exception as e:
        # 网络异常等未知错误
        logger.error(f"检查飞书凭证异常: {e}", exc_info=True)
        return CheckResult(
            name="飞书凭证",
            success=False,
            message="获取 token 异常",
            detail=f"{type(e).__name__}: {e}",
        )


def check_bitable_app() -> CheckResult:
    """检查多维表格是否可访问：调用 list_tables 获取表格列表。

    Returns:
        CheckResult: 成功时 detail 含表格名列表，失败时 message 含错误原因
    """
    # 前置：app_token 必须配置
    if not settings.feishu_bitable_app_token:
        return CheckResult(
            name="多维表格访问",
            success=False,
            message="FEISHU_BITABLE_APP_TOKEN 未配置",
            detail="请在 .env 中设置多维表格 App Token",
        )

    try:
        tables = bitable_client.list_tables()
        table_names = [t.get("name", "") for t in tables if t.get("name")]
        if table_names:
            detail = "表名: " + ", ".join(table_names)
        else:
            detail = f"（多维表格中共 {len(tables)} 张表，无名称）"
        return CheckResult(
            name="多维表格访问",
            success=True,
            message=f"访问成功，共 {len(tables)} 张数据表",
            detail=detail,
        )
    except Exception as e:
        logger.error(f"检查多维表格访问异常: {e}", exc_info=True)
        return CheckResult(
            name="多维表格访问",
            success=False,
            message="无法访问多维表格",
            detail=f"{type(e).__name__}: {e}",
        )


def check_business_tables() -> CheckResult:
    """检查 5 张业务表的 table_id 是否都已配置。

    检查项：选品池 / Listing库 / 销售日报 / 库存预警 / 采集配置

    Returns:
        CheckResult: 全部配置返回 success=True，否则 detail 列出缺失项
    """
    missing: list[str] = []
    configured: list[str] = []

    for attr_name, display_name, env_key in _BUSINESS_TABLES:
        value = getattr(settings, attr_name, "")
        if value:
            configured.append(display_name)
        else:
            missing.append(f"{display_name}（{env_key}）")

    if missing:
        return CheckResult(
            name="业务表配置",
            success=False,
            message=f"有 {len(missing)} 张表未配置 table_id",
            detail="缺失: " + "; ".join(missing),
        )

    return CheckResult(
        name="业务表配置",
        success=True,
        message="5 张业务表均已配置",
        detail="已配置: " + ", ".join(configured),
    )


def check_table_permissions() -> CheckResult:
    """检查多维表格权限是否设置为"组织内可编辑"。

    调用云文档权限 API（GET /drive/v1/permissions/{token}/public）查询当前公开权限，
    验证 link_share_entity 是否为 tenant_editable。

    Returns:
        CheckResult: 权限正确返回 success=True，否则给出修复建议
    """
    app_token = settings.feishu_bitable_app_token
    if not app_token:
        return CheckResult(
            name="表格权限",
            success=False,
            message="FEISHU_BITABLE_APP_TOKEN 未配置",
            detail="无法检查权限，请先配置 App Token",
        )

    # 获取 token（可能因凭证无效失败）
    try:
        token = feishu_auth.get_token()
    except Exception as e:
        return CheckResult(
            name="表格权限",
            success=False,
            message="获取飞书 token 失败",
            detail=str(e),
        )

    url = f"{FEISHU_BASE_URL}/drive/v1/permissions/{app_token}/public"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json; charset=utf-8",
    }

    try:
        response = httpx.get(
            url, headers=headers, params={"type": "bitable"}, timeout=_HTTP_TIMEOUT
        )
        data = response.json()
    except httpx.HTTPError as e:
        logger.error(f"请求权限 API 失败: {e}", exc_info=True)
        return CheckResult(
            name="表格权限",
            success=False,
            message="请求权限 API 失败",
            detail=f"{type(e).__name__}: {e}",
        )
    except ValueError as e:
        # JSON 解析失败
        logger.error(f"权限 API 响应解析失败: {e}", exc_info=True)
        return CheckResult(
            name="表格权限",
            success=False,
            message="权限 API 响应非 JSON",
            detail=str(e),
        )

    if data.get("code") != 0:
        return CheckResult(
            name="表格权限",
            success=False,
            message="飞书 API 返回错误",
            detail=f"code={data.get('code')}, msg={data.get('msg')}",
        )

    public_data = data.get("data", {})
    link_share = public_data.get("link_share_entity", "")
    external_access = public_data.get("external_access_entity", "")

    if link_share == "tenant_editable":
        return CheckResult(
            name="表格权限",
            success=True,
            message="已设置为组织内可编辑",
            detail=f"link_share_entity={link_share}, external_access_entity={external_access}",
        )

    return CheckResult(
        name="表格权限",
        success=False,
        message="权限未设置为组织内可编辑",
        detail=(
            f"当前 link_share_entity={link_share or '(空)'}，"
            f"期望 tenant_editable。请运行 python scripts/grant_table_permission.py 修复"
        ),
    )


def check_callback_server() -> CheckResult:
    """检查回调服务是否在运行：HTTP 请求本地 8000 端口的 /health 端点。

    Returns:
        CheckResult: 服务运行返回 success=True，否则给出启动建议
    """
    try:
        response = httpx.get(_CALLBACK_HEALTH_URL, timeout=_HTTP_TIMEOUT)
        if response.status_code == 200:
            return CheckResult(
                name="回调服务",
                success=True,
                message="回调服务运行中",
                detail=f"GET {_CALLBACK_HEALTH_URL} -> 200",
            )
        return CheckResult(
            name="回调服务",
            success=False,
            message=f"回调服务响应异常: HTTP {response.status_code}",
            detail=f"GET {_CALLBACK_HEALTH_URL} -> {response.status_code}",
        )
    except httpx.ConnectError:
        return CheckResult(
            name="回调服务",
            success=False,
            message="回调服务未运行",
            detail=(
                f"无法连接 {_CALLBACK_HEALTH_URL}，"
                f"请执行: python scripts/start_callback_server.py"
            ),
        )
    except httpx.HTTPError as e:
        logger.error(f"请求回调服务失败: {e}", exc_info=True)
        return CheckResult(
            name="回调服务",
            success=False,
            message="请求回调服务失败",
            detail=f"{type(e).__name__}: {e}",
        )


def check_tunnel() -> CheckResult:
    """检查 Cloudflare 隧道是否在运行：HTTP 请求 .env 中配置的公网 URL。

    从 .env 读取 CLOUDFLARE_TUNNEL_URL，向其 /health 端点发起 HTTP 请求验证可达性。

    Returns:
        CheckResult: 公网 URL 可达返回 success=True，否则给出配置建议
    """
    config = read_env_config()
    tunnel_url = config.get(_TUNNEL_URL_ENV_KEY, "").strip()

    if not tunnel_url:
        return CheckResult(
            name="Cloudflare 隧道",
            success=False,
            message="未配置公网隧道 URL",
            detail=f"请在 .env 中设置 {_TUNNEL_URL_ENV_KEY}=https://your-tunnel.example.com",
        )

    # 拼接健康检查端点（去除尾部斜杠避免双斜杠）
    check_url = tunnel_url.rstrip("/") + "/health"

    try:
        response = httpx.get(check_url, timeout=_HTTP_TIMEOUT)
        if response.status_code == 200:
            return CheckResult(
                name="Cloudflare 隧道",
                success=True,
                message="隧道可达",
                detail=f"GET {check_url} -> 200",
            )
        # 收到非 200 响应，说明隧道在转发流量但后端可能异常
        return CheckResult(
            name="Cloudflare 隧道",
            success=False,
            message=f"隧道响应异常: HTTP {response.status_code}",
            detail=f"GET {check_url} -> {response.status_code}（隧道在运行，但后端可能异常）",
        )
    except httpx.ConnectError:
        return CheckResult(
            name="Cloudflare 隧道",
            success=False,
            message="隧道未运行或不可达",
            detail=f"无法连接 {check_url}，请确认 Cloudflare 隧道已启动",
        )
    except httpx.HTTPError as e:
        logger.error(f"请求隧道失败: {e}", exc_info=True)
        return CheckResult(
            name="Cloudflare 隧道",
            success=False,
            message="请求隧道失败",
            detail=f"{type(e).__name__}: {e}",
        )


# ============================================================
# 统一入口
# ============================================================


def run_all_checks() -> list[CheckResult]:
    """按顺序执行所有健康检查。

    Returns:
        CheckResult 列表，按以下顺序：
        1. 飞书凭证
        2. 多维表格访问
        3. 业务表配置
        4. 表格权限
        5. 回调服务
        6. Cloudflare 隧道
    """
    logger.info("=" * 50)
    logger.info("系统健康检查开始")
    logger.info("=" * 50)

    results: list[CheckResult] = [
        check_credentials(),
        check_bitable_app(),
        check_business_tables(),
        check_table_permissions(),
        check_callback_server(),
        check_tunnel(),
    ]

    success_count = sum(1 for r in results if r.success)
    logger.info("=" * 50)
    logger.info(f"系统健康检查完成: {success_count}/{len(results)} 项通过")
    logger.info("=" * 50)

    return results
