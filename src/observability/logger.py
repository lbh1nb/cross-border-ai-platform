"""统一日志模块：基于 loguru，按天切割，ERROR 级别预留告警接口。"""

from __future__ import annotations

import sys
from pathlib import Path

from loguru import logger

from src.config import settings

# 标记是否已初始化，避免重复配置
_initialized = False


def setup_logger() -> None:
    """初始化全局日志配置。项目入口处调用一次即可。"""
    global _initialized
    if _initialized:
        return

    # 清除默认 handler
    logger.remove()

    # 控制台输出：仅在有终端时启用（pythonw.exe 无终端，跳过）
    if sys.stderr is not None and sys.stderr.writable():
        logger.add(
            sys.stderr,
            level=settings.log_level,
            format=(
                "<green>{time:YYYY-MM-DD HH:mm:ss}</green> | "
                "<level>{level: <8}</level> | "
                "<cyan>{name}</cyan>:<cyan>{function}</cyan>:<cyan>{line}</cyan> - "
                "<level>{message}</level>"
            ),
        )

    # 文件输出：按天切割，保留 30 天，自动压缩
    log_dir = Path("logs")
    log_dir.mkdir(exist_ok=True)
    logger.add(
        log_dir / "app_{time:YYYY-MM-DD}.log",
        level=settings.log_level,
        rotation="00:00",       # 每天 0 点切割
        retention="30 days",    # 保留 30 天
        compression="zip",      # 自动压缩
        encoding="utf-8",
        format=(
            "{time:YYYY-MM-DD HH:mm:ss} | {level: <8} | "
            "{name}:{function}:{line} - {message}"
        ),
    )

    _initialized = True


def get_logger():
    """获取 logger 实例。"""
    if not _initialized:
        setup_logger()
    return logger
