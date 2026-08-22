"""Central LLM manager and dynamic provider router."""

import os
from typing import Any, Optional

from implegym.ai.providers import (
    BaseLLMProvider,
    ClaudeProvider,
    DeepSeekProvider,
    GeminiProvider,
    OllamaProvider,
    OpenAIProvider,
)
from implegym.models.schemas import AIConfigSchema


class LLMManager:
    """Factory and router for multi-provider AI servers (OpenAI, Gemini, DeepSeek, Claude, Ollama) with dynamic hyperparameters."""

    _instance: Optional["LLMManager"] = None

    def __init__(self, default_provider: str | None = None) -> None:
        self.default_provider_name = default_provider or os.getenv("AI_PROVIDER", "openai").lower()
        self.default_temperature: float = 0.3
        self.default_max_tokens: int | None = 4096
        self._providers: dict[str, BaseLLMProvider] = {
            "openai": OpenAIProvider(),
            "gemini": GeminiProvider(),
            "deepseek": DeepSeekProvider(),
            "claude": ClaudeProvider(),
            "ollama": OllamaProvider(),
        }

    @classmethod
    def get_instance(cls) -> "LLMManager":
        """Get or create singleton LLMManager instance."""
        if cls._instance is None:
            cls._instance = LLMManager()
        return cls._instance

    def configure_provider(self, config: AIConfigSchema) -> None:
        """Update provider settings and hyperparameters at runtime."""
        name = config.provider.lower()
        self.default_provider_name = name
        self.default_temperature = config.temperature
        self.default_max_tokens = config.max_tokens

        if name == "openai":
            self._providers["openai"] = OpenAIProvider(
                api_key=config.api_key,
                model=config.model,
                api_base=config.api_base,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
        elif name == "gemini":
            self._providers["gemini"] = GeminiProvider(
                api_key=config.api_key,
                model=config.model,
                api_base=config.api_base,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
        elif name == "deepseek":
            self._providers["deepseek"] = DeepSeekProvider(
                api_key=config.api_key,
                model=config.model,
                api_base=config.api_base,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
        elif name == "claude":
            self._providers["claude"] = ClaudeProvider(
                api_key=config.api_key,
                model=config.model,
                api_base=config.api_base,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )
        elif name == "ollama":
            self._providers["ollama"] = OllamaProvider(
                base_url=config.api_base,
                model=config.model,
                temperature=config.temperature,
                max_tokens=config.max_tokens,
            )

    def get_provider(self, name: str | None = None) -> BaseLLMProvider:
        """Retrieve dedicated provider instance by name."""
        provider_key = (name or self.default_provider_name).lower()
        provider = self._providers.get(provider_key)
        if not provider:
            return self._providers["openai"]
        return provider

    def get_current_config(self) -> dict[str, Any]:
        """Return currently active configuration with masked API keys for safety."""
        active = self.get_provider()
        masked_key = ""
        if active.api_key and active.api_key != "ollama":
            masked_key = (
                f"{active.api_key[:4]}...{active.api_key[-4:]}"
                if len(active.api_key) > 8
                else "***"
            )

        return {
            "provider": active.provider_name,
            "model": active.model,
            "api_base": active.api_base,
            "api_key_masked": masked_key,
            "is_configured": active.is_configured,
            "temperature": active.temperature,
            "max_tokens": active.max_tokens,
        }

    def get_models_for_provider(self, name: str | None = None) -> list[str]:
        """Get list of supported models for a specific provider."""
        provider = self.get_provider(name)
        return provider.get_available_models()

    def list_available_providers(self) -> list[dict[str, Any]]:
        """List all supported providers with their configuration status and default models."""
        return [
            {
                "name": p.provider_name,
                "model": p.model,
                "api_base": p.api_base,
                "is_configured": p.is_configured,
                "temperature": p.temperature,
                "max_tokens": p.max_tokens,
                "available_models": p.get_available_models(),
            }
            for p in self._providers.values()
        ]

    @property
    def is_configured(self) -> bool:
        """Check if the active provider is configured."""
        active = self.get_provider()
        return active.is_configured

    async def chat_completion(
        self,
        messages: list[dict[str, str]],
        provider: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        response_format: dict[str, Any] | None = None,
        config_override: AIConfigSchema | None = None,
    ) -> str:
        """Route chat completion to requested provider with hyperparameter overrides."""
        if config_override:
            temp_provider = self._create_temporary_provider(config_override)
            return await temp_provider.chat_completion(
                messages=messages,
                temperature=temperature or config_override.temperature,
                max_tokens=max_tokens or config_override.max_tokens,
                response_format=response_format,
            )

        target_provider = self.get_provider(provider)
        return await target_provider.chat_completion(
            messages=messages,
            temperature=temperature,
            max_tokens=max_tokens,
            response_format=response_format,
        )

    def _create_temporary_provider(self, config: AIConfigSchema) -> BaseLLMProvider:
        """Create on-the-fly provider for one-off request with custom config."""
        name = config.provider.lower()
        if name == "gemini":
            return GeminiProvider(
                config.api_key, config.model, config.api_base, config.temperature, config.max_tokens
            )
        elif name == "deepseek":
            return DeepSeekProvider(
                config.api_key, config.model, config.api_base, config.temperature, config.max_tokens
            )
        elif name == "claude":
            return ClaudeProvider(
                config.api_key, config.model, config.api_base, config.temperature, config.max_tokens
            )
        elif name == "ollama":
            return OllamaProvider(
                config.api_base, config.model, config.temperature, config.max_tokens
            )
        return OpenAIProvider(
            config.api_key, config.model, config.api_base, config.temperature, config.max_tokens
        )


# Backward compatibility alias
OpenAIClient = LLMManager
