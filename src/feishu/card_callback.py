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

import asyncio
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

    # 3. 审批实例状态变更事件（08-06 审批流自动化）
    # 老格式：event.event_type = approval_instance
    # 新格式：header.event_type = approval_instance
    is_approval_event = (
        (callback_type == "event_callback" and body.get("event", {}).get("event_type") == "approval_instance")
        or event_type == "approval_instance"
    )

    if is_approval_event:
        event = body.get("event", {})
        return await _handle_approval_status_changed(event)

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
    1. 立刻返回 toast + 更新后的卡片（毫秒级响应，避免飞书 3 秒超时）
    2. 后台异步回写多维表格"审批状态"字段
    3. 回写失败时通过应用机器人发告警消息到飞书群

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

    # 后台异步回写（不阻塞响应，避免飞书 3 秒超时）
    asyncio.create_task(
        _async_writeback_with_notify(value, operator_id, approved=True)
    )

    # 立刻返回乐观响应（用户先看到成功提示，回写失败会另发告警）
    return {
        "toast": {
            "type": "success",
            "content": f"✅ 审批已通过: {biz_type} {biz_id}\n正在更新多维表格...",
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
    1. 立刻返回 toast + 更新后的卡片（毫秒级响应，避免飞书 3 秒超时）
    2. 后台异步回写多维表格"审批状态"字段
    3. 回写失败时通过应用机器人发告警消息到飞书群

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

    # 后台异步回写（不阻塞响应）
    asyncio.create_task(
        _async_writeback_with_notify(value, operator_id, approved=False)
    )

    # 立刻返回乐观响应
    return {
        "toast": {
            "type": "success",
            "content": f"❌ 审批已拒绝: {biz_type} {biz_id}\n正在更新多维表格...",
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


async def _async_writeback_with_notify(
    value: dict[str, Any], operator_id: str, approved: bool
) -> None:
    """后台异步回写多维表格，失败时发告警消息到飞书群。

    使用 run_in_executor 避免阻塞 event loop（bitable_client 是同步 httpx 调用）。

    Args:
        value: 按钮携带的数据
        operator_id: 操作人 open_id
        approved: True=已通过, False=已驳回
    """
    biz_id = value.get("biz_id", "unknown")
    biz_type = value.get("biz_type", "unknown")
    status = "已通过" if approved else "已驳回"

    try:
        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(
            None, _update_approval_status, biz_id, status
        )

        if ok:
            logger.info(f"异步回写成功: ASIN={biz_id}, 状态={status}")
        else:
            # 回写失败，发告警消息到飞书群
            await _notify_writeback_failure(biz_id, biz_type, status, operator_id)

    except Exception as e:
        logger.error(
            f"异步回写异常: ASIN={biz_id}, status={status}, error={e}",
            exc_info=True,
        )
        await _notify_writeback_failure(biz_id, biz_type, status, operator_id)


async def _notify_writeback_failure(
    biz_id: str, biz_type: str, status: str, operator_id: str
) -> None:
    """回写失败时发告警消息到飞书群。

    Args:
        biz_id: 业务 ID（ASIN）
        biz_type: 业务类型
        status: 目标状态（已通过/已驳回）
        operator_id: 审批人 open_id
    """
    try:
        # 延迟导入避免循环依赖
        from src.feishu.application_bot import application_bot

        msg = (
            f"⚠️ 审批回写失败\n"
            f"业务类型: {biz_type}\n"
            f"ASIN: {biz_id}\n"
            f"目标状态: {status}\n"
            f"审批人: {operator_id}\n"
            f"请手动检查多维表格'库存预警'表。"
        )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, application_bot.send_text, msg)
        logger.info(f"已发送回写失败告警: ASIN={biz_id}")

    except Exception as e:
        logger.error(f"发送回写失败告警也失败了: ASIN={biz_id}, error={e}")


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


# ============ 飞书审批流状态变更回调（08-06） ============


# 飞书审批实例状态码 → 多维表格"审批状态"字段值
# 飞书状态码文档：https://open.feishu.cn/document/server-docs/approval-v4/event/status-changed
APPROVAL_EVENT_STATUS_MAP = {
    "PENDING": "审批中",
    "APPROVED": "已通过",
    "REJECTED": "已驳回",
    "CANCELED": "已撤销",
    "DELETED": "已删除",
    "COMPLETED": "已完成",
}


async def _handle_approval_status_changed(event: dict[str, Any]) -> JSONResponse:
    """处理飞书审批实例状态变更事件。

    业务流程：
    1. 飞书审批流实例状态变更（主管在审批中心通过/拒绝）
    2. 飞书推送 approval_instance 事件到我们的回调服务
    3. 从事件中解析 instance_code 和 status
    4. 异步回写多维表格"审批状态"字段（按 instance_code 关联）

    飞书事件格式（approval_instance.status_changed）：
    {
        "event_type": "approval_instance",
        "instance_code": "81D31358-...",
        "status": "APPROVED",  # PENDING/APPROVED/REJECTED/CANCELED
        "form": "[{...}]",  # 表单内容（含 ASIN）
        "operator": {"open_id": "ou_xxx"}
    }

    Args:
        event: 飞书事件数据

    Returns:
        JSON 响应（飞书要求 3 秒内响应，所以异步回写）
    """
    instance_code = event.get("instance_code", "")
    status_code = event.get("status", "")
    operator = event.get("operator", {})
    operator_id = operator.get("open_id", "unknown")

    logger.info(
        f"审批状态变更: instance_code={instance_code}, "
        f"status={status_code}, operator={operator_id}"
    )

    if not instance_code or not status_code:
        logger.warning(f"审批事件缺少关键字段: {event}")
        return JSONResponse(
            content={"success": False, "message": "Missing instance_code or status"}
        )

    # 后台异步处理（避免飞书 3 秒超时）
    asyncio.create_task(
        _async_handle_approval_event(instance_code, status_code, operator_id)
    )

    # 立刻返回成功响应
    return JSONResponse(
        content={
            "success": True,
            "message": f"Approval event received: {instance_code} -> {status_code}",
        }
    )


async def _async_handle_approval_event(
    instance_code: str, status_code: str, operator_id: str
) -> None:
    """异步处理审批状态变更：从表单提取 ASIN → 回写多维表格。

    Args:
        instance_code: 审批实例 Code
        status_code: 飞书审批状态码（APPROVED/REJECTED 等）
        operator_id: 操作人 open_id
    """
    status_text = APPROVAL_EVENT_STATUS_MAP.get(status_code, "未知")
    logger.info(
        f"异步处理审批事件: instance_code={instance_code}, "
        f"status={status_code} -> {status_text}"
    )

    try:
        # 从审批实例表单中提取 ASIN（飞书事件可能不带 form，需要查询）
        asin = await _extract_asin_from_approval(instance_code)
        if not asin:
            logger.error(
                f"无法从审批实例提取 ASIN: instance_code={instance_code}, "
                f"跳过回写"
            )
            await _notify_approval_writeback_failure(
                instance_code, "", status_text, operator_id, "无法提取 ASIN"
            )
            return

        # 回写多维表格
        loop = asyncio.get_event_loop()
        ok = await loop.run_in_executor(
            None, _update_approval_status, asin, status_text
        )

        if ok:
            logger.info(
                f"审批状态回写成功: ASIN={asin}, 状态={status_text}"
            )
        else:
            await _notify_approval_writeback_failure(
                instance_code, asin, status_text, operator_id, "多维表格更新失败"
            )

    except Exception as e:
        logger.error(
            f"处理审批事件异常: instance_code={instance_code}, error={e}",
            exc_info=True,
        )
        await _notify_approval_writeback_failure(
            instance_code, "", status_text, operator_id, str(e)
        )


async def _extract_asin_from_approval(instance_code: str) -> str:
    """从审批实例表单中提取 ASIN。

    飞书审批事件回调中可能不包含表单内容，需要调用查询 API 获取。
    查询审批实例详情后，从 form 字段解析 ASIN。

    Args:
        instance_code: 审批实例 Code

    Returns:
        ASIN 字符串，失败返回空字符串
    """
    try:
        from src.feishu.approval import approval_client

        loop = asyncio.get_event_loop()
        # 查询审批实例详情（同步 API，用 run_in_executor 避免阻塞）
        detail = await loop.run_in_executor(
            None, approval_client.query_approval_status, instance_code
        )

        if not detail:
            logger.warning(f"查询审批实例详情为空: {instance_code}")
            return ""

        # form 是 JSON 字符串，需要解析
        import json

        form_str = detail.get("form", "")
        if not form_str:
            logger.warning(f"审批实例表单为空: {instance_code}")
            return ""

        fields = json.loads(form_str)
        for field in fields:
            # 通过字段名匹配（更稳健，不依赖字段 ID）
            if field.get("name") == "ASIN":
                return str(field.get("value", ""))

        logger.warning(f"审批表单中未找到 ASIN 字段: {instance_code}")
        return ""

    except Exception as e:
        logger.error(
            f"提取 ASIN 异常: instance_code={instance_code}, error={e}",
            exc_info=True,
        )
        return ""


async def _notify_approval_writeback_failure(
    instance_code: str,
    asin: str,
    status: str,
    operator_id: str,
    reason: str,
) -> None:
    """审批回写失败时发告警消息到飞书群。

    Args:
        instance_code: 审批实例 Code
        asin: 商品 ASIN（可能为空）
        status: 目标状态
        operator_id: 审批人 open_id
        reason: 失败原因
    """
    try:
        from src.feishu.application_bot import application_bot

        msg = (
            f"⚠️ 审批状态回写失败\n"
            f"审批实例: {instance_code}\n"
            f"商品 ASIN: {asin or '未知'}\n"
            f"目标状态: {status}\n"
            f"审批人: {operator_id}\n"
            f"失败原因: {reason}\n"
            f"请手动检查多维表格'库存预警'表。"
        )
        loop = asyncio.get_event_loop()
        await loop.run_in_executor(None, application_bot.send_text, msg)
        logger.info(f"已发送审批回写失败告警: instance_code={instance_code}")

    except Exception as e:
        logger.error(
            f"发送审批回写失败告警也失败了: instance_code={instance_code}, error={e}"
        )


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
