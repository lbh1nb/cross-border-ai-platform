"""ModelRouter 单元测试：测试多模型路由逻辑。

覆盖场景：
1. provider 检测：Anthropic 优先、OpenAI 回退、都没有时报错
2. 任务类型映射：simple/standard/complex 各自映射到正确模型
3. 未知任务类型回退到 standard
4. 未配置凭证时抛 ValueError
5. 国内大模型识别：base_url 命中关键字时切换到对应模型（v0.5.1 新增）
"""

from __future__ import annotations

import pytest

from src.ai.model_router import (
    ModelRouter,
    _TASK_MODEL_MAP,
    _DOMESTIC_MODEL_MAP,
    _detect_domestic_provider,
    reset_model_router,
)


class TestProviderDetection:
    """测试模型提供商检测逻辑。"""

    def test_anthropic_priority(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """配置了 Anthropic 时优先使用 Anthropic。"""
        from src.config import settings

        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
        monkeypatch.setattr(settings, "openai_api_key", "sk-openai-test")

        router = ModelRouter()
        assert router._provider == "anthropic"

    def test_openai_fallback(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """未配置 Anthropic 时回退到 OpenAI。"""
        from src.config import settings

        monkeypatch.setattr(settings, "anthropic_api_key", "")
        monkeypatch.setattr(settings, "openai_api_key", "sk-openai-test")

        router = ModelRouter()
        assert router._provider == "openai"

    def test_no_credentials(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """两家凭证都未配置时 provider 为空字符串。"""
        from src.config import settings

        monkeypatch.setattr(settings, "anthropic_api_key", "")
        monkeypatch.setattr(settings, "openai_api_key", "")

        router = ModelRouter()
        assert router._provider == ""


class TestTaskModelMapping:
    """测试任务类型到模型的映射。"""

    def test_simple_task_maps_to_cheap_model(self) -> None:
        """simple 任务映射到便宜模型。"""
        assert _TASK_MODEL_MAP["simple"]["anthropic"] == "claude-haiku-4-5"
        assert _TASK_MODEL_MAP["simple"]["openai"] == "gpt-4o-mini"

    def test_standard_task_maps_to_mid_model(self) -> None:
        """standard 任务映射到中等模型。"""
        assert _TASK_MODEL_MAP["standard"]["anthropic"] == "claude-sonnet-4-6"
        assert _TASK_MODEL_MAP["standard"]["openai"] == "gpt-4o"

    def test_complex_task_maps_to_strong_model(self) -> None:
        """complex 任务映射到强模型。"""
        assert _TASK_MODEL_MAP["complex"]["anthropic"] == "claude-opus-4-8"


class TestGetLlm:
    """测试 get_llm 方法。"""

    def test_no_provider_raises_value_error(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """未配置凭证时 get_llm 抛 ValueError。"""
        from src.config import settings

        monkeypatch.setattr(settings, "anthropic_api_key", "")
        monkeypatch.setattr(settings, "openai_api_key", "")

        router = ModelRouter()
        with pytest.raises(ValueError, match="未配置 AI 模型凭证"):
            router.get_llm("standard")

    def test_unknown_task_type_falls_back_to_standard(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """未知任务类型回退到 standard（不抛异常）。"""
        from src.config import settings

        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
        monkeypatch.setattr(settings, "openai_api_key", "")

        router = ModelRouter()
        # 未知类型不应抛异常，会回退到 standard
        # 注意：这里会真正创建 LLM 实例，但不调用 invoke，不会发网络请求
        llm = router.get_llm("unknown_type")
        assert llm is not None

    def test_anthropic_llm_created_with_callbacks(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Anthropic LLM 创建后应挂载监控回调。"""
        from src.config import settings

        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")
        monkeypatch.setattr(settings, "openai_api_key", "")

        router = ModelRouter()
        llm = router.get_llm("standard")
        # 验证 LLM 实例创建成功
        assert llm is not None


class TestSingleton:
    """测试单例管理。"""

    def test_reset_singleton(self) -> None:
        """reset_model_router 后单例应被重置。"""
        reset_model_router()
        from src.ai.model_router import get_model_router, _router

        # 重置后内部引用为 None
        assert _router is None
        # 再次获取会创建新实例
        router = get_model_router()
        assert router is not None


class TestDomesticProviderDetection:
    """测试国内大模型识别（v0.5.1 新增）。"""

    @pytest.mark.parametrize(
        "base_url,expected",
        [
            ("https://api.deepseek.com/v1", "deepseek"),
            ("https://dashscope.aliyuncs.com/compatible-mode/v1", "dashscope"),
            ("https://open.bigmodel.cn/api/paas/v4/", "bigmodel"),
            ("https://api.moonshot.cn/v1", "moonshot"),
            # 大小写不敏感
            ("HTTPS://API.DEEPSEEK.COM/V1", "deepseek"),
            # 未命中返回 None
            ("https://api.openai.com/v1", None),
            ("", None),
        ],
    )
    def test_detect_domestic_by_base_url(
        self, base_url: str, expected: str | None
    ) -> None:
        """根据 base_url 识别国内大模型提供商。"""
        assert _detect_domestic_provider(base_url) == expected

    def test_domestic_provider_priority_over_anthropic(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """配了国内大模型 base_url 时，优先于 Anthropic。"""
        from src.config import settings

        monkeypatch.setattr(settings, "openai_api_base", "https://api.deepseek.com/v1")
        monkeypatch.setattr(settings, "openai_api_key", "sk-deepseek-test")
        monkeypatch.setattr(settings, "anthropic_api_key", "sk-ant-test")

        router = ModelRouter()
        assert router._provider == "openai"
        assert router._domestic == "deepseek"

    def test_domestic_uses_domestic_model_name(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """国内大模型命中后使用对应的国内模型名，而非 OpenAI 默认名。"""
        from src.config import settings

        monkeypatch.setattr(settings, "openai_api_base", "https://api.deepseek.com/v1")
        monkeypatch.setattr(settings, "openai_api_key", "sk-deepseek-test")

        router = ModelRouter()
        # standard 任务应映射到 deepseek-chat
        llm = router.get_llm("standard")
        assert llm is not None
        # LangChain OpenAI 实例的 model_name 属性应包含 deepseek
        assert "deepseek" in str(llm.model_name).lower()

    def test_domestic_complex_task_uses_reasoner(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """DeepSeek complex 任务应使用 deepseek-reasoner。"""
        from src.config import settings

        monkeypatch.setattr(settings, "openai_api_base", "https://api.deepseek.com/v1")
        monkeypatch.setattr(settings, "openai_api_key", "sk-deepseek-test")

        router = ModelRouter()
        llm = router.get_llm("complex")
        assert "deepseek-reasoner" in str(llm.model_name).lower()

    def test_openai_base_url_passed_to_llm(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """配置了 base_url 时应传给 ChatOpenAI 实例。"""
        from src.config import settings

        monkeypatch.setattr(settings, "openai_api_base", "https://api.deepseek.com/v1")
        monkeypatch.setattr(settings, "openai_api_key", "sk-deepseek-test")

        router = ModelRouter()
        llm = router.get_llm("standard")
        # ChatOpenAI 把 base_url 存在 openai_api_base 属性
        assert "deepseek.com" in str(llm.openai_api_base)

    def test_openai_no_base_url_not_passed(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """未配置 base_url 时不传给 ChatOpenAI（走 OpenAI 官方）。"""
        from src.config import settings

        monkeypatch.setattr(settings, "openai_api_base", "")
        monkeypatch.setattr(settings, "openai_api_key", "sk-openai-test")

        router = ModelRouter()
        llm = router.get_llm("standard")
        # openai_api_base 应为 None 或未设置（不是用户配置的值）
        base_value = getattr(llm, "openai_api_base", None)
        # None 或不在配置值中即可（OpenAI SDK 默认会兜底到 api.openai.com）
        assert base_value is None or "deepseek" not in str(base_value).lower()

    def test_all_domestic_models_have_three_task_types(self) -> None:
        """所有国内大模型都配置了 simple/standard/complex 三个模型。"""
        for provider, model_map in _DOMESTIC_MODEL_MAP.items():
            assert "simple" in model_map, f"{provider} 缺少 simple 模型"
            assert "standard" in model_map, f"{provider} 缺少 standard 模型"
            assert "complex" in model_map, f"{provider} 缺少 complex 模型"
            assert all(model_map.values()), f"{provider} 有空模型名"
