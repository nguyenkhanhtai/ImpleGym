"""Multi-provider AI abstractions and dedicated implementations with dynamic hyperparameters."""

import os
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
import httpx
from openai import AsyncOpenAI
from implegym.config import settings


class BaseLLMProvider(ABC):
    """Abstract base class for all AI model providers."""

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = 4096,
    ) -> None:
        self.api_key = api_key
        self.model = model
        self.api_base = api_base
        self.temperature = temperature
        self.max_tokens = max_tokens

    @property
    @abstractmethod
    def provider_name(self) -> str:
        """Name identifier for the provider."""
        pass

    @property
    @abstractmethod
    def is_configured(self) -> bool:
        """Check if provider credentials/endpoints are set."""
        pass

    @abstractmethod
    def get_available_models(self) -> List[str]:
        """Return list of standard/discovered models for this provider."""
        pass

    @abstractmethod
    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Send chat messages and return the completion response text."""
        pass


class OpenAIProvider(BaseLLMProvider):
    """Dedicated provider for OpenAI (GPT-4o, o3-mini, o1, etc.)."""

    DEFAULT_BASE = "https://api.openai.com/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = 4096,
    ) -> None:
        key = api_key or os.getenv("OPENAI_API_KEY") or settings.openai_api_key
        mdl = model or os.getenv("OPENAI_MODEL", "gpt-4o")
        base = api_base or os.getenv("OPENAI_API_BASE", self.DEFAULT_BASE)
        super().__init__(api_key=key, model=mdl, api_base=base, temperature=temperature, max_tokens=max_tokens)
        self._init_client()

    def _init_client(self) -> None:
        if self.api_key:
            kwargs: Dict[str, Any] = {"api_key": self.api_key}
            if self.api_base:
                kwargs["base_url"] = self.api_base
            self._client = AsyncOpenAI(**kwargs)
        else:
            self._client = None

    @property
    def provider_name(self) -> str:
        return "openai"

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    def get_available_models(self) -> List[str]:
        return [
            "gpt-4o",
            "gpt-4o-mini",
            "o3-mini",
            "o1",
            "o1-mini",
            "gpt-4-turbo",
            "gpt-3.5-turbo",
        ]

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self._client:
            raise ValueError("OpenAI API key is not configured.")

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens or self.max_tokens:
            kwargs["max_tokens"] = max_tokens or self.max_tokens
        if response_format:
            kwargs["response_format"] = response_format

        res = await self._client.chat.completions.create(**kwargs)
        return (res.choices[0].message.content or "").strip()


class GeminiProvider(BaseLLMProvider):
    """Dedicated provider for Google Gemini via OpenAI-compatible endpoint."""

    DEFAULT_BASE = "https://generativelanguage.googleapis.com/v1beta/openai/"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = 4096,
    ) -> None:
        key = api_key or os.getenv("GEMINI_API_KEY")
        mdl = model or os.getenv("GEMINI_MODEL", "gemini-2.5-flash")
        base = api_base or os.getenv("GEMINI_API_BASE", self.DEFAULT_BASE)
        super().__init__(api_key=key, model=mdl, api_base=base, temperature=temperature, max_tokens=max_tokens)
        self._init_client()

    def _init_client(self) -> None:
        if self.api_key:
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.api_base)
        else:
            self._client = None

    @property
    def provider_name(self) -> str:
        return "gemini"

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    def get_available_models(self) -> List[str]:
        return [
            "gemini-2.5-flash",
            "gemini-2.5-pro",
            "gemini-2.0-flash",
            "gemini-1.5-pro",
            "gemini-1.5-flash",
        ]

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self._client:
            raise ValueError("Gemini API key is not configured (GEMINI_API_KEY).")

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens or self.max_tokens:
            kwargs["max_tokens"] = max_tokens or self.max_tokens
        if response_format:
            kwargs["response_format"] = response_format

        res = await self._client.chat.completions.create(**kwargs)
        return (res.choices[0].message.content or "").strip()


class DeepSeekProvider(BaseLLMProvider):
    """Dedicated provider for DeepSeek (deepseek-chat, deepseek-reasoner)."""

    DEFAULT_BASE = "https://api.deepseek.com/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = 4096,
    ) -> None:
        key = api_key or os.getenv("DEEPSEEK_API_KEY")
        mdl = model or os.getenv("DEEPSEEK_MODEL", "deepseek-chat")
        base = api_base or os.getenv("DEEPSEEK_API_BASE", self.DEFAULT_BASE)
        super().__init__(api_key=key, model=mdl, api_base=base, temperature=temperature, max_tokens=max_tokens)
        self._init_client()

    def _init_client(self) -> None:
        if self.api_key:
            self._client = AsyncOpenAI(api_key=self.api_key, base_url=self.api_base)
        else:
            self._client = None

    @property
    def provider_name(self) -> str:
        return "deepseek"

    @property
    def is_configured(self) -> bool:
        return self._client is not None

    def get_available_models(self) -> List[str]:
        return [
            "deepseek-chat",
            "deepseek-reasoner",
            "deepseek-coder",
        ]

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self._client:
            raise ValueError("DeepSeek API key is not configured (DEEPSEEK_API_KEY).")

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens or self.max_tokens:
            kwargs["max_tokens"] = max_tokens or self.max_tokens
        if response_format:
            kwargs["response_format"] = response_format

        res = await self._client.chat.completions.create(**kwargs)
        return (res.choices[0].message.content or "").strip()


class ClaudeProvider(BaseLLMProvider):
    """Dedicated provider for Anthropic Claude via Messages API."""

    DEFAULT_BASE = "https://api.anthropic.com/v1"

    def __init__(
        self,
        api_key: Optional[str] = None,
        model: Optional[str] = None,
        api_base: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = 4096,
    ) -> None:
        key = api_key or os.getenv("ANTHROPIC_API_KEY")
        mdl = model or os.getenv("ANTHROPIC_MODEL", "claude-3-5-sonnet-20241022")
        base = api_base or os.getenv("ANTHROPIC_API_BASE", self.DEFAULT_BASE)
        super().__init__(api_key=key, model=mdl, api_base=base, temperature=temperature, max_tokens=max_tokens)

    @property
    def provider_name(self) -> str:
        return "claude"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_key)

    def get_available_models(self) -> List[str]:
        return [
            "claude-3-7-sonnet-20250219",
            "claude-3-5-sonnet-20241022",
            "claude-3-5-haiku-20241022",
            "claude-3-opus-20240229",
        ]

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        if not self.api_key:
            raise ValueError("Anthropic API key is not configured (ANTHROPIC_API_KEY).")

        system_prompt = ""
        user_messages: List[Dict[str, str]] = []
        for m in messages:
            if m["role"] == "system":
                system_prompt += m["content"] + "\n"
            else:
                user_messages.append({"role": m["role"], "content": m["content"]})

        headers = {
            "x-api-key": self.api_key,
            "anthropic-version": "2023-06-01",
            "content-type": "application/json",
        }
        payload: Dict[str, Any] = {
            "model": self.model,
            "max_tokens": max_tokens or self.max_tokens or 4096,
            "temperature": temperature if temperature is not None else self.temperature,
            "messages": user_messages,
        }
        if system_prompt.strip():
            payload["system"] = system_prompt.strip()

        endpoint = f"{self.api_base.rstrip('/')}/messages" if self.api_base else "https://api.anthropic.com/v1/messages"
        async with httpx.AsyncClient(timeout=60.0) as client:
            resp = await client.post(endpoint, headers=headers, json=payload)
            resp.raise_for_status()
            data = resp.json()
            content = data.get("content", [])
            if content and isinstance(content, list):
                return content[0].get("text", "").strip()
            return ""


class OllamaProvider(BaseLLMProvider):
    """Dedicated provider for local Ollama LLMs (e.g. llama3, deepseek-r1, qwen2.5-coder)."""

    DEFAULT_BASE = "http://localhost:11434/v1"

    def __init__(
        self,
        base_url: Optional[str] = None,
        model: Optional[str] = None,
        temperature: float = 0.3,
        max_tokens: Optional[int] = 4096,
    ) -> None:
        base = base_url or os.getenv("OLLAMA_BASE_URL", self.DEFAULT_BASE)
        mdl = model or os.getenv("OLLAMA_MODEL", "qwen2.5-coder:latest")
        super().__init__(api_key="ollama", model=mdl, api_base=base, temperature=temperature, max_tokens=max_tokens)
        self._client = AsyncOpenAI(api_key="ollama", base_url=self.api_base)

    @property
    def provider_name(self) -> str:
        return "ollama"

    @property
    def is_configured(self) -> bool:
        return bool(self.api_base)

    def get_available_models(self) -> List[str]:
        return [
            "qwen2.5-coder:latest",
            "deepseek-r1:latest",
            "deepseek-r1:7b",
            "deepseek-r1:14b",
            "llama3.3:latest",
            "llama3:latest",
            "codellama:latest",
            "mistral:latest",
        ]

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: Optional[float] = None,
        max_tokens: Optional[int] = None,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature if temperature is not None else self.temperature,
        }
        if max_tokens or self.max_tokens:
            kwargs["max_tokens"] = max_tokens or self.max_tokens
        if response_format:
            kwargs["response_format"] = response_format

        res = await self._client.chat.completions.create(**kwargs)
        return (res.choices[0].message.content or "").strip()
