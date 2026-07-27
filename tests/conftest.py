"""pytest 全局配置：为所有测试隔离 .env 中的 AI 字段。

autouse=True 让所有测试自动应用，无需手动 import。
避免本地 .env 配置了 OPENAI_API_BASE 后干扰 ModelRouter 的单元测试。
"""

from __future__ import annotations

import pytest


@pytest.fixture(autouse=True)
def _isolate_ai_settings(monkeypatch: pytest.MonkeyPatch) -> None:
    """每个测试运行前重置 AI 相关配置，确保测试隔离。"""
    from src.config import settings

    # 仅当测试未显式设置时才使用默认空值
    # 注意：monkeypatch.setattr 会在测试结束后自动恢复原值
    monkeypatch.setattr(settings, "openai_api_base", "")
    monkeypatch.setattr(settings, "openai_api_key", "")
    monkeypatch.setattr(settings, "anthropic_api_key", "")
