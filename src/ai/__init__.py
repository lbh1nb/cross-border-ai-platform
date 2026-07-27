"""AI 调度层：统一管理 LLM 模型路由、Prompt 模板和工具注册。

设计思想：
- ModelRouter：按任务复杂度自动选择模型（简单任务用便宜模型，复杂任务用强模型）
- PromptManager：集中管理 Prompt 模板，支持变量渲染和版本管理
- ToolRegistry：工具注册中心，Agent 通过名称调用工具

三者解耦，便于独立测试和扩展。
"""

from src.ai.model_router import ModelRouter, get_model_router
from src.ai.prompt_manager import PromptManager, get_prompt_manager
from src.ai.tool_registry import ToolRegistry, get_tool_registry

__all__ = [
    "ModelRouter",
    "get_model_router",
    "PromptManager",
    "get_prompt_manager",
    "ToolRegistry",
    "get_tool_registry",
]
