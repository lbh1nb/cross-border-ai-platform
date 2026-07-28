"""Listing 优化 Agent 的工具集：拉取待优化商品、LLM 优化 Listing、保存优化结果。

设计思想（v0.7.0 新增）：
- 与 selection_tools / insight_tools 保持一致的代码风格
- 3 工具：fetch_pending_listings / optimize_listing / save_listing
- LLM 调用预留完整接口，未配置 API Key 时自动用 Mock 模板化兜底
- 接入 API Key 后无需改代码，自动切换真实 LLM 生成优化文案

三个工具：
1. fetch_pending_listings：从 Listing 库拉取"待优化"状态的商品
2. optimize_listing：用 LLM 生成优化标题/五点描述/关键词/建议（Mock 兜底）
3. save_listing：把优化结果写回 Listing 库 + 推送联动卡片到飞书群
"""

from __future__ import annotations

import json
from datetime import datetime
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.ai.model_router import get_model_router
from src.ai.prompt_manager import get_prompt_manager
from src.config import settings
from src.feishu.application_bot import application_bot
from src.feishu.bitable import bitable_client
from src.feishu.card_templates import build_orchestration_card, build_table_url
from src.feishu.field_mapping import LISTING_FIELDS, LISTING_PRIMARY_KEYS
from src.observability.logger import get_logger

logger = get_logger()


# ============ 工具 1：拉取待优化 Listing ============

class FetchPendingListingsArgs(BaseModel):
    """拉取待优化 Listing 工具的参数 schema。"""

    limit: int = Field(
        default=5,
        description="最多拉取多少条待优化记录，默认 5，最大 20",
        ge=1,
        le=20,
    )


def _extract_text(field: Any) -> str:
    """从飞书字段值中提取纯文本（复用 insight_tools 同名函数逻辑）。"""
    if field is None:
        return ""
    if isinstance(field, str):
        return field
    if isinstance(field, (int, float)):
        return str(field)
    if isinstance(field, list) and field:
        first = field[0]
        if isinstance(first, dict):
            return first.get("text") or first.get("name") or str(first)
        return str(first)
    if isinstance(field, dict):
        return field.get("name") or field.get("text") or str(field)
    return str(field)


@tool(args_schema=FetchPendingListingsArgs)
def fetch_pending_listings(limit: int = 5) -> str:
    """从 Listing 库拉取"待优化"状态的商品列表。

    返回 JSON 格式的待优化商品列表，包含 ASIN、商品名称、原始标题。
    """
    logger.info(f"工具调用: fetch_pending_listings(limit={limit})")

    try:
        table_id = settings.feishu_table_id_listing
        if not table_id:
            return json.dumps(
                {"error": "未配置 Listing 库表 ID", "listings": []},
                ensure_ascii=False,
            )

        # 查询状态="待优化"的记录
        filter_condition = {
            "conjunction": "and",
            "conditions": [
                {
                    "field_name": LISTING_FIELDS["status"],
                    "operator": "is",
                    "value": ["待优化"],
                }
            ],
        }
        records = bitable_client.query_records(
            table_id, filter_condition=filter_condition
        )

        # 转换为 LLM 友好格式
        listings: list[dict[str, Any]] = []
        for r in records[:limit]:
            fields = r.get("fields", {})
            listings.append({
                "record_id": r.get("record_id", ""),
                "asin": _extract_text(fields.get(LISTING_FIELDS["asin"])),
                "name": _extract_text(fields.get(LISTING_FIELDS["name"])),
                "original_title": _extract_text(
                    fields.get(LISTING_FIELDS["original_title"])
                ),
            })

        result = {
            "count": len(listings),
            "listings": listings,
            "message": f"拉取到 {len(listings)} 条待优化记录",
        }
        logger.info(f"fetch_pending_listings 完成: 拉取 {len(listings)} 条")
        return json.dumps(result, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"fetch_pending_listings 失败: {e}", exc_info=True)
        return json.dumps({"error": str(e), "listings": []}, ensure_ascii=False)


# ============ 工具 2：LLM 优化 Listing ============

class OptimizeListingArgs(BaseModel):
    """LLM 优化 Listing 工具的参数 schema。"""

    listings_json: str = Field(
        description="待优化 Listing 列表 JSON（由 fetch_pending_listings 返回）"
    )


def _is_llm_configured() -> bool:
    """检查是否配置了可用的 LLM 凭证。

    用于决定是调用真实 LLM 还是使用 Mock 兜底。
    接入 API Key 后此函数自动返回 True，无需改代码。
    """
    return bool(settings.openai_api_key or settings.anthropic_api_key)


def _mock_optimize_single(listing: dict[str, Any]) -> dict[str, Any]:
    """Mock 模式：用模板化规则生成优化建议（不调 LLM）。

    用途：未配置 API Key 时保证流程跑通，方便联调测试。
    接入 Key 后此函数不再被调用，自动切换到真实 LLM。
    """
    asin = listing.get("asin", "")
    name = listing.get("name", "")
    original_title = listing.get("original_title") or name

    # 模板化优化（占位实现，符合计划"占位"定位）
    optimized_title = (
        f"{original_title} - Premium Quality | Fast Shipping | Top Rated"
        if len(original_title) < 180
        else original_title[:180]
    )
    optimized_bullets = (
        "1. 高品质材质：精选优质材料，耐用长久\n"
        "2. 多功能设计：满足多种使用场景\n"
        "3. 用户好评：累计好评率 95%+\n"
        "4. 快速配送：Prime 会员次日达\n"
        "5. 售后保障：30 天无理由退换"
    )
    backend_keywords = (
        f"{name}, best seller, premium, durable, "
        f"top rated, fast shipping, gift idea"
    )
    suggestion = (
        "【Mock 模式生成】建议：\n"
        "1. 标题补充品牌词和高搜索量关键词\n"
        "2. 五点描述突出差异化卖点\n"
        "3. 后台关键词补充长尾词\n"
        "（接入 API Key 后将自动切换为 LLM 真实优化）"
    )

    return {
        "asin": asin,
        "name": name,
        "optimized_title": optimized_title,
        "optimized_bullets": optimized_bullets,
        "backend_keywords": backend_keywords,
        "optimization_suggestion": suggestion,
        "ctr_estimate": 0.035,  # Mock 预估点击率 3.5%
        "source": "mock",
    }


def _llm_optimize_single(listing: dict[str, Any]) -> dict[str, Any]:
    """真实 LLM 模式：调用 LLM 生成优化文案。

    预留完整接口，接入 API Key 后自动启用。
    """
    router = get_model_router()
    pm = get_prompt_manager()
    llm = router.get_llm(task_type="standard", temperature=0.4)
    prompt = pm.get_prompt("listing_optimization")

    messages = prompt.format_messages(
        asin=listing.get("asin", ""),
        name=listing.get("name", ""),
        original_title=listing.get("original_title", ""),
    )

    logger.info(f"调用 LLM 优化 Listing ASIN={listing.get('asin')}")
    response = llm.invoke(messages)
    content = (
        response.content if hasattr(response, "content") else str(response)
    )
    content_text = content if isinstance(content, str) else str(content)

    # 尝试解析 LLM 返回的 JSON
    json_str = _extract_json(content_text)
    if json_str:
        result = json.loads(json_str)
        result["asin"] = listing.get("asin", "")
        result["name"] = listing.get("name", "")
        result["source"] = "llm"
        return result

    # LLM 未返回合法 JSON，回退到 Mock
    logger.warning(
        f"LLM 未返回合法 JSON，ASIN={listing.get('asin')} 回退到 Mock"
    )
    return _mock_optimize_single(listing)


def _extract_json(text: str) -> str | None:
    """从可能包含 ```json ``` 包裹的文本中提取 JSON 字符串。"""
    if "```json" in text:
        start = text.find("```json") + len("```json")
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()
    if "```" in text:
        start = text.find("```") + 3
        end = text.find("```", start)
        if end > start:
            return text[start:end].strip()
    # 尝试直接找 { ... } 块
    start = text.find("{")
    end = text.rfind("}")
    if start >= 0 and end > start:
        return text[start : end + 1]
    return None


@tool(args_schema=OptimizeListingArgs)
def optimize_listing(listings_json: str) -> str:
    """用 LLM 优化待优化 Listing 的标题/五点描述/关键词/建议。

    未配置 API Key 时自动用 Mock 模板化兜底，配置后自动切换真实 LLM。
    返回 JSON 格式的优化结果列表。
    """
    logger.info("工具调用: optimize_listing()")

    try:
        data = json.loads(listings_json)
        listings = data.get("listings", [])
        use_llm = _is_llm_configured()
        mode_desc = "LLM 真实模式" if use_llm else "Mock 兜底模式"
        logger.info(f"优化模式: {mode_desc}，共 {len(listings)} 条")

        results: list[dict[str, Any]] = []
        for listing in listings:
            try:
                if use_llm:
                    result = _llm_optimize_single(listing)
                else:
                    result = _mock_optimize_single(listing)
                results.append(result)
            except Exception as e:
                logger.warning(
                    f"优化失败 ASIN={listing.get('asin')}: {e}，回退到 Mock"
                )
                results.append(_mock_optimize_single(listing))

        output = {
            "mode": "llm" if use_llm else "mock",
            "count": len(results),
            "optimizations": results,
            "message": f"{mode_desc}完成 {len(results)} 条优化",
        }
        logger.info(f"optimize_listing 完成: {output['message']}")
        return json.dumps(output, ensure_ascii=False, indent=2)

    except Exception as e:
        logger.error(f"optimize_listing 失败: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============ 工具 3：保存优化结果 ============

class SaveListingArgs(BaseModel):
    """保存优化结果工具的参数 schema。"""

    optimizations_json: str = Field(
        description="优化结果 JSON（由 optimize_listing 返回）"
    )
    push_to_feishu: bool = Field(
        default=True,
        description="是否推送联动进度卡片到飞书群，默认 True",
    )


@tool(args_schema=SaveListingArgs)
def save_listing(optimizations_json: str, push_to_feishu: bool = True) -> str:
    """将 Listing 优化结果写回飞书 Listing 库 + 推送联动进度卡片到飞书群。

    动作：
    1. 按 ASIN 主键更新 Listing 库（优化标题/五点描述/关键词/建议/点击率预估）
    2. 状态从"待优化"改为"已优化"
    3. 推送一张联动进度卡片到飞书群（含优化统计和样本展示）
    """
    logger.info(f"工具调用: save_listing(push_to_feishu={push_to_feishu})")

    try:
        data = json.loads(optimizations_json)
        optimizations = data.get("optimizations", [])
        mode = data.get("mode", "unknown")

        table_id = settings.feishu_table_id_listing
        updated_count = 0
        failed_count = 0

        if table_id:
            # 构建 ASIN -> record_id 索引
            existing_records = bitable_client.query_records(table_id)
            asin_index: dict[str, str] = {}
            for r in existing_records:
                fields = r.get("fields", {})
                asin = _extract_text(fields.get(LISTING_FIELDS["asin"]))
                if asin and r.get("record_id"):
                    asin_index[asin] = r["record_id"]

            for opt in optimizations:
                asin = opt.get("asin", "")
                record_id = asin_index.get(asin, "")
                if not record_id:
                    logger.warning(f"未找到 ASIN={asin} 的记录，跳过")
                    failed_count += 1
                    continue

                update_fields = {
                    LISTING_FIELDS["optimized_title"]: opt.get(
                        "optimized_title", ""
                    ),
                    LISTING_FIELDS["optimized_bullets"]: opt.get(
                        "optimized_bullets", ""
                    ),
                    LISTING_FIELDS["backend_keywords"]: opt.get(
                        "backend_keywords", ""
                    ),
                    LISTING_FIELDS["optimization_suggestion"]: opt.get(
                        "optimization_suggestion", ""
                    ),
                    LISTING_FIELDS["ctr_estimate"]: opt.get(
                        "ctr_estimate", 0
                    ),
                    LISTING_FIELDS["status"]: "已优化",
                    LISTING_FIELDS["name"]: opt.get("name", ""),
                }
                try:
                    bitable_client.update_record(
                        table_id, record_id, update_fields
                    )
                    updated_count += 1
                except Exception as e:
                    failed_count += 1
                    logger.warning(
                        f"更新 Listing 失败 ASIN={asin}: {e}"
                    )
        else:
            logger.warning("未配置 Listing 库表 ID，跳过写回")

        # 推送联动进度卡片
        pushed = False
        if push_to_feishu:
            try:
                card = build_orchestration_card(
                    title="🎯 双 Agent 联动 · Listing 优化完成",
                    stage="listing_completed",
                    stats={
                        "优化模式": "LLM 真实调用" if mode == "llm" else "Mock 兜底",
                        "优化成功": f"{updated_count} 条",
                        "优化失败": f"{failed_count} 条",
                        "总处理": f"{updated_count + failed_count} 条",
                    },
                    samples=optimizations[:3],  # 展示前 3 条样本
                    table_url=build_table_url(table_id),
                )
                application_bot.send_card(card)
                pushed = True
                logger.info("联动进度卡片已推送到飞书群")
            except Exception as e:
                logger.error(f"推送联动进度卡片失败: {e}")

        result = {
            "updated_records": updated_count,
            "failed_records": failed_count,
            "mode": mode,
            "pushed_to_feishu": pushed,
            "message": (
                f"已更新 {updated_count} 条 Listing 记录"
                f"（失败 {failed_count} 条），"
                f"模式={mode}，"
                f"卡片推送{'成功' if pushed else '失败'}"
            ),
        }
        logger.info(f"save_listing 完成: {result}")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"save_listing 失败: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# 导出所有工具列表（供 Agent 注册使用）
LISTING_TOOLS = [fetch_pending_listings, optimize_listing, save_listing]
