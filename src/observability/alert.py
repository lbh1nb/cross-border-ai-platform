"""异常告警闭环：LLM 调用失败率超阈值时自动告警到飞书群。

设计思想：
- 每次 LLM 调用失败后触发检查（由 llm_monitor 调用）
- 触发条件：近 1 小时调用数 >= 10 且失败率 > 10%
- 防重复：同一告警 30 分钟内只发送一次
- 告警通道：优先应用机器人（application_bot），失败回退到 Webhook 机器人

告警流程：
    LLM 调用失败（on_llm_error 触发）
        ↓
    alert_checker.check_and_alert()
        ↓
    查询近 1 小时统计
        ↓
    失败率 > 10% 且总数 >= 10？
        ↓ 是
    距上次告警超过 30 分钟？
        ↓ 是
    发送飞书告警消息 → 记录告警时间
"""

from __future__ import annotations

import time
from datetime import datetime
from typing import Any

from src.observability.logger import get_logger
from src.observability.metrics_store import metrics_store

logger = get_logger()


# 告警阈值
_ALERT_WINDOW_HOURS = 1          # 统计窗口：1 小时
_ALERT_MIN_TOTAL = 10            # 最少调用数（避免少量调用误报）
_ALERT_FAILURE_RATE_THRESHOLD = 0.10  # 失败率阈值：10%
_ALERT_COOLDOWN_SECONDS = 30 * 60  # 告警冷却：30 分钟


class AlertChecker:
    """LLM 调用异常告警检查器。"""

    def __init__(self) -> None:
        # 上次告警时间戳（用于冷却判断）
        self._last_alert_at: float = 0.0

    def check_and_alert(self) -> bool:
        """检查是否需要告警，如需要则发送。

        触发条件（全部满足）：
        1. 近 1 小时调用数 >= 10
        2. 失败率 > 10%
        3. 距上次告警超过 30 分钟

        Returns:
            是否发送了告警
        """
        # 冷却判断
        now = time.time()
        if now - self._last_alert_at < _ALERT_COOLDOWN_SECONDS:
            return False

        # 查询统计
        try:
            stats = metrics_store.get_stats(hours=_ALERT_WINDOW_HOURS)
        except Exception as e:
            logger.warning(f"告警检查失败：无法查询统计: {e}")
            return False

        total = stats["total"]
        failure_rate = stats["failure_rate"]

        # 未达阈值
        if total < _ALERT_MIN_TOTAL:
            return False
        if failure_rate <= _ALERT_FAILURE_RATE_THRESHOLD:
            return False

        # 触发告警
        self._send_alert(stats)
        self._last_alert_at = now
        return True

    def _send_alert(self, stats: dict[str, Any]) -> None:
        """发送告警消息到飞书群。

        优先用应用机器人，失败回退到 Webhook 机器人。

        Args:
            stats: get_stats() 返回的统计字典
        """
        alert_text = self._format_alert_text(stats)

        # 通道 1：应用机器人
        try:
            from src.feishu.application_bot import application_bot
            if application_bot.send_text(alert_text):
                logger.warning(f"已通过应用机器人发送 LLM 告警：失败率={stats['failure_rate']:.1%}")
                return
        except Exception as e:
            logger.warning(f"应用机器人发送告警失败: {e}")

        # 通道 2：Webhook 机器人
        try:
            from src.feishu.feishu_bot import feishu_bot
            if feishu_bot.send_text(alert_text):
                logger.warning(f"已通过 Webhook 机器人发送 LLM 告警：失败率={stats['failure_rate']:.1%}")
                return
        except Exception as e:
            logger.warning(f"Webhook 机器人发送告警失败: {e}")

        # 两个通道都失败
        logger.error(
            f"LLM 告警发送失败（所有通道均不可用）：失败率={stats['failure_rate']:.1%}"
        )

    def _format_alert_text(self, stats: dict[str, Any]) -> str:
        """格式化告警消息文本。"""
        now_str = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        return (
            f"⚠️ [LLM 调用异常告警]\n\n"
            f"时间：{now_str}\n"
            f"统计窗口：近 {stats['hours']} 小时\n"
            f"总调用数：{stats['total']}\n"
            f"成功：{stats['success']}，失败：{stats['failed']}\n"
            f"失败率：{stats['failure_rate']:.1%}（阈值 10%）\n"
            f"平均耗时：{stats['avg_duration_ms']:.0f} ms\n"
            f"总成本：${stats['total_cost_usd']:.4f}\n\n"
            f"请检查 API Key 有效性、网络连通性或模型服务状态。"
        )


# 模块级单例
alert_checker = AlertChecker()
