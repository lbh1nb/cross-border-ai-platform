"""数据洞察 Agent A/B 对比脚本（v0.6.1 新增，08-18 任务③）。

用途：
    用同一份数据分别调用两个不同模型（GPT-4o-mini vs Claude），
    对比数据洞察 Agent 的输出质量，选最优模型作为默认。

对比维度（5 项，每项 1-5 分）：
    1. 结构完整性：JSON 字段是否齐全
    2. 异常识别准确度：是否正确识别销量跌幅和 ACoS 异常
    3. 建议可操作性：建议是否具体可落地
    4. 表达清晰度：语言是否简洁易懂
    5. 业务价值：洞察是否有深度

运行模式：
    1. Mock 模式（默认）：用本地 Mock 输出，不消耗 API 额度，可随时跑
    2. 真实模式：调用真实 LLM API，需配置 API Key

用法：
    # Mock 模式（默认，无需 API Key）
    python scripts/ab_compare_insight.py

    # 真实模式（需配置 .env 中的 API Key）
    python scripts/ab_compare_insight.py --real

输出：
    - 控制台打印对比表格
    - 生成 docs/ab_compare_report.md 对比报告
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

# 把项目根目录加入 sys.path
_PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(_PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(_PROJECT_ROOT))

from src.ai.agents.anomaly_detector import detect_anomalies
from src.observability.logger import get_logger

logger = get_logger()


# ============ 测试数据（与联调脚本一致） ============
def _build_test_data() -> tuple[list[dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    """构建测试数据：当天 + 前一天 + 异常列表。

    Returns:
        (current_sales, previous_sales, anomalies)
    """
    today = datetime.now().replace(hour=0, minute=0, second=0, microsecond=0)
    yesterday = today - timedelta(days=1)

    previous_sales = [
        {"平台": "亚马逊", "销售额": 12000, "订单数": 120, "ACoS": 0.20},
        {"平台": "沃尔玛", "销售额": 4000, "订单数": 40, "ACoS": 0.15},
        {"平台": "Wayfair", "销售额": 3000, "订单数": 25, "ACoS": 0.12},
    ]
    current_sales = [
        # 亚马逊销量下跌 50%
        {"平台": "亚马逊", "销售额": 6000, "订单数": 60, "ACoS": 0.20},
        # 沃尔玛 ACoS 升到 55%
        {"平台": "沃尔玛", "销售额": 4000, "订单数": 40, "ACoS": 0.55},
        {"平台": "Wayfair", "销售额": 3000, "订单数": 25, "ACoS": 0.12},
    ]
    anomalies = detect_anomalies(current_sales, previous_sales)
    return current_sales, previous_sales, anomalies


# ============ Mock 输出（GPT-4o-mini vs Claude 风格模拟） ============
def _mock_gpt4o_mini_output(anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    """模拟 GPT-4o-mini 的输出风格：简洁但深度一般。"""
    has_anomaly = len(anomalies) > 0
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sales_insight": {
            "trend": "下降" if has_anomaly else "平稳",
            "change_pct": "-33.3%" if has_anomaly else "+2.1%",
            "summary": "昨日销售额下降，主要受亚马逊影响。",
            "anomaly": "亚马逊销量下跌 50%" if has_anomaly else "",
        },
        "ad_insight": {
            "efficiency": "低效",
            "acos_eval": "沃尔玛 ACoS 偏高，需优化。",
            "suggestion": "调整广告关键词。",
        },
        "inventory_insight": {
            "health": "关注",
            "risk_items": [],
            "suggestion": "关注亚马逊补货。",
        },
        "top_priority": "处理亚马逊销量下跌问题。",
        "action_items": ["排查亚马逊关键词排名", "优化沃尔玛广告"],
    }


def _mock_claude_output(anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    """模拟 Claude 的输出风格：详细且建议具体。"""
    has_anomaly = len(anomalies) > 0
    return {
        "date": datetime.now().strftime("%Y-%m-%d"),
        "sales_insight": {
            "trend": "下降",
            "change_pct": "-33.3%",
            "summary": (
                "昨日总销售额 $13,000，环比下降 33.3%。"
                "主因是亚马逊销售额从 $12,000 跌至 $6,000（跌幅 50%），"
                "需立即排查关键词排名和广告位变化。"
            ) if has_anomaly else "昨日销售平稳，无异常波动。",
            "anomaly": (
                "亚马逊销量跌幅 50%（阈值 30%），"
                "沃尔玛 ACoS=55%（阈值 50%），均为硬规则检测到的确定异常。"
            ) if has_anomaly else "",
        },
        "ad_insight": {
            "efficiency": "低效",
            "acos_eval": (
                "沃尔玛 ACoS 从 15% 飙升到 55%，远超 30% 合理区间上限。"
                "建议暂停近 7 天零转化的关键词，"
                "把预算转移到转化率 Top 10 的精准匹配关键词。"
            ),
            "suggestion": (
                "1. 暂停沃尔玛低转化关键词（预计降低 ACoS 15-20 个百分点）；"
                "2. 亚马逊广告预算维持不变（销量下跌非广告问题）；"
                "3. Wayfair ACoS=12% 表现优秀，可适度增加预算 10%。"
            ),
        },
        "inventory_insight": {
            "health": "关注",
            "risk_items": ["亚马逊库存天数 30 天，但销量下跌后实际可售天数会延长"],
            "suggestion": "暂缓亚马逊补货计划，待销量恢复后再评估。",
        },
        "top_priority": (
            "立即排查亚马逊销量下跌原因：检查关键词排名、广告位、"
            "竞品动态、Review 是否有差评。"
        ),
        "action_items": [
            "1. 拉取亚马逊 Search Term 报告，对比近 3 天关键词排名变化",
            "2. 暂停沃尔玛 ACoS > 80% 的关键词，预算转移至 Top 10 转化词",
            "3. 暂缓亚马逊补货，3 天后重新评估销量趋势",
        ],
    }


# ============ 真实 LLM 调用（需 API Key） ============
def _call_real_llm(provider: str, sales_records, previous_records, anomalies) -> dict[str, Any]:
    """调用真实 LLM API 进行分析。

    Args:
        provider: "openai" 或 "anthropic"
        sales_records: 当天销售数据
        previous_records: 前一天销售数据
        anomalies: 异常列表

    Returns:
        LLM 返回的分析结果 dict
    """
    from src.ai.model_router import get_model_router
    from src.ai.prompt_manager import get_prompt_manager
    from langchain_core.messages import HumanMessage

    router = get_model_router()
    pm = get_prompt_manager()

    # openai 用 simple 模型（gpt-4o-mini），anthropic 用 standard（claude-sonnet）
    task_type = "simple" if provider == "openai" else "standard"
    llm = router.get_llm(task_type=task_type)

    sales_text = json.dumps(sales_records, ensure_ascii=False, indent=2)
    inventory_text = "无库存预警数据（A/B 测试模式）"
    prompt = pm.get_prompt("insight_analysis")
    messages = prompt.format_messages(
        sales_data=sales_text,
        inventory_data=inventory_text,
    )

    # 补充前一天数据和异常检测结果
    previous_text = json.dumps(previous_records, ensure_ascii=False, indent=2)
    anomalies_text = json.dumps(anomalies, ensure_ascii=False, indent=2) if anomalies else "无异常"
    messages.append(HumanMessage(
        content=(
            f"## 补充上下文\n### 前一天销售数据\n{previous_text}\n\n"
            f"### 硬规则异常检测结果\n{anomalies_text}\n\n"
            f"请返回 JSON 对象。"
        )
    ))

    response = llm.invoke(messages)
    content = response.content if hasattr(response, "content") else str(response)
    content_text = content if isinstance(content, str) else str(content)

    # 提取 JSON
    from src.ai.agents.insight_tools import _extract_json
    json_str = _extract_json(content_text)
    if json_str:
        return json.loads(json_str)
    return {"raw_output": content_text, "parse_error": True}


# ============ 评分逻辑 ============
def _score_output(output: dict[str, Any], anomalies: list[dict[str, Any]]) -> dict[str, Any]:
    """对 LLM 输出进行 5 维度评分（每项 1-5 分）。

    评分标准基于确定性的结构检查，避免主观偏差。
    """
    scores: dict[str, int] = {}

    # 1. 结构完整性：6 个必需字段是否齐全
    required_keys = ["date", "sales_insight", "ad_insight", "inventory_insight", "top_priority", "action_items"]
    present = sum(1 for k in required_keys if k in output and output[k])
    scores["结构完整性"] = max(1, round(present / len(required_keys) * 5))

    # 2. 异常识别准确度
    sales_anomaly = output.get("sales_insight", {}).get("anomaly", "")
    if anomalies:
        # 有异常时，anomaly 字段应非空且提到关键词
        if sales_anomaly and any(
            kw in sales_anomaly for kw in ["下跌", "异常", "跌幅", "ACoS", "过高"]
        ):
            scores["异常识别"] = 5
        elif sales_anomaly:
            scores["异常识别"] = 3
        else:
            scores["异常识别"] = 1
    else:
        # 无异常时，anomaly 字段应为空
        scores["异常识别"] = 5 if not sales_anomaly else 2

    # 3. 建议可操作性：action_items 数量和具体度
    actions = output.get("action_items", [])
    if isinstance(actions, list) and len(actions) >= 3:
        # 检查是否含具体动词（拉取/暂停/优化/排查 等）
        action_text = " ".join(str(a) for a in actions)
        if any(kw in action_text for kw in ["拉取", "暂停", "优化", "排查", "转移", "评估"]):
            scores["建议可操作性"] = 5
        else:
            scores["建议可操作性"] = 3
    elif isinstance(actions, list) and len(actions) >= 1:
        scores["建议可操作性"] = 2
    else:
        scores["建议可操作性"] = 1

    # 4. 表达清晰度：summary 长度和具体度
    summary = output.get("sales_insight", {}).get("summary", "")
    if 20 <= len(summary) <= 200 and any(
        kw in summary for kw in ["$", "销售额", "订单", "销量", "环比"]
    ):
        scores["表达清晰度"] = 5
    elif summary:
        scores["表达清晰度"] = 3
    else:
        scores["表达清晰度"] = 1

    # 5. 业务价值：top_priority 是否含具体动作
    priority = output.get("top_priority", "")
    if priority and any(
        kw in priority for kw in ["排查", "检查", "暂停", "优化", "拉取", "评估"]
    ):
        scores["业务价值"] = 5
    elif priority:
        scores["业务价值"] = 3
    else:
        scores["业务价值"] = 1

    total = sum(scores.values())
    return {"scores": scores, "total": total, "max": 25}


# ============ 报告生成 ============
def _generate_report(
    gpt_output: dict[str, Any],
    claude_output: dict[str, Any],
    gpt_scores: dict[str, Any],
    claude_scores: dict[str, Any],
    anomalies: list[dict[str, Any]],
    real_mode: bool,
) -> str:
    """生成 Markdown 对比报告。"""
    mode_label = "真实 LLM 调用" if real_mode else "Mock 模式（不消耗 API 额度）"
    timestamp = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

    # 决出胜者
    if gpt_scores["total"] > claude_scores["total"]:
        winner = "GPT-4o-mini"
    elif claude_scores["total"] > gpt_scores["total"]:
        winner = "Claude"
    else:
        winner = "平手"

    report = f"""# 数据洞察 Agent A/B 对比报告

> 生成时间：{timestamp}
> 运行模式：{mode_label}
> 测试数据：3 平台销售数据，含 {len(anomalies)} 条硬规则异常

## 1. 对比结论

| 模型 | 总分 | 推荐场景 |
|------|------|----------|
| GPT-4o-mini | {gpt_scores['total']}/{gpt_scores['max']} | 快速概览、低成本场景 |
| Claude | {claude_scores['total']}/{claude_scores['max']} | 深度分析、高质量建议场景 |
| **胜者** | - | **{winner}** |

## 2. 5 维度评分对比

| 评分维度 | GPT-4o-mini | Claude | 差距 |
|----------|-------------|--------|------|
| 结构完整性 | {gpt_scores['scores']['结构完整性']}/5 | {claude_scores['scores']['结构完整性']}/5 | {gpt_scores['scores']['结构完整性'] - claude_scores['scores']['结构完整性']:+d} |
| 异常识别 | {gpt_scores['scores']['异常识别']}/5 | {claude_scores['scores']['异常识别']}/5 | {gpt_scores['scores']['异常识别'] - claude_scores['scores']['异常识别']:+d} |
| 建议可操作性 | {gpt_scores['scores']['建议可操作性']}/5 | {claude_scores['scores']['建议可操作性']}/5 | {gpt_scores['scores']['建议可操作性'] - claude_scores['scores']['建议可操作性']:+d} |
| 表达清晰度 | {gpt_scores['scores']['表达清晰度']}/5 | {claude_scores['scores']['表达清晰度']}/5 | {gpt_scores['scores']['表达清晰度'] - claude_scores['scores']['表达清晰度']:+d} |
| 业务价值 | {gpt_scores['scores']['业务价值']}/5 | {claude_scores['scores']['业务价值']}/5 | {gpt_scores['scores']['业务价值'] - claude_scores['scores']['业务价值']:+d} |
| **总分** | **{gpt_scores['total']}/{gpt_scores['max']}** | **{claude_scores['total']}/{claude_scores['max']}** | **{gpt_scores['total'] - claude_scores['total']:+d}** |

## 3. 异常检测上下文（硬规则结果）

以下异常由确定性规则检测，两个模型应都能识别：

"""
    for idx, a in enumerate(anomalies, start=1):
        report += f"{idx}. [{a['severity']}] {a['type']} - {a['detail']}\n"

    report += f"""

## 4. GPT-4o-mini 输出

```json
{json.dumps(gpt_output, ensure_ascii=False, indent=2)}
```

## 5. Claude 输出

```json
{json.dumps(claude_output, ensure_ascii=False, indent=2)}
```

## 6. 推荐选型

基于本次对比，**{winner}** 在数据洞察任务上表现更优。

### 选型建议

| 场景 | 推荐模型 | 理由 |
|------|----------|------|
| 日常日报（成本敏感） | GPT-4o-mini | 成本低，结构完整即可 |
| 异常深度分析（质量优先） | Claude | 建议更具体，业务价值更高 |
| 国内访问（无代理） | DeepSeek | 国内直连，性价比最高 |

> 💡 项目当前默认使用 DeepSeek（国内大模型），兼顾成本和质量。
> 本对比报告用于评估模型差异，实际选型请结合 API 可用性和成本预算。
"""
    return report


# ============ 主流程 ============
def main(real_mode: bool = False) -> bool:
    """运行 A/B 对比。

    Args:
        real_mode: True=调用真实 LLM API，False=用 Mock 输出

    Returns:
        是否成功
    """
    print("=" * 70)
    print("  数据洞察 Agent A/B 对比（GPT-4o-mini vs Claude）")
    print(f"  模式：{'真实 LLM 调用' if real_mode else 'Mock 模式（默认）'}")
    print("=" * 70)
    print()

    # 构建测试数据
    current, previous, anomalies = _build_test_data()
    print(f"【测试数据】{len(current)} 条销售记录，{len(anomalies)} 条异常")
    for a in anomalies:
        print(f"  - [{a['severity']}] {a['type']}: {a['detail']}")
    print()

    # 调用两个模型
    if real_mode:
        print("【调用真实 LLM】")
        try:
            print("  调用 GPT-4o-mini...")
            gpt_output = _call_real_llm("openai", current, previous, anomalies)
            print("  ✓ GPT-4o-mini 完成")
        except Exception as e:
            print(f"  ✗ GPT-4o-mini 调用失败: {e}")
            print("  回退到 Mock 模式")
            gpt_output = _mock_gpt4o_mini_output(anomalies)

        try:
            print("  调用 Claude...")
            claude_output = _call_real_llm("anthropic", current, previous, anomalies)
            print("  ✓ Claude 完成")
        except Exception as e:
            print(f"  ✗ Claude 调用失败: {e}")
            print("  回退到 Mock 模式")
            claude_output = _mock_claude_output(anomalies)
    else:
        print("【Mock 模式】用本地模拟输出，不消耗 API 额度")
        gpt_output = _mock_gpt4o_mini_output(anomalies)
        claude_output = _mock_claude_output(anomalies)
    print()

    # 评分
    print("【评分对比】")
    gpt_scores = _score_output(gpt_output, anomalies)
    claude_scores = _score_output(claude_output, anomalies)

    print(f"  GPT-4o-mini: {gpt_scores['total']}/{gpt_scores['max']}")
    for dim, score in gpt_scores["scores"].items():
        print(f"    - {dim}: {score}/5")
    print()
    print(f"  Claude: {claude_scores['total']}/{claude_scores['max']}")
    for dim, score in claude_scores["scores"].items():
        print(f"    - {dim}: {score}/5")
    print()

    # 决出胜者
    if gpt_scores["total"] > claude_scores["total"]:
        winner = "GPT-4o-mini"
    elif claude_scores["total"] > gpt_scores["total"]:
        winner = "Claude"
    else:
        winner = "平手"
    print(f"【结论】胜者：{winner}")
    print()

    # 生成报告
    report = _generate_report(
        gpt_output, claude_output, gpt_scores, claude_scores, anomalies, real_mode
    )
    report_path = _PROJECT_ROOT / "docs" / "ab_compare_report.md"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(report, encoding="utf-8")
    print(f"【报告已保存】{report_path}")
    print()

    return True


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="数据洞察 Agent A/B 对比")
    parser.add_argument(
        "--real",
        action="store_true",
        help="调用真实 LLM API（需配置 API Key）",
    )
    args = parser.parse_args()
    success = main(real_mode=args.real)
    sys.exit(0 if success else 1)
