"""OpenAI API client wrapper with fallback and structured response handling."""

import os
from typing import Any, Dict, List, Optional
from openai import AsyncOpenAI
from implegym.config import settings


class OpenAIClient:
    """Async OpenAI API client manager."""

    def __init__(self, api_key: Optional[str] = None, model: Optional[str] = None) -> None:
        self.api_key = api_key or settings.openai_api_key or os.getenv("OPENAI_API_KEY")
        self.model = model or settings.openai_model
        self._client: Optional[AsyncOpenAI] = None
        if self.api_key:
            self._client = AsyncOpenAI(api_key=self.api_key)

    @property
    def is_configured(self) -> bool:
        """Check whether OpenAI API key is configured."""
        return self._client is not None

    async def chat_completion(
        self,
        messages: List[Dict[str, str]],
        temperature: float = 0.3,
        response_format: Optional[Dict[str, Any]] = None,
    ) -> str:
        """Execute chat completion with retry handling."""
        if not self._client:
            raise ValueError(
                "OpenAI API key is not configured. Please set OPENAI_API_KEY in your environment or .env file."
            )

        kwargs: Dict[str, Any] = {
            "model": self.model,
            "messages": messages,
            "temperature": temperature,
        }
        if response_format:
            kwargs["response_format"] = response_format

        response = await self._client.chat.completions.create(**kwargs)
        content = response.choices[0].message.content or ""
        return content.strip()
