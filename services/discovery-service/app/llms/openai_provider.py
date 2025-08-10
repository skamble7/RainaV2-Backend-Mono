from typing import List, Optional, Dict, Any
from .base import LLMProvider, ChatMessage
from openai import AsyncOpenAI
import os

class OpenAIProvider(LLMProvider):
    def __init__(self, model_id: str, api_key: str | None = None):
        self.model_id = model_id
        self._client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    async def chat(self, messages: List[ChatMessage], **kwargs) -> str:
        resp = await self._client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            temperature=kwargs.get("temperature", 0.2),
        )
        return resp.choices[0].message.content or ""

    async def chat_json(self, messages: List[ChatMessage], **kwargs) -> str:
        """Force JSON object output when supported."""
        resp = await self._client.chat.completions.create(
            model=self.model_id,
            messages=messages,
            temperature=kwargs.get("temperature", 0.2),
            response_format={"type": "json_object"},
        )
        return resp.choices[0].message.content or "{}"
