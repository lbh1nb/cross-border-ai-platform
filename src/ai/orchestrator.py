"""Agent 编排引擎：基于状态机管理双 Agent 联动工作流。

设计思想（v0.7.0 新增）：
- 不用 LangGraph 的 StateGraph，用纯 Python 状态机更直观可控
- 5 个核心状态 + 2 个联动场景
- 状态持久化到内存（运行时），跨会话不持久化（避免过度设计）
- 失败可重试，支持断点续跑

状态机：
    IDLE → SELECTING → SELECTED → LISTING_OPTIMIZING → COMPLETED
                                                    ↓
                                                  FAILED ← 任意阶段失败

联动场景：
    场景①：选品 Agent 输出 → 写入 Listing 库 → Listing Agent 优化
    场景②：数据洞察发现爆款 → 触发选品 Agent 复盘

使用方式：
    from src.ai.orchestrator import Orchestrator, run_selection_to_listing

    # 场景①：选品 → Listing 联动
    result = run_selection_to_listing(category="家居收纳")

    # 场景②：洞察发现爆款 → 选品复盘
    result = run_insight_to_selection_review(top_priority="...", action_items=[...])
"""

from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Callable

from src.observability.logger import get_logger

logger = get_logger()


# ============================================================
# 状态机定义
# ============================================================
class OrchestratorState(str, Enum):
    """编排引擎状态枚举。"""

    IDLE = "idle"                            # 空闲，等待启动
    SELECTING = "selecting"                  # 选品 Agent 执行中
    SELECTED = "selecting_done"              # 选品完成，准备触发 Listing
    LISTING_OPTIMIZING = "listing_optimizing"  # Listing Agent 执行中
    COMPLETED = "completed"                  # 全部完成
    FAILED = "failed"                        # 失败


# 联动场景标识
class OrchestrationScenario(str, Enum):
    """联动场景枚举。"""

    SELECTION_TO_LISTING = "selection_to_listing"      # 场景①：选品 → Listing
    INSIGHT_TO_SELECTION = "insight_to_selection"      # 场景②：洞察 → 选品复盘


# 触发"选品复盘"的关键词（场景②判断依据）
_REVIEW_TRIGGER_KEYWORDS = ["复盘", "选品", "爆款", "上升", "增长"]


# ============================================================
# 状态机数据结构
# ============================================================
@dataclass
class OrchestratorContext:
    """编排引擎运行时上下文。

    存储联动过程中的中间状态和最终结果。
    """

    scenario: OrchestrationScenario
    state: OrchestratorState = OrchestratorState.IDLE
    started_at: str = field(
        default_factory=lambda: datetime.now().isoformat()
    )
    completed_at: str = ""
    error: str = ""

    # 场景①中间数据
    category: str = ""                           # 选品输入品类
    selection_result: dict[str, Any] = field(default_factory=dict)  # 选品 Agent 输出
    top_picks: list[dict[str, Any]] = field(default_factory=list)   # 推荐商品列表
    listing_records_created: int = 0             # 写入 Listing 库的记录数
    listing_result: dict[str, Any] = field(default_factory=dict)    # Listing Agent 输出

    # 场景②中间数据
    insight_top_priority: str = ""               # 洞察输出的最紧急事项
    insight_action_items: list[str] = field(default_factory=list)   # 洞察行动建议
    review_triggered: bool = False               # 是否触发了选品复盘
    review_category: str = ""                    # 复盘的品类


@dataclass
class OrchestrationResult:
    """编排引擎最终输出。"""

    success: bool
    scenario: str
    state: str
    duration_seconds: float = 0.0
    context: OrchestratorContext = field(default_factory=lambda: OrchestratorContext(OrchestrationScenario.SELECTION_TO_LISTING))
    summary: str = ""


# ============================================================
# 编排引擎核心
# ============================================================
class Orchestrator:
    """Agent 编排引擎：管理双 Agent 联动状态机。

    职责：
    1. 管理状态机转换（IDLE → SELECTING → SELECTED → LISTING_OPTIMIZING → COMPLETED）
    2. 串联选品 Agent 和 Listing Agent，传递中间状态
    3. 失败时记录错误，状态转为 FAILED
    4. 支持进度回调，便于 GUI 实时显示联动进度

    设计要点：
    - 不依赖 LangGraph，纯 Python 实现，便于测试和调试
    - Agent 调用通过依赖注入（默认导入 selection_agent / listing_agent）
    - 测试时可注入 Mock Agent 函数，避免真实 LLM 调用
    """

    def __init__(
        self,
        selection_runner: Callable[[str], dict[str, Any]] | None = None,
        listing_runner: Callable[[int], dict[str, Any]] | None = None,
        progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
    ) -> None:
        """初始化编排引擎。

        Args:
            selection_runner: 选品 Agent 运行函数，默认用 run_selection_agent
            listing_runner: Listing Agent 运行函数，默认用 run_listing_agent
            progress_callback: 进度回调函数（阶段名, 上下文快照）
        """
        # 延迟导入避免循环依赖
        if selection_runner is None:
            from src.ai.agents.selection_agent import run_selection_agent
            selection_runner = run_selection_agent
        if listing_runner is None:
            from src.ai.agents.listing_agent import run_listing_agent
            listing_runner = run_listing_agent

        self._selection_runner = selection_runner
        self._listing_runner = listing_runner
        self._progress_callback = progress_callback

    # ------------------------------------------------------------
    # 场景①：选品 → Listing 联动
    # ------------------------------------------------------------
    def run_selection_to_listing(self, category: str) -> OrchestrationResult:
        """执行场景①：选品 Agent 输出 → 自动创建 Listing 优化任务。

        流程：
        1. 启动选品 Agent（state=SELECTING）
        2. 选品完成，从 agent_output 提取 top_picks（state=SELECTED）
        3. 把 top_picks 写入 Listing 库（state 仍=SELECTED）
        4. 启动 Listing Agent 优化（state=LISTING_OPTIMIZING）
        5. 完成（state=COMPLETED）

        Args:
            category: 选品品类名

        Returns:
            OrchestrationResult 包含联动全流程结果
        """
        ctx = OrchestratorContext(
            scenario=OrchestrationScenario.SELECTION_TO_LISTING,
            category=category,
        )
        start_time = datetime.now()
        logger.info(
            f"[Orchestrator] 启动场景①：选品→Listing，品类={category}"
        )

        try:
            # 阶段 1：选品 Agent
            ctx.state = OrchestratorState.SELECTING
            self._emit_progress("选品 Agent 启动", ctx)

            selection_result = self._selection_runner(category)
            ctx.selection_result = selection_result

            if not selection_result.get("success", False):
                raise RuntimeError(
                    f"选品 Agent 失败: {selection_result.get('error', '未知错误')}"
                )

            # 从选品结果提取 top_picks
            top_picks = self._extract_top_picks(selection_result)
            ctx.top_picks = top_picks
            logger.info(
                f"[Orchestrator] 选品完成，获得 {len(top_picks)} 个推荐商品"
            )

            if not top_picks:
                raise RuntimeError("选品 Agent 未返回任何推荐商品")

            # 阶段 2：写入 Listing 库
            ctx.state = OrchestratorState.SELECTED
            self._emit_progress(
                f"选品完成，{len(top_picks)} 个商品待写入 Listing 库", ctx
            )

            created_count = self._write_picks_to_listing(top_picks, category)
            ctx.listing_records_created = created_count
            logger.info(
                f"[Orchestrator] 已写入 {created_count} 条记录到 Listing 库"
            )

            # 阶段 3：Listing Agent 优化
            ctx.state = OrchestratorState.LISTING_OPTIMIZING
            self._emit_progress("Listing Agent 启动", ctx)

            listing_result = self._listing_runner(limit=created_count)
            ctx.listing_result = listing_result

            if not listing_result.get("success", False):
                logger.warning(
                    f"[Orchestrator] Listing Agent 失败但不阻塞: "
                    f"{listing_result.get('error')}"
                )
                # Listing 失败不阻塞整体流程，因为选品已完成
                ctx.error = f"Listing Agent 警告: {listing_result.get('error', '')}"

            # 阶段 4：完成
            ctx.state = OrchestratorState.COMPLETED
            ctx.completed_at = datetime.now().isoformat()
            duration = (datetime.now() - start_time).total_seconds()

            summary = (
                f"场景①完成：选品 {len(top_picks)} 个商品，"
                f"写入 Listing 库 {created_count} 条，"
                f"Listing Agent {'成功' if listing_result.get('success') else '部分失败'}，"
                f"耗时 {duration:.1f}s"
            )
            logger.info(f"[Orchestrator] {summary}")

            return OrchestrationResult(
                success=True,
                scenario=ctx.scenario.value,
                state=ctx.state.value,
                duration_seconds=duration,
                context=ctx,
                summary=summary,
            )

        except Exception as e:
            ctx.state = OrchestratorState.FAILED
            ctx.error = str(e)
            ctx.completed_at = datetime.now().isoformat()
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(
                f"[Orchestrator] 场景①失败: {e}", exc_info=True
            )
            return OrchestrationResult(
                success=False,
                scenario=ctx.scenario.value,
                state=ctx.state.value,
                duration_seconds=duration,
                context=ctx,
                summary=f"场景①失败: {e}",
            )

    # ------------------------------------------------------------
    # 场景②：洞察发现爆款 → 触发选品复盘
    # ------------------------------------------------------------
    def run_insight_to_selection_review(
        self,
        top_priority: str,
        action_items: list[str],
        category_hint: str = "",
    ) -> OrchestrationResult:
        """执行场景②：数据洞察发现爆款 → 触发选品 Agent 复盘。

        判断逻辑：
        - 检查 top_priority 和 action_items 是否包含复盘触发关键词
        - 命中关键词则触发选品 Agent 重跑对应品类
        - 未命中则返回"无需复盘"

        Args:
            top_priority: 数据洞察 Agent 输出的 top_priority 字段
            action_items: 数据洞察 Agent 输出的 action_items 列表
            category_hint: 可选品类提示（如洞察数据中识别出的品类）

        Returns:
            OrchestrationResult 包含复盘触发判断和（如触发）选品结果
        """
        ctx = OrchestratorContext(
            scenario=OrchestrationScenario.INSIGHT_TO_SELECTION,
            insight_top_priority=top_priority,
            insight_action_items=action_items,
            review_category=category_hint or "家居收纳",  # 默认品类
        )
        start_time = datetime.now()
        logger.info(
            f"[Orchestrator] 启动场景②：洞察→选品复盘，"
            f"top_priority={top_priority[:50]}..."
        )

        try:
            # 阶段 1：判断是否需要复盘
            should_review = self._should_trigger_review(
                top_priority, action_items
            )
            ctx.review_triggered = should_review

            if not should_review:
                ctx.state = OrchestratorState.COMPLETED
                ctx.completed_at = datetime.now().isoformat()
                duration = (datetime.now() - start_time).total_seconds()
                summary = (
                    f"场景②完成：洞察未触发复盘条件，"
                    f"top_priority 和 action_items 未包含复盘关键词，"
                    f"耗时 {duration:.1f}s"
                )
                logger.info(f"[Orchestrator] {summary}")
                return OrchestrationResult(
                    success=True,
                    scenario=ctx.scenario.value,
                    state=ctx.state.value,
                    duration_seconds=duration,
                    context=ctx,
                    summary=summary,
                )

            # 阶段 2：触发选品复盘
            ctx.state = OrchestratorState.SELECTING
            self._emit_progress(
                f"触发选品复盘，品类={ctx.review_category}", ctx
            )

            logger.info(
                f"[Orchestrator] 命中复盘关键词，"
                f"触发选品 Agent 重跑品类={ctx.review_category}"
            )
            selection_result = self._selection_runner(ctx.review_category)
            ctx.selection_result = selection_result

            if not selection_result.get("success", False):
                raise RuntimeError(
                    f"复盘选品 Agent 失败: {selection_result.get('error')}"
                )

            # 阶段 3：完成
            ctx.state = OrchestratorState.COMPLETED
            ctx.completed_at = datetime.now().isoformat()
            duration = (datetime.now() - start_time).total_seconds()

            top_picks = self._extract_top_picks(selection_result)
            ctx.top_picks = top_picks
            summary = (
                f"场景②完成：洞察触发复盘，"
                f"重跑品类「{ctx.review_category}」获得 {len(top_picks)} 个推荐，"
                f"耗时 {duration:.1f}s"
            )
            logger.info(f"[Orchestrator] {summary}")

            return OrchestrationResult(
                success=True,
                scenario=ctx.scenario.value,
                state=ctx.state.value,
                duration_seconds=duration,
                context=ctx,
                summary=summary,
            )

        except Exception as e:
            ctx.state = OrchestratorState.FAILED
            ctx.error = str(e)
            ctx.completed_at = datetime.now().isoformat()
            duration = (datetime.now() - start_time).total_seconds()
            logger.error(
                f"[Orchestrator] 场景②失败: {e}", exc_info=True
            )
            return OrchestrationResult(
                success=False,
                scenario=ctx.scenario.value,
                state=ctx.state.value,
                duration_seconds=duration,
                context=ctx,
                summary=f"场景②失败: {e}",
            )

    # ------------------------------------------------------------
    # 私有辅助方法
    # ------------------------------------------------------------
    def _emit_progress(
        self, message: str, ctx: OrchestratorContext
    ) -> None:
        """通过回调通知进度。"""
        if self._progress_callback:
            try:
                self._progress_callback(
                    message,
                    {
                        "state": ctx.state.value,
                        "scenario": ctx.scenario.value,
                        "category": ctx.category,
                    },
                )
            except Exception as e:
                logger.warning(f"进度回调失败: {e}")

    @staticmethod
    def _extract_top_picks(
        selection_result: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """从选品 Agent 结果中提取 top_picks。

        选品 Agent 的 agent_output 是 LLM 文本，可能包含 JSON。
        尝试解析 JSON 提取 top_picks，失败则返回空列表。
        """
        agent_output = selection_result.get("agent_output", "")
        if not agent_output:
            return []

        # 尝试从输出中提取 JSON
        text = agent_output if isinstance(agent_output, str) else str(agent_output)

        # 优先找 ```json ``` 块
        json_str: str | None = None
        if "```json" in text:
            start = text.find("```json") + len("```json")
            end = text.find("```", start)
            if end > start:
                json_str = text[start:end].strip()
        elif "{" in text and "top_picks" in text:
            # 直接找包含 top_picks 的 JSON 块
            start = text.find("{")
            end = text.rfind("}")
            if end > start:
                json_str = text[start : end + 1]

        if not json_str:
            logger.warning(
                "[Orchestrator] 选品 Agent 输出未包含可解析的 JSON，"
                "top_picks 提取失败"
            )
            return []

        try:
            data = json.loads(json_str)
            top_picks = data.get("top_picks", [])
            if isinstance(top_picks, list):
                return top_picks
        except json.JSONDecodeError as e:
            logger.warning(
                f"[Orchestrator] 选品 Agent 输出 JSON 解析失败: {e}"
            )

        return []

    @staticmethod
    def _write_picks_to_listing(
        top_picks: list[dict[str, Any]],
        category: str,
    ) -> int:
        """把选品 top_picks 写入 Listing 库（增量同步）。

        Args:
            top_picks: 选品 Agent 推荐的商品列表
            category: 品类名（仅用于日志）

        Returns:
            成功写入的记录数
        """
        from src.feishu.field_mapping import (
            LISTING_FIELDS,
            picks_to_listing_records,
        )
        from src.feishu.sync_service import create_listing_sync_service

        records = picks_to_listing_records(top_picks)
        if not records:
            logger.warning(
                f"[Orchestrator] 品类={category} 无可写入 Listing 库的记录"
            )
            return 0

        service = create_listing_sync_service()
        result = service.sync_records(
            records, primary_keys=[LISTING_FIELDS["asin"]]
        )

        logger.info(
            f"[Orchestrator] Listing 库同步: 新增 {result.new_count} / "
            f"更新 {result.update_count} / 跳过 {result.skip_count} / "
            f"失败 {result.fail_count}"
        )
        return result.new_count + result.update_count

    @staticmethod
    def _should_trigger_review(
        top_priority: str, action_items: list[str]
    ) -> bool:
        """判断洞察结果是否需要触发选品复盘。

        判断规则：
        - top_priority 包含复盘触发关键词 → 触发
        - 任一 action_item 包含复盘触发关键词 → 触发
        - 否则不触发

        Args:
            top_priority: 洞察输出的 top_priority
            action_items: 洞察输出的 action_items

        Returns:
            True 表示需要触发复盘
        """
        check_text = top_priority or ""
        for item in action_items or []:
            check_text += " " + (item or "")

        check_text_lower = check_text.lower()
        for keyword in _REVIEW_TRIGGER_KEYWORDS:
            if keyword in check_text_lower:
                return True
        return False


# ============================================================
# 便捷入口函数
# ============================================================
def run_selection_to_listing(
    category: str,
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> OrchestrationResult:
    """场景①入口：选品 → Listing 联动。

    Args:
        category: 选品品类
        progress_callback: 可选进度回调

    Returns:
        OrchestrationResult
    """
    orchestrator = Orchestrator(progress_callback=progress_callback)
    return orchestrator.run_selection_to_listing(category)


def run_insight_to_selection_review(
    top_priority: str,
    action_items: list[str],
    category_hint: str = "",
    progress_callback: Callable[[str, dict[str, Any]], None] | None = None,
) -> OrchestrationResult:
    """场景②入口：洞察 → 选品复盘。

    Args:
        top_priority: 洞察输出的 top_priority
        action_items: 洞察输出的 action_items
        category_hint: 可选品类提示
        progress_callback: 可选进度回调

    Returns:
        OrchestrationResult
    """
    orchestrator = Orchestrator(progress_callback=progress_callback)
    return orchestrator.run_insight_to_selection_review(
        top_priority=top_priority,
        action_items=action_items,
        category_hint=category_hint,
    )


def should_trigger_review_from_insight(
    top_priority: str, action_items: list[str]
) -> bool:
    """便捷查询：洞察结果是否应触发选品复盘。

    供数据洞察 Agent 完成后调用，判断是否需要联动选品 Agent。
    """
    return Orchestrator._should_trigger_review(top_priority, action_items)
