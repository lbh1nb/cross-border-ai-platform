"""飞书交互卡片模板库。

集中管理各类业务卡片的 JSON 模板，避免在业务代码中硬编码卡片结构。
08-04 提供"库存预警卡片"，08-05 扩展"选品报告卡片""日报卡片"。

卡片 JSON 结构官方文档：
https://open.feishu.cn/document/uAjLw4CM/ukTMukTMukTM/ucTM5YjL3ETO24yNxkjN

卡片模板设计原则：
1. 标题颜色按严重程度区分（red=紧急/orange=预警/yellow=关注/green=正常/blue=普通通知）
2. 正文用 lark_md 格式，支持加粗、链接
3. 底部统一放"查看详情"按钮，跳转飞书多维表格
4. 按钮支持两种行为：
   - url：点击后跳转链接（适合查看详情场景）
   - value：点击后触发回调（适合审批/操作场景，需 08-05 回调服务支持）
5. 每个模板函数返回纯 dict，便于测试和复用
"""

from __future__ import annotations

from typing import Any

from src.config import settings


# 预警等级 -> 卡片标题颜色映射
ALERT_TEMPLATE_MAP = {
    "紧急": "red",
    "预警": "orange",
    "关注": "yellow",
    "正常": "green",
}


def build_inventory_alert_card(
    asin: str,
    product_name: str,
    sku: str,
    platform: str,
    stock_days: int,
    alert_level: str,
    current_stock: int = 0,
    daily_sales: float = 0.0,
    suggested_purchase: int = 0,
    table_url: str = "",
) -> dict[str, Any]:
    """构建库存预警交互卡片。

    当库存低于阈值时，发送此卡片到飞书群，包含商品信息和处理建议。

    Args:
        asin: 商品 ASIN
        product_name: 商品名称
        sku: 商品 SKU
        platform: 所属平台（亚马逊/沃尔玛/Wayfair）
        stock_days: 可售天数
        alert_level: 预警等级（紧急/预警/关注/正常）
        current_stock: 当前库存数量
        daily_sales: 日均销量
        suggested_purchase: 建议采购量
        table_url: 多维表格链接（用于"查看详情"按钮跳转）

    Returns:
        飞书卡片 JSON 对象

    示例：
        card = build_inventory_alert_card(
            asin="B08X4ABC",
            product_name="户外折叠椅",
            sku="CHAIR-001",
            platform="亚马逊",
            stock_days=5,
            alert_level="紧急",
            current_stock=25,
            daily_sales=5.0,
            suggested_purchase=100,
        )
        feishu_bot.send_card(card)
    """
    template_color = ALERT_TEMPLATE_MAP.get(alert_level, "blue")

    # 构建卡片正文内容（lark_md 格式，支持加粗和链接）
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**商品名称**\n{product_name}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**所属平台**\n{platform}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**ASIN**\n{asin}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**SKU**\n{sku}",
                    },
                },
            ],
        },
        {
            "tag": "hr",
        },
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**当前库存**\n{current_stock} 件",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**日均销量**\n{daily_sales:.1f} 件/天",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**可售天数**\n**{stock_days} 天**",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**预警等级**\n**{alert_level}**",
                    },
                },
            ],
        },
    ]

    # 建议采购量（仅当有值时显示）
    if suggested_purchase > 0:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**建议采购量**：{suggested_purchase} 件",
            },
        })

    # 添加处理建议
    suggestion_text = _get_alert_suggestion(alert_level, stock_days)
    if suggestion_text:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**处理建议**：{suggestion_text}",
            },
        })

    # 添加"查看详情"按钮（跳转多维表格）
    table_url = table_url or build_table_url()
    if table_url:
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看库存详情"},
                    "url": table_url,
                    "type": "primary",
                },
            ],
        })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"【{alert_level}】库存预警通知",
            },
            "template": template_color,
        },
        "elements": elements,
    }


def _get_alert_suggestion(alert_level: str, stock_days: int) -> str:
    """根据预警等级返回处理建议文案。

    Args:
        alert_level: 预警等级
        stock_days: 可售天数

    Returns:
        处理建议文本
    """
    if alert_level == "紧急":
        return f"可售天数仅 {stock_days} 天，请立即启动紧急采购流程，避免断货"
    if alert_level == "预警":
        return f"可售天数 {stock_days} 天，建议本周内安排补货"
    if alert_level == "关注":
        return f"可售天数 {stock_days} 天，请关注销售趋势，准备补货计划"
    return ""


def build_table_url(table_id: str = "") -> str:
    """构建飞书多维表格 URL（在飞书桌面端可直接打开，不跳浏览器）。

    使用企业租户域名生成链接（如 https://ocndodd7lmyr.feishu.cn/base/xxx?table=yyy），
    飞书桌面端会拦截本企业租户域名的链接，直接在飞书内打开多维表格。
    如果用通用 feishu.cn 域名，飞书桌面端不会拦截，会丢给浏览器导致需重新登录。

    Args:
        table_id: 表格 ID，留空则用库存预警表 ID

    Returns:
        多维表格 URL，若未配置租户域名或 app_token 则返回空字符串
    """
    app_token = settings.feishu_bitable_app_token
    tenant_domain = settings.feishu_tenant_domain
    target_table_id = table_id or settings.feishu_table_id_inventory
    if not app_token or not tenant_domain or not target_table_id:
        return ""
    return (
        f"https://{tenant_domain}.feishu.cn/base/{app_token}"
        f"?table={target_table_id}"
    )


# ===== 选品报告卡片 =====


def build_selection_report_card(
    date: str,
    total_configs: int,
    new_count: int,
    update_count: int,
    skip_count: int,
    fail_count: int,
    top_categories: list[str] | None = None,
    table_url: str = "",
) -> dict[str, Any]:
    """构建选品采集报告卡片。

    工作日 9:00 自动采集后，向飞书群发送当日采集统计。

    Args:
        date: 采集日期（如 "2026-07-26"）
        total_configs: 总配置数
        new_count: 新增商品数
        update_count: 更新商品数
        skip_count: 跳过数（无变化）
        fail_count: 失败数
        top_categories: 顶部品类列表（最多展示 3 个）
        table_url: 选品池表链接（用于"查看选品池"按钮跳转）

    Returns:
        飞书卡片 JSON 对象
    """
    total_processed = new_count + update_count
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**采集日期**\n{date}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**配置数**\n{total_configs} 条",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**新增商品**\n**{new_count}** 个",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**更新商品**\n{update_count} 个",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**跳过**\n{skip_count} 个",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**失败**\n{fail_count} 个",
                    },
                },
            ],
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**总处理商品数**：**{total_processed}** 个",
            },
        },
    ]

    # 顶部品类展示
    if top_categories:
        categories_text = " / ".join(top_categories[:3])
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**采集品类**：{categories_text}",
            },
        })

    # 失败数大于 0 时增加警告
    if fail_count > 0:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"⚠️ 有 {fail_count} 条配置采集失败，请查看日志排查原因",
            },
        })

    # 查看选品池按钮
    table_url = table_url or build_table_url(settings.feishu_table_id_selection)
    if table_url:
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看选品池"},
                    "url": table_url,
                    "type": "primary",
                },
            ],
        })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"【选品日报】{date} 采集完成",
            },
            "template": "blue",
        },
        "elements": elements,
    }


# ===== 日报卡片 =====


def build_daily_report_card(
    date: str,
    total_sales: float,
    total_orders: int,
    avg_acos: float,
    abnormal_count: int = 0,
    ai_insight: str = "",
    table_url: str = "",
) -> dict[str, Any]:
    """构建销售日报卡片。

    每天 18:00 自动生成日报后，向飞书群发送当日销售统计。

    Args:
        date: 日报日期（如 "2026-07-26"）
        total_sales: 总销售额（美金）
        total_orders: 总订单数
        avg_acos: 平均 ACoS（广告成本销售比，百分比）
        abnormal_count: 异常订单数（如退款率高、ACoS 过高）
        ai_insight: AI 洞察文本（可选，由第3周 AI Agent 生成）
        table_url: 销售日报表链接

    Returns:
        飞书卡片 JSON 对象
    """
    # 颜色策略：异常>0 用橙色，否则用绿色（正常）
    header_color = "orange" if abnormal_count > 0 else "green"

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**日报日期**\n{date}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**总订单数**\n{total_orders} 单",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**总销售额**\n**${total_sales:,.2f}**",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**平均 ACoS**\n{avg_acos:.1f}%",
                    },
                },
            ],
        },
        {"tag": "hr"},
    ]

    # 异常订单提示
    if abnormal_count > 0:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"⚠️ **异常订单**：{abnormal_count} 单，请关注退款率/ACoS 异常",
            },
        })
    else:
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": "✅ 当日无异常订单",
            },
        })

    # AI 洞察（可选）
    if ai_insight:
        elements.append({"tag": "hr"})
        elements.append({
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**AI 洞察**\n{ai_insight}",
            },
        })

    # 查看日报按钮
    table_url = table_url or build_table_url(settings.feishu_table_id_daily_report)
    if table_url:
        elements.append({
            "tag": "action",
            "actions": [
                {
                    "tag": "button",
                    "text": {"tag": "plain_text", "content": "查看销售日报"},
                    "url": table_url,
                    "type": "primary",
                },
            ],
        })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"【销售日报】{date}",
            },
            "template": header_color,
        },
        "elements": elements,
    }


# ===== 审批卡片（带回调按钮）=====


def build_approval_card(
    biz_type: str,
    biz_id: str,
    title: str,
    amount: float,
    description: str,
    operator: str = "",
    table_url: str = "",
) -> dict[str, Any]:
    """构建审批卡片（带"通过/拒绝"回调按钮）。

    用于选品金额 > 5000 美金时自动触发审批，用户点击按钮触发回调。

    Args:
        biz_type: 业务类型（如 "选品采购" / "库存补货"）
        biz_id: 业务唯一 ID（如 ASIN/SKU）
        title: 审批标题
        amount: 审批金额（美金）
        description: 审批描述
        operator: 申请人
        table_url: 关联表格链接

    Returns:
        飞书卡片 JSON 对象

    注意：
        按钮使用 value 字段（而非 url），点击后触发 card.action.trigger 回调。
        回调服务（card_callback.py）接收并处理。
    """
    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**业务类型**\n{biz_type}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**业务 ID**\n{biz_id}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**审批金额**\n**${amount:,.2f}**",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**申请人**\n{operator or '系统自动触发'}",
                    },
                },
            ],
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**审批说明**\n{description}",
            },
        },
    ]

    # 表格链接按钮（url 跳转）
    actions: list[dict[str, Any]] = []
    if table_url:
        actions.append({
            "tag": "button",
            "text": {"tag": "plain_text", "content": "查看详情"},
            "url": table_url,
            "type": "default",
        })

    # 审批按钮（value 回调）
    # 飞书卡片协议要求 value 对象里的值只能是 string/int/bool，不能是 float
    # 否则报错 230099: parse card json err
    amount_str = str(amount)
    actions.append({
        "tag": "button",
        "text": {"tag": "plain_text", "content": "✓ 通过"},
        "value": {
            "action": "approve",
            "biz_type": biz_type,
            "biz_id": biz_id,
            "amount": amount_str,
        },
        "type": "primary",
    })
    actions.append({
        "tag": "button",
        "text": {"tag": "plain_text", "content": "✗ 拒绝"},
        "value": {
            "action": "reject",
            "biz_type": biz_type,
            "biz_id": biz_id,
            "amount": amount_str,
        },
        "type": "danger",
    })

    elements.append({"tag": "action", "actions": actions})

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"【待审批】{title}",
            },
            "template": "orange",
        },
        "elements": elements,
    }


def build_approval_done_card(
    approved: bool,
    biz_type: str,
    biz_id: str,
    amount: float,
    approver: str = "",
    table_url: str = "",
) -> dict[str, Any]:
    """构建已审批卡片（用于回调返回时更新原卡片）。

    用户点击"通过"或"拒绝"后，回调服务返回此卡片替换原卡片，
    让按钮变灰不可点，防止重复审批。

    Args:
        approved: True=已通过, False=已拒绝
        biz_type: 业务类型
        biz_id: 业务 ID（ASIN/SKU）
        amount: 审批金额
        approver: 审批人 open_id
        table_url: 关联表格链接

    Returns:
        飞书卡片 JSON 对象（无按钮，仅显示审批结果）
    """
    status_text = "✅ 已通过" if approved else "❌ 已拒绝"
    header_template = "green" if approved else "red"

    elements: list[dict[str, Any]] = [
        {
            "tag": "div",
            "fields": [
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**业务类型**\n{biz_type}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**业务 ID**\n{biz_id}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**审批金额**\n${amount:,.2f}",
                    },
                },
                {
                    "is_short": True,
                    "text": {
                        "tag": "lark_md",
                        "content": f"**审批状态**\n{status_text}",
                    },
                },
            ],
        },
        {"tag": "hr"},
        {
            "tag": "div",
            "text": {
                "tag": "lark_md",
                "content": f"**审批人**\n{approver or '未知'}\n\n此审批已处理，多维表格审批状态已更新。",
            },
        },
    ]

    # 仅保留"查看详情"链接按钮，不再有审批按钮
    if table_url:
        elements.append({
            "tag": "action",
            "actions": [{
                "tag": "button",
                "text": {"tag": "plain_text", "content": "查看详情"},
                "url": table_url,
                "type": "default",
            }],
        })

    return {
        "config": {"wide_screen_mode": True},
        "header": {
            "title": {
                "tag": "plain_text",
                "content": f"【{status_text}】{biz_type}审批",
            },
            "template": header_template,
        },
        "elements": elements,
    }
