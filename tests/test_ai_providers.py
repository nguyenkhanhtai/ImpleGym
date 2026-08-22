"""Tests for dedicated AI providers (OpenAI, Gemini, DeepSeek, Claude, Ollama)."""

from implegym.ai.client import LLMManager
from implegym.ai.providers import (
    ClaudeProvider,
    DeepSeekProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
)


def test_llm_manager_provider_registry() -> None:
    """Test LLMManager manages all dedicated providers."""
    manager = LLMManager()
    providers = manager.list_available_providers()

    assert len(providers) == 5
    provider_names = {p["name"] for p in providers}
    assert provider_names == {"openai", "gemini", "deepseek", "claude", "ollama"}


def test_dedicated_provider_initialization() -> None:
    """Test dedicated provider classes instantiate with correct defaults."""
    openai_p = OpenAIProvider(api_key="test-key", model="gpt-4o")
    assert openai_p.provider_name == "openai"
    assert openai_p.is_configured is True

    gemini_p = GeminiProvider(api_key="gemini-key", model="gemini-2.5-flash")
    assert gemini_p.provider_name == "gemini"
    assert gemini_p.is_configured is True

    deepseek_p = DeepSeekProvider(api_key="ds-key", model="deepseek-chat")
    assert deepseek_p.provider_name == "deepseek"
    assert deepseek_p.is_configured is True

    claude_p = ClaudeProvider(api_key="anthropic-key", model="claude-3-5-sonnet")
    assert claude_p.provider_name == "claude"
    assert claude_p.is_configured is True

    ollama_p = OllamaProvider(base_url="http://localhost:11434/v1", model="llama3")
    assert ollama_p.provider_name == "ollama"
    assert ollama_p.is_configured is True


def test_llm_manager_dynamic_configuration() -> None:
    """Test updating LLMManager configuration at runtime."""
    from implegym.models.schemas import AIConfigSchema

    manager = LLMManager()

    config = AIConfigSchema(
        provider="deepseek",
        model="deepseek-reasoner",
        api_key="ds-secret-key",
        api_base="https://custom.deepseek.api/v1",
        temperature=0.7,
        max_tokens=2048,
    )
    manager.configure_provider(config)

    active = manager.get_provider()
    assert active.provider_name == "deepseek"
    assert active.model == "deepseek-reasoner"
    assert active.api_base == "https://custom.deepseek.api/v1"
    assert active.temperature == 0.7
    assert active.max_tokens == 2048
    assert active.is_configured is True


def test_provider_model_listings() -> None:
    """Test retrieving available models across all providers."""
    manager = LLMManager()

    openai_models = manager.get_models_for_provider("openai")
    assert "gpt-4o" in openai_models
    assert "o3-mini" in openai_models

    gemini_models = manager.get_models_for_provider("gemini")
    assert "gemini-2.5-flash" in gemini_models

    deepseek_models = manager.get_models_for_provider("deepseek")
    assert "deepseek-reasoner" in deepseek_models

    claude_models = manager.get_models_for_provider("claude")
    assert "claude-3-5-sonnet-20241022" in claude_models

    ollama_models = manager.get_models_for_provider("ollama")
    assert "qwen2.5-coder:latest" in ollama_models
