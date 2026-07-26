"""飞书卡片交互回调服务（FastAPI）。

接收并处理飞书卡片按钮点击回调，支持两类事件：
1. URL 验证（challenge）：飞书首次配置回调 URL 时发送，需原样返回 challenge
2. card.action.trigger：用户点击卡片按钮时触发，根据按钮 value 做对应处理

服务架构：
    飞书服务器 → 公网 URL（需 ngrok 等内网穿透）→ 本地 FastAPI 服务

启动方式：
    python -m src.feishu.card_callback
    或
    uvicorn src.feishu.card_callback:app --host 0.0.0.0 --port 8000

飞书应用配置（一次性，在飞书开放平台操作）：
    1. 启用应用机器人能力
    2. 订阅事件：card.action.trigger
    3. 配置请求地址：https://<ngrok-url>/callback
    4. 发布应用版本并审核通过

支持两种回调格式：
- 老格式（schema 1.0）：顶层有 type 字段
  {"type": "url_verification", "challenge": "xxx"}
  {"type": "event_callback", "event": {"event_type": "card.action.trigger", ...}}

- 新格式（schema 2.0）：顶层无 type，event_type 在 header 里
  {"schema": "2.0", "header": {"event_type": "card.action.trigger", ...}, "event": {...}}
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.config import settings
from src.feishu.bitable import bitable_client
from src.feishu.card_templates import build_approval_done_card
from src.observability.logger import get_logger

logger = get_logger()

app = FastAPI(
    title="飞书卡片回调服务",
    description="接收并处理飞书卡片按钮点击回调",
    version="0.1.0",
)


@app.post("/callback")
async def handle_callback(request: Request) -> JSONResponse:
    """飞书回调统一入口。

    兼容两种回调格式：
    - 老格式（schema 1.0）：顶层有 type 字段
    - 新格式（schema 2.0）：顶层无 type，event_type 在 header 里

    Args:
        request: FastAPI 请求对象

    Returns:
        JSON 响应：
        - URL 验证：{"challenge": <原样返回>}
        - 按钮点击：{"success": True/False, "message": "..."}
    """
    try:
        body: dict[str, Any] = await request.json()
    except Exception as e:
        logger.error(f"回调请求体解析失败: {e}")
        return JSONResponse(
            status_code=400,
            content={"error": "Invalid JSON body"},
        )

    # 兼容两种格式：老格式顶层有 type，新格式 schema=2.0 在 header.event_type
    callback_type = body.get("type", "")
    header = body.get("header", {}) if not callback_type else {}
    event_type = header.get("event_type", "")

    logger.info(
        f"收到飞书回调: type={callback_type or '(新格式)'}, "
        f"event_type={event_type or '(URL验证)'}"
    )

    # 1. URL 验证（两种格式都有 type=url_verification）
    if callback_type == "url_verification":
        challenge = body.get("challenge", "")
        logger.info(f"URL 验证请求, challenge={challenge[:20]}...")
        return JSONResponse(content={"challenge": challenge})

    # 2. 卡片按钮点击事件
    # 老格式：type=event_callback，event_type 在 event 里
    # 新格式：header.event_type=card.action.trigger
    is_card_action = (
        (callback_type == "event_callback" and body.get("event", {}).get("event_type") == "card.action.trigger")
        or event_type == "card.action.trigger"
    )

    if is_card_action:
        event = body.get("event", {})
        return await _handle_card_action(event)

    logger.warning(
        f"未支持的回调: type={callback_type}, event_type={event_type}"
    )
    return JSONResponse(
        status_code=200,
        content={"success": False, "message": f"Unsupported callback: type={callback_type}, event_type={event_type}"},
    )


async def _handle_card_action(event: dict[str, Any]) -> JSONResponse:
    """处理卡片按钮点击事件。

    根据按钮 value 中的 action 字段路由到不同处理器：
    - approve：审批通过
    - reject：审批拒绝
    - 其他：记录日志

    Args:
        event: 飞书事件数据

    Returns:
        JSON 响应（飞书要求 3 秒内响应）
    """
    action_info = event.get("action", {})
    value: dict[str, Any] = action_info.get("value", {})
    action_name = value.get("action", "unknown")

    operator = event.get("operator", {})
    operator_id = operator.get("open_id", "unknown")

    logger.info(
        f"卡片按钮点击: action={action_name}, operator={operator_id}, "
        f"value={value}"
    )

    # 路由到具体处理器
    handlers = {
        "approve": _handle_approve,
        "reject": _handle_reject,
    }
    handler = handlers.get(action_name)
    if handler is None:
        logger.warning(f"未注册的 action: {action_name}")
        return JSONResponse(
            content={"success": False, "message": f"Unknown action: {action_name}"}
        )

    try:
        result = await handler(value, operator_id)
        return JSONResponse(content=result)
    except Exception as e:
        logger.error(f"处理 action={action_name} 失败: {e}", exc_info=True)
        return JSONResponse(
            content={"success": False, "message": f"Handler error: {e}"}
        )


async def _handle_approve(value: dict[str, Any], operator_id: str) -> dict[str, Any]:
    """处理审批通过按钮。

    业务逻辑：
    1. 按 ASIN 查询"库存预警"表，找到对应记录
    2. 更新"审批状态"字段为"已通过"
    3. 返回 toast 提示 + 更新后的卡片（按钮变灰不可点）

    Args:
        value: 按钮携带的数据（biz_type/biz_id/amount）
        operator_id: 操作人 open_id

    Returns:
        飞书期望的响应格式：{"toast": {...}, "card": {...}}
    """
    biz_type = value.get("biz_type", "unknown")
    biz_id = value.get("biz_id", "unknown")
    amount_raw = value.get("amount", "0")
    try:
        amount = float(amount_raw) if amount_raw else 0.0
    except (TypeError, ValueError):
        amount = 0.0

    logger.info(
        f"审批通过: biz_type={biz_type}, biz_id={biz_id}, "
        f"amount=${amount:,.2f}, operator={operator_id}"
    )

    # 回写多维表格"审批状态"字段
    update_ok = _update_approval_status(biz_id, "已通过")

    toast_type = "success" if update_ok else "error"
    toast_content = (
        f"✅ 审批已通过: {biz_type} {biz_id}\n多维表格审批状态已更新"
        if update_ok
        else f"⚠️ 审批通过，但多维表格更新失败: {biz_type} {biz_id}"
    )

    return {
        "toast": {
            "type": toast_type,
            "content": toast_content,
        },
        "card": {
            "type": "raw",
            "data": build_approval_done_card(
                approved=True,
                biz_type=biz_type,
                biz_id=biz_id,
                amount=amount,
                approver=operator_id,
            ),
        },
    }


async def _handle_reject(value: dict[str, Any], operator_id: str) -> dict[str, Any]:
    """处理审批拒绝按钮。

    业务逻辑：
    1. 按 ASIN 查询"库存预警"表，找到对应记录
    2. 更新"审批状态"字段为"已驳回"
    3. 返回 toast 提示 + 更新后的卡片（按钮变灰不可点）

    Args:
        value: 按钮携带的数据
        operator_id: 操作人 open_id

    Returns:
        飞书期望的响应格式：{"toast": {...}, "card": {...}}
    """
    biz_type = value.get("biz_type", "unknown")
    biz_id = value.get("biz_id", "unknown")
    amount_raw = value.get("amount", "0")
    try:
        amount = float(amount_raw) if amount_raw else 0.0
    except (TypeError, ValueError):
        amount = 0.0

    logger.info(
        f"审批拒绝: biz_type={biz_type}, biz_id={biz_id}, operator={operator_id}"
    )

    # 回写多维表格"审批状态"字段
    update_ok = _update_approval_status(biz_id, "已驳回")

    toast_type = "success" if update_ok else "error"
    toast_content = (
        f"❌ 审批已拒绝: {biz_type} {biz_id}\n多维表格审批状态已更新"
        if update_ok
        else f"⚠️ 审批拒绝，但多维表格更新失败: {biz_type} {biz_id}"
    )

    return {
        "toast": {
            "type": toast_type,
            "content": toast_content,
        },
        "card": {
            "type": "raw",
            "data": build_approval_done_card(
                approved=False,
                biz_type=biz_type,
                biz_id=biz_id,
                amount=amount,
                approver=operator_id,
            ),
        },
    }


def _update_approval_status(asin: str, status: str) -> bool:
    """按 ASIN 查询库存预警表并更新"审批状态"字段。

    Args:
        asin: 商品 ASIN（审批卡片 value 里的 biz_id）
        status: 目标状态（"已通过" / "已驳回"）

    Returns:
        True=更新成功, False=更新失败或未找到记录
    """
    table_id = settings.feishu_table_id_inventory
    if not table_id:
        logger.error("未配置 FEISHU_TABLE_ID_INVENTORY，无法回写审批状态")
        return False

    try:
        # 按 ASIN 查询记录（飞书 filter 条件）
        filter_condition = {
            "conjunction": "and",
            "conditions": [
                {
                    "field_name": "ASIN",
                    "operator": "is",
                    "value": [asin],
                }
            ],
        }
        records = bitable_client.query_records(table_id, filter_condition)

        if not records:
            logger.warning(f"未找到 ASIN={asin} 的库存预警记录，无法更新审批状态")
            return False

        # 取第一条匹配记录（ASIN 应该是唯一的）
        record_id = records[0].get("record_id", "")
        if not record_id:
            logger.error(f"ASIN={asin} 的记录缺少 record_id")
            return False

        # 更新"审批状态"字段
        bitable_client.update_record(table_id, record_id, {"审批状态": status})
        logger.info(
            f"已更新库存预警表: ASIN={asin}, record_id={record_id}, 审批状态={status}"
        )
        return True

    except Exception as e:
        logger.error(
            f"更新库存预警表审批状态失败: ASIN={asin}, status={status}, error={e}",
            exc_info=True,
        )
        return False


@app.get("/health")
async def health_check() -> dict[str, str]:
    """健康检查端点（用于监控和 ngrok 隧道验证）。"""
    return {"status": "ok", "service": "feishu-card-callback"}


@app.get("/")
async def root() -> dict[str, str]:
    """根路径，返回服务说明。"""
    return {
        "service": "飞书卡片回调服务",
        "version": "0.1.0",
        "endpoints": "/callback (POST), /health (GET)",
    }


if __name__ == "__main__":
    import uvicorn

    host = "0.0.0.0"
    port = 8000
    logger.info(f"启动飞书卡片回调服务: http://{host}:{port}")
    logger.info("回调端点: POST /callback")
    logger.info("健康检查: GET /health")
    logger.info("")
    logger.info("使用 ngrok 暴露到公网后，把公网 URL + /callback 配置到飞书应用")
    uvicorn.run(app, host=host, port=port, log_level="info")
