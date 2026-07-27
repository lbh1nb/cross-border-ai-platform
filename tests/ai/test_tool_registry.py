"""ToolRegistry 单元测试：测试工具注册与获取。

覆盖场景：
1. 注册工具后可按名称获取
2. 获取未注册工具抛 KeyError
3. 批量获取工具
4. 工具描述自动生成
5. 列出所有工具名称
"""

from __future__ import annotations

import pytest

from src.ai.tool_registry import ToolRegistry, reset_tool_registry


def _sample_func(x: int) -> int:
    """测试用的工具函数。"""
    return x * 2


class TestToolRegistry:
    """ToolRegistry 核心功能测试。"""

    def test_register_and_get_tool(self) -> None:
        """注册后能按名称获取工具。"""
        registry = ToolRegistry()
        registry.register("double", "将数字翻倍", _sample_func)

        tool = registry.get_tool("double")
        assert tool.name == "double"
        assert tool.description == "将数字翻倍"

    def test_get_unregistered_tool_raises_keyerror(self) -> None:
        """获取未注册的工具抛 KeyError。"""
        registry = ToolRegistry()

        with pytest.raises(KeyError, match="未注册"):
            registry.get_tool("nonexistent")

    def test_get_tools_batch(self) -> None:
        """批量获取工具列表。"""
        registry = ToolRegistry()
        registry.register("tool_a", "工具 A", _sample_func)
        registry.register("tool_b", "工具 B", _sample_func)

        tools = registry.get_tools(["tool_a", "tool_b"])
        assert len(tools) == 2
        assert tools[0].name == "tool_a"
        assert tools[1].name == "tool_b"

    def test_list_tool_names(self) -> None:
        """列出所有已注册工具名称。"""
        registry = ToolRegistry()
        registry.register("tool_a", "工具 A", _sample_func)
        registry.register("tool_b", "工具 B", _sample_func)

        names = registry.list_tool_names()
        assert set(names) == {"tool_a", "tool_b"}

    def test_get_tool_descriptions(self) -> None:
        """工具描述文本自动生成。"""
        registry = ToolRegistry()
        registry.register("tool_a", "工具 A 描述", _sample_func)
        registry.register("tool_b", "工具 B 描述", _sample_func)

        descriptions = registry.get_tool_descriptions()
        assert "- tool_a: 工具 A 描述" in descriptions
        assert "- tool_b: 工具 B 描述" in descriptions

    def test_empty_registry_descriptions(self) -> None:
        """空注册中心的描述应为空字符串。"""
        registry = ToolRegistry()
        assert registry.get_tool_descriptions() == ""

    def test_overwrite_existing_tool(self) -> None:
        """重复注册同名工具会覆盖旧工具。"""
        registry = ToolRegistry()
        registry.register("tool", "旧描述", _sample_func)
        registry.register("tool", "新描述", _sample_func)

        tool = registry.get_tool("tool")
        assert tool.description == "新描述"


class TestToolRegistryWithSchema:
    """测试带参数 schema 的工具注册。"""

    def test_register_with_pydantic_schema(self) -> None:
        """使用 Pydantic 模型作为参数 schema 注册工具。"""
        from pydantic import BaseModel, Field

        class MyArgs(BaseModel):
            value: int = Field(description="输入值")

        registry = ToolRegistry()
        registry.register(
            "schema_tool", "带 schema 的工具", _sample_func, args_schema=MyArgs
        )

        tool = registry.get_tool("schema_tool")
        assert tool.name == "schema_tool"


class TestSingleton:
    """测试单例管理。"""

    def test_reset_tool_registry(self) -> None:
        """reset_tool_registry 后单例应被重置。"""
        reset_tool_registry()
        from src.ai.tool_registry import _registry

        assert _registry is None
