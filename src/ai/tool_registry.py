"""工具注册中心：Agent 通过名称调用工具。

设计思想：
- 工具是 Agent 的"手脚"，封装具体的业务操作
- 每个工具有 name、description、func，Agent 通过 LLM 决策调用哪个
- 工具可以是同步或异步函数，统一封装为 Tool 接口

使用方式：
    registry = get_tool_registry()
    registry.register("fetch_products", "抓取商品数据", fetch_func)
    tools = registry.get_tools(["fetch_products", "analyze_data"])
"""

from __future__ import annotations

from typing import Any, Callable

from langchain_core.tools import StructuredTool, Tool

from src.observability.logger import get_logger

logger = get_logger()


class ToolRegistry:
    """工具注册中心。

    管理所有 Agent 可用的工具，支持：
    - 按名称注册工具
    - 按名称列表批量获取工具
    - 工具描述自动生成（供 LLM 决策）
    """

    def __init__(self) -> None:
        self._tools: dict[str, Tool | StructuredTool] = {}
        logger.info("ToolRegistry 初始化完成")

    def register(
        self,
        name: str,
        description: str,
        func: Callable[..., Any],
        args_schema: type | None = None,
    ) -> None:
        """注册一个工具。

        Args:
            name: 工具名称（Agent 通过此名称调用）
            description: 工具描述（LLM 根据此描述决定是否调用）
            func: 工具函数
            args_schema: 参数 schema（Pydantic 模型，用于参数校验）
        """
        if args_schema:
            tool = StructuredTool.from_function(
                func=func,
                name=name,
                description=description,
                args_schema=args_schema,
            )
        else:
            tool = Tool(
                name=name,
                description=description,
                func=func,
            )

        self._tools[name] = tool
        logger.info(f"已注册工具: {name}")

    def get_tool(self, name: str) -> Tool | StructuredTool:
        """获取单个工具。

        Raises:
            KeyError: 工具不存在
        """
        tool = self._tools.get(name)
        if tool is None:
            raise KeyError(
                f"工具 '{name}' 未注册。"
                f"可用工具：{list(self._tools.keys())}"
            )
        return tool

    def get_tools(self, names: list[str]) -> list[Tool | StructuredTool]:
        """批量获取工具列表。"""
        return [self.get_tool(name) for name in names]

    def list_tool_names(self) -> list[str]:
        """列出所有已注册的工具名称。"""
        return list(self._tools.keys())

    def get_tool_descriptions(self) -> str:
        """生成所有工具的描述文本（供 LLM 了解可用工具）。"""
        lines = []
        for name, tool in self._tools.items():
            lines.append(f"- {name}: {tool.description}")
        return "\n".join(lines)


# 模块级单例
_registry: ToolRegistry | None = None


def get_tool_registry() -> ToolRegistry:
    """获取 ToolRegistry 单例。"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def reset_tool_registry() -> None:
    """重置单例（测试用）。"""
    global _registry
    _registry = None
