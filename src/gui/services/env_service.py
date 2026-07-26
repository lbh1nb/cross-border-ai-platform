"""配置读写服务。

封装 .env 文件的读写操作，让 GUI 不直接接触文件 IO。
业务用户在 GUI 表单里填配置，点"保存"后由本服务写入 .env。

设计要点：
- 读：解析 .env 文件成 dict，供 GUI 表单回填
- 写：把 GUI 表单的值写回 .env，保留注释和分组
- 不暴露文件路径给上层
"""

from __future__ import annotations

import os
import sys
from pathlib import Path
from typing import Any

from src.observability.logger import get_logger

logger = get_logger()


def _resolve_env_path() -> Path:
    """获取 .env 文件路径。

    打包模式（PyInstaller frozen）：exe 同目录
    开发模式：项目根目录
    """
    if getattr(sys, "frozen", False):
        return Path(sys.executable).resolve().parent / ".env"
    return Path(__file__).resolve().parent.parent.parent.parent / ".env"


# .env 文件路径
_ENV_PATH = _resolve_env_path()


def read_env_config() -> dict[str, str]:
    """读取 .env 文件，返回配置字典。

    Returns:
        配置字典，key 是环境变量名，value 是字符串值
    """
    if not _ENV_PATH.exists():
        logger.warning(f".env 文件不存在: {_ENV_PATH}")
        return {}

    config: dict[str, str] = {}
    try:
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith("#"):
                    continue
                # 解析 KEY=VALUE
                if "=" in line:
                    key, _, value = line.partition("=")
                    config[key.strip()] = value.strip()
    except Exception as e:
        logger.error(f"读取 .env 失败: {e}", exc_info=True)
        return {}

    return config


def write_env_config(updates: dict[str, str]) -> bool:
    """更新 .env 文件中的配置项。

    只更新 updates 里提到的 key，其他 key 和注释保持不变。
    如果 key 不存在，追加到文件末尾。

    Args:
        updates: 要更新的配置字典

    Returns:
        True 表示成功，False 表示失败
    """
    if not _ENV_PATH.exists():
        logger.error(f".env 文件不存在: {_ENV_PATH}")
        return False

    try:
        # 读取所有行
        with open(_ENV_PATH, "r", encoding="utf-8") as f:
            lines = f.readlines()

        # 标记已处理的 key
        updated_keys: set[str] = set()
        new_lines: list[str] = []

        for line in lines:
            stripped = line.strip()
            # 跳过空行和注释直接保留
            if not stripped or stripped.startswith("#"):
                new_lines.append(line)
                continue

            if "=" in stripped:
                key, _, _ = stripped.partition("=")
                key = key.strip()
                if key in updates:
                    # 替换为新值
                    new_value = updates[key]
                    new_lines.append(f"{key}={new_value}\n")
                    updated_keys.add(key)
                else:
                    new_lines.append(line)
            else:
                new_lines.append(line)

        # 追加未找到的 key
        for key, value in updates.items():
            if key not in updated_keys:
                new_lines.append(f"\n# 自动追加\n{key}={value}\n")

        # 写回文件
        with open(_ENV_PATH, "w", encoding="utf-8") as f:
            f.writelines(new_lines)

        logger.info(f".env 配置已更新: {list(updates.keys())}")
        return True

    except Exception as e:
        logger.error(f"写入 .env 失败: {e}", exc_info=True)
        return False


def get_config_value(key: str, default: str = "") -> str:
    """获取单个配置值。

    Args:
        key: 环境变量名
        default: 默认值

    Returns:
        配置值字符串
    """
    return read_env_config().get(key, default)


def is_approval_configured() -> bool:
    """检查审批流是否已配置。

    Returns:
        True 表示 approval_code / approver_open_id / node_id 三项均已配置
    """
    config = read_env_config()
    return bool(
        config.get("FEISHU_APPROVAL_CODE")
        and config.get("FEISHU_APPROVAL_APPROVER_OPEN_ID")
        and config.get("FEISHU_APPROVAL_NODE_ID")
    )
