"""选品 Agent 的工具集：抓取、分析、报告。

设计思想：
- 每个工具是一个独立函数，用 LangChain @tool 装饰器封装
- 工具复用已有的 BaseCollector 和 bitable_client，不重复造轮子
- 工具输入输出都用 JSON 序列化，便于 LLM 理解

三个工具：
1. fetch_products：抓取指定品类的商品数据（复用 MockAmazonCollector）
2. analyze_products：用 LLM 分析商品数据，输出结构化选品建议
3. save_report：将分析结果写入飞书多维表格 + 推送卡片到群
"""

from __future__ import annotations

import json
from typing import Any

from langchain_core.tools import tool
from pydantic import BaseModel, Field

from src.ai.model_router import get_model_router
from src.ai.prompt_manager import get_prompt_manager
from src.config import settings
from src.feishu.application_bot import application_bot
from src.feishu.bitable import bitable_client
from src.feishu.card_templates import build_ai_analysis_card, build_table_url
from src.observability.logger import get_logger
from src.pipeline.collectors.amazon_mock import MockAmazonCollector

logger = get_logger()


# ============ 工具 1：抓取商品数据 ============

class FetchProductsArgs(BaseModel):
    """抓取商品工具的参数 schema。"""

    category: str = Field(
        description="品类名称，如 '家居收纳'、'厨房用品'、'户外家具'、'办公家具'、'卧室家具'"
    )
    limit: int = Field(
        default=10,
        description="抓取数量，默认 10，最大 50",
        ge=1,
        le=50,
    )


@tool(args_schema=FetchProductsArgs)
def fetch_products(category: str, limit: int = 10) -> str:
    """抓取指定品类的亚马逊热卖商品数据。

    返回 JSON 格式的商品列表，包含 ASIN、名称、价格、评分、评论数、BSR 排名等。
    """
    logger.info(f"工具调用: fetch_products(category={category}, limit={limit})")

    try:
        collector = MockAmazonCollector(seed=42)
        products = collector.collect(category=category, limit=limit)
        collector.close()

        # 序列化为 JSON（LLM 友好格式）
        products_data = [
            {
                "asin": p.asin,
                "name": p.name,
                "category": p.category,
                "price_range": f"${p.price_min}-${p.price_max}",
                "rating": p.rating,
                "review_count": p.review_count,
                "bsr_rank": p.bsr_rank,
                "market_capacity": p.market_capacity,
                "competition_level": p.competition_level,
                "profit_margin": p.profit_margin,
            }
            for p in products
        ]

        result = json.dumps(products_data, ensure_ascii=False, indent=2)
        logger.info(f"抓取成功：{len(products)} 个商品")
        return result

    except Exception as e:
        logger.error(f"fetch_products 失败: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============ 工具 2：分析商品数据 ============

class AnalyzeProductsArgs(BaseModel):
    """分析商品工具的参数 schema。"""

    category: str = Field(description="品类名称")
    products_json: str = Field(
        description="商品数据 JSON 字符串（由 fetch_products 工具返回）"
    )


@tool(args_schema=AnalyzeProductsArgs)
def analyze_products(category: str, products_json: str) -> str:
    """用 LLM 分析商品数据，从市场容量、竞争强度、利润空间三维度评估选品机会。

    返回结构化 JSON，包含 top_picks（推荐商品列表）和 summary（总体分析）。
    """
    logger.info(f"工具调用: analyze_products(category={category})")

    try:
        # 解析商品数据
        products = json.loads(products_json)
        product_count = len(products)

        # 获取 LLM 和 Prompt
        router = get_model_router()
        pm = get_prompt_manager()

        llm = router.get_llm("standard", temperature=0.3)
        prompt = pm.get_prompt("selection_analysis")

        # 渲染 Prompt 并调用 LLM
        messages = prompt.format_messages(
            category=category,
            product_count=product_count,
            products_json=products_json,
        )

        logger.info(f"调用 LLM 分析 {product_count} 个商品...")
        response = llm.invoke(messages)
        content = response.content if hasattr(response, "content") else str(response)

        logger.info("LLM 分析完成")
        return content

    except Exception as e:
        logger.error(f"analyze_products 失败: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# ============ 工具 3：保存报告 ============

class SaveReportArgs(BaseModel):
    """保存报告工具的参数 schema。"""

    analysis_json: str = Field(
        description="分析结果 JSON 字符串（由 analyze_products 工具返回）"
    )
    push_to_feishu: bool = Field(
        default=True,
        description="是否推送报告到飞书群，默认 True",
    )


@tool(args_schema=SaveReportArgs)
def save_report(analysis_json: str, push_to_feishu: bool = True) -> str:
    """将选品分析结果写入飞书多维表格并推送卡片到飞书群。

    成功返回保存的记录数和推送状态。
    """
    logger.info(f"工具调用: save_report(push_to_feishu={push_to_feishu})")

    try:
        analysis = json.loads(analysis_json)
        category = analysis.get("category", "未知品类")
        top_picks = analysis.get("top_picks", [])
        summary = analysis.get("summary", "")

        # 1. 写入飞书多维表格（选品池表）
        table_id = settings.feishu_table_id_selection
        saved_count = 0

        if table_id:
            for pick in top_picks:
                try:
                    record = {
                        "商品名称": pick.get("name", ""),
                        "ASIN": pick.get("asin", ""),
                        "品类": category,
                        "来源平台": "亚马逊",
                        "市场容量": analysis.get("market_capacity", ""),
                        "竞争强度": analysis.get("competition_level", ""),
                        "利润空间": pick.get("estimated_margin", ""),
                    }
                    bitable_client.create_record(table_id, record)
                    saved_count += 1
                except Exception as e:
                    logger.warning(f"保存记录失败 ASIN={pick.get('asin')}: {e}")
        else:
            logger.warning("未配置选品池表 ID，跳过多维表格写入")

        # 2. 推送 AI 分析报告卡片到飞书群（v0.5.2 改用交互卡片）
        pushed = False
        if push_to_feishu:
            try:
                card = build_ai_analysis_card(
                    category=category,
                    market_capacity=analysis.get("market_capacity", "未知"),
                    competition_level=analysis.get("competition_level", "未知"),
                    profit_potential=analysis.get("profit_potential", "未知"),
                    top_picks=top_picks,
                    summary=summary,
                    table_url=build_table_url(settings.feishu_table_id_selection),
                )
                application_bot.send_card(card)
                pushed = True
                logger.info("AI 分析报告卡片已推送到飞书群")
            except Exception as e:
                logger.error(f"推送飞书群失败: {e}")

        result = {
            "saved_records": saved_count,
            "pushed_to_feishu": pushed,
            "message": f"已保存 {saved_count} 条记录到多维表格，"
                       f"飞书群推送{'成功' if pushed else '失败'}",
        }
        logger.info(f"save_report 完成: {result}")
        return json.dumps(result, ensure_ascii=False)

    except Exception as e:
        logger.error(f"save_report 失败: {e}", exc_info=True)
        return json.dumps({"error": str(e)}, ensure_ascii=False)


# 导出所有工具列表（供 Agent 注册使用）
SELECTION_TOOLS = [fetch_products, analyze_products, save_report]
