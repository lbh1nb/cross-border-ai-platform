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

回调数据结构（飞书推送的 JSON）：
    {
        "challenge": "xxx",  # URL 验证时存在
        "token": "xxx",
        "type": "url_verification" | "event_callback",
        "event": {
            "event_type": "card.action.trigger",
            "operator": {"open_id": "ou_xxx"},
            "action": {"value": {"action": "approve", "biz_id": "xxx"}, "tag": "button"},
            "token": "xxx",
            "context": {"open_message_id": "om_xxx"}
        }
    }
"""

from __future__ import annotations

from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from src.config import settings
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

    处理两类回调：
    1. URL 验证（type=url_verification）：飞书首次配置回调 URL 时验证所有权
    2. 卡片按钮点击（type=event_callback，event_type=card.action.trigger）

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

    callback_type = body.get("type", "")
    logger.info(f"收到飞书回调: type={callback_type}")

    # 1. URL 验证
    if callback_type == "url_verification":
        challenge = body.get("challenge", "")
        logger.info(f"URL 验证请求, challenge={challenge[:20]}...")
        return JSONResponse(content={"challenge": challenge})

    # 2. 卡片按钮点击事件
    if callback_type == "event_callback":
        event = body.get("event", {})
        event_type = event.get("event_type", "")
        if event_type == "card.action.trigger":
            return await _handle_card_action(event)

        logger.warning(f"未支持的事件类型: {event_type}")
        return JSONResponse(
            status_code=200,
            content={"success": False, "message": f"Unsupported event: {event_type}"},
        )

    logger.warning(f"未支持的回调类型: {callback_type}")
    return JSONResponse(
        status_code=400,
        content={"error": f"Unsupported callback type: {callback_type}"},
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

    业务逻辑（08-06 完善）：
    1. 回写多维表格"审批状态"字段为"已通过"
    2. 记录审批人到"审批人"字段
    3. 触发后续流程（如下单采购）

    当前实现：仅记录日志，返回成功。

    Args:
        value: 按钮携带的数据（biz_type/biz_id/amount）
        operator_id: 操作人 open_id

    Returns:
        处理结果
    """
    biz_type = value.get("biz_type", "unknown")
    biz_id = value.get("biz_id", "unknown")
    amount = value.get("amount", 0)

    logger.info(
        f"审批通过: biz_type={biz_type}, biz_id={biz_id}, "
        f"amount=${amount}, operator={operator_id}"
    )

    # TODO 08-06: 回写飞书表格审批状态
    # from src.feishu.bitable import bitable_client
    # bitable_client.update_record(table_id, record_id, {
    #     "审批状态": "已通过",
    #     "审批人": operator_id,
    # })

    return {
        "success": True,
        "message": f"审批已通过: {biz_type} {biz_id}",
    }


async def _handle_reject(value: dict[str, Any], operator_id: str) -> dict[str, Any]:
    """处理审批拒绝按钮。

    业务逻辑（08-06 完善）：
    1. 回写多维表格"审批状态"字段为"已拒绝"
    2. 记录审批人到"审批人"字段

    当前实现：仅记录日志，返回成功。

    Args:
        value: 按钮携带的数据
        operator_id: 操作人 open_id

    Returns:
        处理结果
    """
    biz_type = value.get("biz_type", "unknown")
    biz_id = value.get("biz_id", "unknown")

    logger.info(
        f"审批拒绝: biz_type={biz_type}, biz_id={biz_id}, operator={operator_id}"
    )

    return {
        "success": True,
        "message": f"审批已拒绝: {biz_type} {biz_id}",
    }


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
