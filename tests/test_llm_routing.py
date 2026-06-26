from types import SimpleNamespace

from services.llm import _fallback_models


class TestLLMFallbackRouting:
    def test_cloud_mode_keeps_local_fallback_without_api_keys(self):
        settings = SimpleNamespace(
            KIMI_API_KEY="",
            DEEPSEEK_API_KEY="",
            ANTHROPIC_API_KEY="",
            OPENAI_API_KEY="",
            LOCAL_LLM_MODEL="qwen3.5:0.8b",
        )

        models = _fallback_models("kimi-k2.6", settings, "cloud")

        assert models == ["local:qwen3.5:0.8b"]

    def test_local_mode_forces_selected_model(self):
        settings = SimpleNamespace(LOCAL_LLM_MODEL="qwen3.5:0.8b")

        models = _fallback_models("", settings, "local")

        assert models == ["local:qwen3.5:0.8b"]
