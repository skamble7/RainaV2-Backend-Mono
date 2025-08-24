# app/llms/openai_provider.py
from typing import List, Optional, Dict, Any
from .base import LLMProvider, ChatMessage
from openai import AsyncOpenAI, APIError, BadRequestError
import os, json, logging

log = logging.getLogger(__name__)

def _stringify_messages(messages: List[ChatMessage]) -> List[Dict[str, str]]:
    out: List[Dict[str, str]] = []
    for m in messages:
        role = m.get("role")
        content = m.get("content")
        if not isinstance(content, str):
            content = json.dumps(content, separators=(",", ":"))
        out.append({"role": role, "content": content})
    return out

class OpenAIProvider(LLMProvider):
    def __init__(self, model_id: str, api_key: str | None = None):
        self.model_id = model_id
        self._client = AsyncOpenAI(api_key=api_key or os.getenv("OPENAI_API_KEY"))

    async def chat(self, messages: List[ChatMessage], **kwargs) -> str:
        try:
            resp = await self._client.chat.completions.create(
                model=self.model_id,
                messages=_stringify_messages(messages),
                temperature=kwargs.get("temperature", 0.2),
                max_tokens=kwargs.get("max_tokens"),
            )
            return resp.choices[0].message.content or ""
        except BadRequestError as e:
            # Surfacing the server's error body is critical to fix 400s fast
            log.error("OpenAI chat 400: %s", getattr(e, "response", None) and e.response.text)
            raise
        except APIError as e:
            log.exception("OpenAI chat APIError")
            raise

    async def chat_json(self, messages: List[ChatMessage], **kwargs) -> str:
        """Force JSON object output when supported."""
        try:
            resp = await self._client.chat.completions.create(
                model=self.model_id,
                messages=_stringify_messages(messages),
                temperature=kwargs.get("temperature", 0.2),
                response_format={"type": "json_object"},
                max_tokens=kwargs.get("max_tokens"),
            )
            content = resp.choices[0].message.content or "{}"
            # Guardrail: ensure it’s valid JSON
            json.loads(content)
            return content
        except BadRequestError as e:
            log.error("OpenAI chat_json 400: %s", getattr(e, "response", None) and e.response.text)
            raise
        except APIError as e:
            log.exception("OpenAI chat_json APIError")
            raise
