"""数据洞察 Agent 的工具集：拉数据、分析、推送日报。

设计思想：
- 复用 bitable_client 查询销售日报表和库存预警表
- 用 LLM 从三维度（销量/广告/库存）生成结构化洞察
- 把 AI 洞察写回销售日报表 + 推送日报卡片到飞书群

三个工具：
1. fetch_daily_data：拉昨日销售数据 + 当前库存预警数据
2. analyze_daily_data：用 LLM 分析三维度，输出结构化洞察 JSON
3. save_insight_report：写回 AI 洞察字段 + 推送日报卡片
"""

from __future__ import annotations

import json
from datetime import datetime, timedelta
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.ai.model_router import get_model_router
from src.ai.prompt_manager import get_prompt_manager
from src.config import settings
from src.feishu.application_bot import application_bot
from src.feishu.bitable import bitable_client
from src.feishu.card_templates import build_ai_insight_card, build_table_url
from src.observability.logger import get_logger

logger = get_logger()


# ============ 工具 1：拉取昨日业务数据 ============

class FetchDailyDataArgs(BaseModel):
    """拉取业务数据工具的参数 schema。"""

    target_date: str = Field(
        default="",
        description="目标日期，格式 YYYY-MM-DD。留空表示昨天",
    )


def _normalize_date(target_date: str) -> str:
    """归一化日期字符串为 YYYY-MM-DD。"""
    if not target_date:
        return (datetime.now() - timedelta(days=1)).strftime("%Y-%m-%d")
    # 兼容 datetime 格式
    try:
        return datetime.fromisoformat(target_date).strftime("%Y-%m-%d")
    except ValueError:
        return target_date


def _extract_field_value(field: Any) -> Any:
    """从飞书字段值中提取纯文本/数字。

    飞书多维表格字段值的格式：
    - 文本：[{"text": "内容", "type": "text"}]
    - 数字：123.45
    - 单选：{"name": "选项名"}
    - 日期：毫秒时间戳
    """
    if field is None:
        return ""
    if isinstance(field, (int, float)):
        return field
    if isinstance(field, str):
        return field
    if isinstance(field, list) and field:
        first = field[0]
        if isinstance(first, dict):
            return first.get("text") or first.get("name") or str(first)
        return str(first)
    if isinstance(field, dict):
        return field.get("name") or field.get("text") or str(field)
    return str(field)


def _query_sales_records(table_id: str, date_str: str) -> list[dict[str, Any]]:
    """查询指定日期的销售日报记录。

    抽成独立函数避免当天/前一天查询代码重复（v0.6.1 新增）。

    Args:
        table_id: 销售日报表 ID
        date_str: 目标日期 YYYY-MM-DD

    Returns:
        销售日报记录列表，每条含平台/销售额/订单数等字段
    """
    filter_condition = {
        "conjunction": "and",
        "conditions": [
            {
                "field_name": "日期",
                "operator": "is",
                "value": [date_str],
            }
        ],
    }
    raw_records = bitable_client.query_records(
        table_id, filter_condition=filter_condition
    )
    records: list[dict[str, Any]] = []
    for r in raw_records:
        fields = r.get("fields", {})
        records.append({
            "平台": _extract_field_value(fields.get("平台")),
            "销售额": _extract_field_value(fields.get("销售额")),
            "订单数": _extract_field_value(fields.get("订单数")),
            "广告花费": _extract_field_value(fields.get("广告花费")),
            "ACoS": _extract_field_value(fields.get("ACoS")),
            "退货数": _extract_field_value(fields.get("退货数")),
            "库存天数": _extract_field_value(fields.get("库存天数")),
            "异常标记": _extract_field_value(fields.get("异常标记")),
        })
    return records


@tool(args_schema=FetchDailyDataArgs)
def fetch_daily_data(target_date: str = "") -> str:
    """拉取昨日销售数据和当前库存预警数据。

    从飞书多维表格查询：
    - 销售日报表中目标日期的所有记录
    - 销售日报表中前一天的记录（v0.6.1 新增，用于销量环比异常检测）
    - 库存预警表中所有预警等级 != 正常 的记录
    - 自动执行硬规则异常检测（销量跌幅 > 30% 标红，ACoS > 50% 标低效）

    Args:
        target_date: 目标日期 YYYY-MM-DD，留空表示昨天

    Returns:
        JSON 字符串，含 sales_records/previous_sales_records/inventory_records/anomalies
    """
    date_str = _normalize_date(target_date)
    # 前一天日期（v0.6.1 新增：用于销量环比异常检测）
    prev_date_str = (
        datetime.fromisoformat(date_str) - timedelta(days=1)
    ).strftime("%Y-%m-%d")
    logger.info(f"开始拉取 {date_str} 的业务数据（前一天 {prev_date_str} 用于环比）")

    sales_records: list[dict[str, Any]] = []
    previous_sales_records: list[dict[str, Any]] = []
    inventory_records: list[dict[str, Any]] = []

    try:
        # 1. 拉销售日报数据（当天 + 前一天，用于环比异常检测）
        sales_table_id = settings.feishu_table_id_daily_report
        if sales_table_id:
            # 当天数据
            sales_records = _query_sales_records(sales_table_id, date_str)
            logger.info(f"拉取销售日报 {date_str}: {len(sales_records)} 条")
            # 前一天数据（v0.6.1 新增：用于销量跌幅检测）
            previous_sales_records = _query_sales_records(sales_table_id, prev_date_str)
            logger.info(f"拉取销售日报 {prev_date_str}: {len(previous_sales_records)} 条")
        else:
            logger.warning("未配置销售日报表 ID")

        # 2. 拉库存预警数据（预警等级 != 正常）
        inventory_table_id = settings.feishu_table_id_inventory
        if inventory_table_id:
            filter_condition = {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": "预警等级",
                        "operator": "isNot",
                        "value": ["正常"],
                    }
                ],
            }
            raw_records = bitable_client.query_records(
                inventory_table_id, filter_condition=filter_condition
            )
            for r in raw_records:
                fields = r.get("fields", {})
                inventory_records.append({
                    "ASIN": _extract_field_value(fields.get("ASIN")),
                    "商品名称": _extract_field_value(fields.get("商品名称")),
                    "SKU": _extract_field_value(fields.get("SKU")),
                    "平台": _extract_field_value(fields.get("平台")),
                    "当前库存": _extract_field_value(fields.get("当前库存")),
                    "日均销量": _extract_field_value(fields.get("日均销量")),
                    "可售天数": _extract_field_value(fields.get("可售天数")),
                    "预警等级": _extract_field_value(fields.get("预警等级")),
                    "建议采购量": _extract_field_value(fields.get("建议采购量")),
                })
            logger.info(f"拉取库存预警: {len(inventory_records)} 条非正常记录")
        else:
            logger.warning("未配置库存预警表 ID")

    except Exception as e:
        logger.error(f"拉取业务数据失败: {e}", exc_info=True)
        return json.dumps(
            {"error": str(e), "sales_records": [], "inventory_records": []},
            ensure_ascii=False,
        )

    # 3. 硬规则异常检测（v0.6.1 新增：销量跌幅 > 30% 自动标红）
    # 不依赖 LLM，用确定性规则检测异常，结果同时供 LLM 分析和预警卡片使用
    from src.ai.agents.anomaly_detector import detect_anomalies

    anomalies = detect_anomalies(sales_records, previous_sales_records)

    result = {
        "date": date_str,
        "previous_date": prev_date_str,
        "sales_records": sales_records,
        "previous_sales_records": previous_sales_records,
        "inventory_records": inventory_records,
        "sales_count": len(sales_records),
        "inventory_alert_count": len(inventory_records),
        "anomalies": anomalies,
    }
    logger.info(
        f"fetch_daily_data 完成: 销售 {len(sales_records)} 条，"
        f"库存预警 {len(inventory_records)} 条，异常 {len(anomalies)} 条"
    )
    return json.dumps(result, ensure_ascii=False)


# ============ 工具 2：LLM 分析三维度 ============

class AnalyzeDailyDataArgs(BaseModel):
    """分析数据工具的参数 schema。"""

    data_json: str = Field(
        description="fetch_daily_data 返回的 JSON 字符串"
    )


@tool(args_schema=AnalyzeDailyDataArgs)
def analyze_daily_data(data_json: str) -> str:
    """用 LLM 分析昨日业务数据，生成三维度洞察。

    分析维度：
    - 销量：销售额/订单数趋势，异常跌幅标记
    - 广告：ACoS 评估，优化建议
    - 库存：断货风险，补货优先级

    Args:
        data_json: fetch_daily_data 返回的 JSON

    Returns:
        JSON 字符串，含 sales_insight/ad_insight/inventory_insight 等
    """
    try:
        data = json.loads(data_json)
        sales_records = data.get("sales_records", [])
        previous_sales_records = data.get("previous_sales_records", [])
        inventory_records = data.get("inventory_records", [])
        anomalies = data.get("anomalies", [])
        date_str = data.get("date", "未知日期")

        # 格式化数据供 LLM 阅读
        sales_text = json.dumps(sales_records, ensure_ascii=False, indent=2) or "无销售数据"
        previous_sales_text = (
            json.dumps(previous_sales_records, ensure_ascii=False, indent=2)
            or "无前一天数据"
        )
        inventory_text = json.dumps(inventory_records, ensure_ascii=False, indent=2) or "无库存预警"
        # v0.6.1 新增：把硬规则检测到的异常信息也喂给 LLM，让 LLM 重点解释
        anomalies_text = (
            json.dumps(anomalies, ensure_ascii=False, indent=2)
            if anomalies
            else "无硬规则检测到的异常"
        )

        # 调用 LLM 分析
        pm = get_prompt_manager()
        router = get_model_router()
        llm = router.get_llm(task_type="standard")  # 数据分析用 standard 模型

        # v0.6.1 新增：把前一天数据和硬规则异常检测结果一起传给 LLM
        # 让 LLM 能基于确定的异常事实给出更准确的解释和建议
        prompt = pm.get_prompt("insight_analysis")
        messages = prompt.format_messages(
            sales_data=sales_text,
            inventory_data=inventory_text,
        )
        # 在最后追加前一天数据和异常检测结果作为补充上下文
        from langchain_core.messages import HumanMessage

        messages.append(HumanMessage(
            content=(
                f"## 补充上下文（v0.6.1 新增）\n\n"
                f"### 前一天销售数据（用于环比）\n{previous_sales_text}\n\n"
                f"### 硬规则异常检测结果（确定性事实，请重点解释这些异常）\n{anomalies_text}\n\n"
                f"请在 sales_insight.anomaly 字段中明确说明异常情况，"
                f"若无异常则填空字符串。"
            )
        ))

        logger.info(f"调用 LLM 分析日报数据，日期={date_str}")
        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)

        # 尝试解析 JSON（LLM 可能包裹在 ```json 中）
        content_text = content if isinstance(content, str) else str(content)
        json_str = _extract_json(content_text)
        if json_str:
            analysis = json.loads(json_str)
        else:
            # LLM 未返回合法 JSON，用兜底结构
            logger.warning("LLM 未返回合法 JSON，使用兜底结构")
            analysis = {
                "date": date_str,
                "sales_insight": {"summary": content_text[:200]},
                "ad_insight": {},
                "inventory_insight": {},
                "top_priority": "请联系技术支持核查 LLM 输出",
                "action_items": [],
            }

        result = {
            "date": date_str,
            "analysis": analysis,
            "anomalies": anomalies,  # v0.6.1 新增：透传硬规则异常给 save_insight_report
            "raw_llm_output": content_text,
        }
        logger.info(
            f"analyze_daily_data 完成，"
            f"LLM 分析 {len(sales_records)} 条销售数据，"
            f"硬规则异常 {len(anomalies)} 条"
        )
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"analyze_daily_data 失败: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _extract_json(text: str) -> str | None:
    """从文本中提取 JSON 字符串。

    支持：
    - 纯 JSON
    - ```json ... ``` 包裹的 JSON
    - ``` ... ``` 包裹的 JSON
    """
    text = text.strip()
    # 尝试直接解析
    if text.startswith("{"):
        return text
    # 尝试从 ```json ``` 中提取
    if "```json" in text:
        start = text.find("```json") + 7
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()
    # 尝试从 ``` ``` 中提取
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()
    # 尝试找第一个 { 到最后一个 }
    first_brace = text.find("{")
    last_brace = text.rfind("}")
    if first_brace >= 0 and last_brace > first_brace:
        return text[first_brace : last_brace + 1]
    return None


# ============ 工具 3：保存洞察报告 + 推送日报卡片 ============

class SaveInsightReportArgs(BaseModel):
    """保存洞察报告工具的参数 schema。"""

    analysis_json: str = Field(
        description="analyze_daily_data 返回的 JSON 字符串"
    )
    push_to_feishu: bool = Field(
        default=True,
        description="是否推送日报卡片到飞书群",
    )


@tool(args_schema=SaveInsightReportArgs)
def save_insight_report(analysis_json: str, push_to_feishu: bool = True) -> str:
    """将 AI 洞察写回销售日报表 + 推送日报卡片到飞书群。

    动作：
    1. 把 AI 洞察文本写入销售日报表的"AI洞察"字段（每条记录都更新）
    2. v0.6.1 新增：检测到异常时，把"异常标记"字段标红（销量下跌/ACoS过高）
    3. 推送一张日报卡片到飞书群（含三维度概览 + 异常标记 + 行动建议）
    4. v0.6.1 新增：如果硬规则检测到异常，额外推送一张红色异常预警卡片

    Args:
        analysis_json: analyze_daily_data 返回的 JSON
        push_to_feishu: 是否推送飞书群

    Returns:
        JSON 字符串，含 updated_records 和 pushed_to_feishu
    """
    try:
        data = json.loads(analysis_json)
        analysis = data.get("analysis", {})
        anomalies = data.get("anomalies", [])  # v0.6.1 新增
        date_str = data.get("date", "")

        # 1. 写回销售日报表 AI 洞察字段 + 异常标记字段
        updated_count = 0
        marked_anomaly_count = 0
        sales_table_id = settings.feishu_table_id_daily_report
        if sales_table_id:
            # 查询目标日期的所有记录，逐条更新 AI 洞察字段
            filter_condition = {
                "conjunction": "and",
                "conditions": [
                    {
                        "field_name": "日期",
                        "operator": "is",
                        "value": [date_str],
                    }
                ],
            }
            records = bitable_client.query_records(
                sales_table_id, filter_condition=filter_condition
            )

            # 从 analysis 提取要写入的洞察文本
            table_insight = _build_table_insight(analysis)

            # v0.6.1 新增：构建 平台 -> 异常类型 映射，用于标红表格"异常标记"字段
            anomaly_map: dict[str, str] = {}
            for a in anomalies:
                platform = a.get("platform", "")
                anomaly_type = a.get("type", "")
                if platform and anomaly_type:
                    anomaly_map[platform] = anomaly_type

            for r in records:
                record_id = r.get("record_id", "")
                if not record_id:
                    continue
                try:
                    # 基础更新字段：AI 洞察
                    update_fields: dict[str, Any] = {"AI洞察": table_insight}

                    # v0.6.1 新增：如果该平台命中异常，把"异常标记"字段标红
                    fields = r.get("fields", {})
                    platform = _extract_field_value(fields.get("平台"))
                    if platform in anomaly_map:
                        update_fields["异常标记"] = anomaly_map[platform]
                        marked_anomaly_count += 1

                    bitable_client.update_record(
                        sales_table_id, record_id, update_fields
                    )
                    updated_count += 1
                except Exception as e:
                    logger.warning(f"更新 AI 洞察失败 record_id={record_id}: {e}")

            logger.info(
                f"已更新 {updated_count} 条销售日报的 AI 洞察字段，"
                f"其中 {marked_anomaly_count} 条标红异常标记"
            )
        else:
            logger.warning("未配置销售日报表 ID，跳过 AI 洞察写回")

        # 2. 推送日报卡片到飞书群
        pushed = False
        if push_to_feishu:
            try:
                card = build_ai_insight_card(
                    date_str=date_str,
                    analysis=analysis,
                    table_url=build_table_url(sales_table_id),
                )
                application_bot.send_card(card)
                pushed = True
                logger.info("数据洞察日报卡片已推送到飞书群")
            except Exception as e:
                logger.error(f"推送日报卡片失败: {e}")

        # v0.6.1 新增：如果有异常，额外推送一张红色异常预警卡片
        anomaly_pushed = False
        if push_to_feishu and anomalies:
            try:
                from src.feishu.card_templates import build_anomaly_alert_card

                alert_card = build_anomaly_alert_card(
                    date_str=date_str,
                    anomalies=anomalies,
                    table_url=build_table_url(sales_table_id),
                )
                application_bot.send_card(alert_card)
                anomaly_pushed = True
                logger.warning(
                    f"检测到 {len(anomalies)} 条异常，已推送红色异常预警卡片"
                )
            except Exception as e:
                logger.error(f"推送异常预警卡片失败: {e}")

        result = {
            "updated_records": updated_count,
            "marked_anomaly_records": marked_anomaly_count,
            "pushed_to_feishu": pushed,
            "anomaly_alert_pushed": anomaly_pushed,
            "anomaly_count": len(anomalies),
            "message": (
                f"已更新 {updated_count} 条日报记录"
                f"（其中 {marked_anomaly_count} 条标红异常），"
                f"日报卡片推送{'成功' if pushed else '失败'}，"
                f"异常预警卡片{'已推送' if anomaly_pushed else '未推送（无异常或失败）'}"
            ),
        }
        logger.info(f"save_insight_report 完成: {result}")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"save_insight_report 失败: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


def _build_table_insight(analysis: dict[str, Any]) -> str:
    """从 analysis 结构中提取要写入表格 AI 洞察字段的文本。"""
    parts: list[str] = []

    sales = analysis.get("sales_insight", {})
    if sales.get("summary"):
        parts.append(f"销量: {sales['summary']}")

    ad = analysis.get("ad_insight", {})
    if ad.get("acos_eval"):
        parts.append(f"广告: {ad['acos_eval']}")

    inv = analysis.get("inventory_insight", {})
    if inv.get("health"):
        parts.append(f"库存: {inv['health']}")

    if analysis.get("top_priority"):
        parts.append(f"优先: {analysis['top_priority']}")

    return " | ".join(parts)[:200] if parts else "AI 洞察生成中"


# 导出所有工具列表（供 Agent 注册使用）
INSIGHT_TOOLS = [fetch_daily_data, analyze_daily_data, save_insight_report]
