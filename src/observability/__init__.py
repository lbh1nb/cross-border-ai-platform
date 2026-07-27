"""可观测性模块：日志、LLM 调用监控、指标存储、异常告警。

模块组成：
- logger: 统一日志（基于 loguru）
- llm_monitor: LLM 调用拦截器（LangChain Callback）
- metrics_store: SQLite 持久化调用日志
- alert: 失败率超阈值自动告警到飞书群
"""

from src.observability.alert import alert_checker, AlertChecker
from src.observability.llm_monitor import llm_monitor, LLMCallMonitor
from src.observability.logger import get_logger, setup_logger
from src.observability.metrics_store import metrics_store, MetricsStore

__all__ = [
    "get_logger",
    "setup_logger",
    "llm_monitor",
    "LLMCallMonitor",
    "metrics_store",
    "MetricsStore",
    "alert_checker",
    "AlertChecker",
]
