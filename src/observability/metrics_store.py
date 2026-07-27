"""SQLite 持久化：存储 LLM 调用日志，支持统计查询。

设计思想：
- 轻量级 SQLite，无需额外数据库服务
- 自动建表、自动创建索引
- 写入采用上下文管理器，避免连接泄漏
- 查询接口面向业务：成功率、平均耗时、总成本、失败率

数据库位置：
- 开发模式：项目根目录 data/llm_metrics.db
- 打包模式：exe 同目录 data/llm_metrics.db

表结构：
    llm_call_logs
    ├── call_id         TEXT PRIMARY KEY  (LangChain run_id)
    ├── model_name      TEXT              (模型名)
    ├── input_summary   TEXT              (输入摘要，截断)
    ├── output_summary  TEXT              (输出摘要，截断)
    ├── duration_ms     INTEGER           (耗时毫秒)
    ├── input_tokens    INTEGER           (输入 token 数)
    ├── output_tokens   INTEGER           (输出 token 数)
    ├── cost_usd        REAL              (成本美元)
    ├── success         INTEGER           (1 成功 / 0 失败)
    ├── error_message   TEXT              (失败时的错误信息)
    └── created_at      TEXT              (ISO 时间戳)
"""

from __future__ import annotations

import sqlite3
import sys
from contextlib import contextmanager
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from src.observability.logger import get_logger

logger = get_logger()


def _resolve_db_path() -> Path:
    """获取 SQLite 数据库文件路径。

    打包模式（PyInstaller frozen）：exe 同目录的 data 子目录
    开发模式：项目根目录的 data 子目录
    """
    if getattr(sys, "frozen", False):
        base = Path(sys.executable).resolve().parent
    else:
        base = Path.cwd()
    data_dir = base / "data"
    data_dir.mkdir(exist_ok=True)
    return data_dir / "llm_metrics.db"


class MetricsStore:
    """LLM 调用日志的 SQLite 存储与查询。"""

    def __init__(self, db_path: Path | None = None) -> None:
        self._db_path = db_path or _resolve_db_path()
        self._init_db()
        logger.info(f"指标数据库初始化完成：{self._db_path}")

    @contextmanager
    def _get_conn(self):
        """获取数据库连接（上下文管理器，自动关闭）。"""
        conn = sqlite3.connect(self._db_path)
        conn.row_factory = sqlite3.Row
        try:
            yield conn
            conn.commit()
        except Exception:
            conn.rollback()
            raise
        finally:
            conn.close()

    def _init_db(self) -> None:
        """初始化数据库表和索引。"""
        with self._get_conn() as conn:
            conn.execute("""
                CREATE TABLE IF NOT EXISTS llm_call_logs (
                    call_id TEXT PRIMARY KEY,
                    model_name TEXT NOT NULL,
                    input_summary TEXT,
                    output_summary TEXT,
                    duration_ms INTEGER NOT NULL,
                    input_tokens INTEGER DEFAULT 0,
                    output_tokens INTEGER DEFAULT 0,
                    cost_usd REAL DEFAULT 0.0,
                    success INTEGER NOT NULL,
                    error_message TEXT,
                    created_at TEXT NOT NULL
                )
            """)
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_created_at ON llm_call_logs(created_at)"
            )
            conn.execute(
                "CREATE INDEX IF NOT EXISTS idx_success ON llm_call_logs(success)"
            )

    def record_call(
        self,
        call_id: str,
        model_name: str,
        input_summary: str,
        output_summary: str,
        duration_ms: int,
        input_tokens: int,
        output_tokens: int,
        cost_usd: float,
        success: bool,
        error_message: str,
    ) -> None:
        """写入一条 LLM 调用记录。

        Args:
            call_id: 调用唯一 ID（LangChain run_id）
            model_name: 模型名称
            input_summary: 输入摘要
            output_summary: 输出摘要
            duration_ms: 耗时（毫秒）
            input_tokens: 输入 token 数
            output_tokens: 输出 token 数
            cost_usd: 成本（美元）
            success: 是否成功
            error_message: 失败时的错误信息
        """
        with self._get_conn() as conn:
            conn.execute(
                """
                INSERT OR REPLACE INTO llm_call_logs
                (call_id, model_name, input_summary, output_summary,
                 duration_ms, input_tokens, output_tokens, cost_usd,
                 success, error_message, created_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    call_id,
                    model_name,
                    input_summary,
                    output_summary,
                    duration_ms,
                    input_tokens,
                    output_tokens,
                    cost_usd,
                    1 if success else 0,
                    error_message,
                    datetime.now().isoformat(),
                ),
            )

    def get_stats(self, hours: int = 1) -> dict[str, Any]:
        """查询近 N 小时的调用统计。

        Args:
            hours: 统计时间窗口（小时）

        Returns:
            统计字典：
            - total: 总调用数
            - success: 成功数
            - failed: 失败数
            - failure_rate: 失败率（0.0-1.0）
            - avg_duration_ms: 平均耗时
            - total_cost_usd: 总成本
            - total_input_tokens: 总输入 token
            - total_output_tokens: 总输出 token
        """
        cutoff = (datetime.now() - timedelta(hours=hours)).isoformat()
        with self._get_conn() as conn:
            row = conn.execute(
                """
                SELECT
                    COUNT(*) as total,
                    SUM(success) as success,
                    SUM(1 - success) as failed,
                    AVG(duration_ms) as avg_duration_ms,
                    SUM(cost_usd) as total_cost_usd,
                    SUM(input_tokens) as total_input_tokens,
                    SUM(output_tokens) as total_output_tokens
                FROM llm_call_logs
                WHERE created_at >= ?
                """,
                (cutoff,),
            ).fetchone()

        total = row["total"] or 0
        success = row["success"] or 0
        failed = row["failed"] or 0

        return {
            "hours": hours,
            "total": total,
            "success": success,
            "failed": failed,
            "failure_rate": (failed / total) if total > 0 else 0.0,
            "avg_duration_ms": round(row["avg_duration_ms"], 2) if row["avg_duration_ms"] else 0.0,
            "total_cost_usd": round(row["total_cost_usd"], 6) if row["total_cost_usd"] else 0.0,
            "total_input_tokens": row["total_input_tokens"] or 0,
            "total_output_tokens": row["total_output_tokens"] or 0,
        }

    def get_recent_calls(self, limit: int = 20) -> list[dict[str, Any]]:
        """查询最近的调用记录。

        Args:
            limit: 返回记录数

        Returns:
            调用记录列表（按时间倒序）
        """
        with self._get_conn() as conn:
            rows = conn.execute(
                """
                SELECT call_id, model_name, duration_ms, input_tokens,
                       output_tokens, cost_usd, success, error_message, created_at
                FROM llm_call_logs
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (limit,),
            ).fetchall()

        return [
            {
                "call_id": r["call_id"],
                "model_name": r["model_name"],
                "duration_ms": r["duration_ms"],
                "input_tokens": r["input_tokens"],
                "output_tokens": r["output_tokens"],
                "cost_usd": r["cost_usd"],
                "success": bool(r["success"]),
                "error_message": r["error_message"],
                "created_at": r["created_at"],
            }
            for r in rows
        ]

    def cleanup(self, days: int = 30) -> int:
        """清理超过指定天数的旧记录。

        Args:
            days: 保留天数

        Returns:
            删除的记录数
        """
        cutoff = (datetime.now() - timedelta(days=days)).isoformat()
        with self._get_conn() as conn:
            cursor = conn.execute(
                "DELETE FROM llm_call_logs WHERE created_at < ?",
                (cutoff,),
            )
            deleted = cursor.rowcount
        if deleted > 0:
            logger.info(f"清理 {deleted} 条过期 LLM 调用记录（>{days}天）")
        return deleted


# 模块级单例
metrics_store = MetricsStore()
