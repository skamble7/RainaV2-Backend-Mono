# app/llms/registry.py
from app.config import settings
from .base import LLMProvider
from .openai_provider import OpenAIProvider

def get_provider(model_id: str | None = None) -> LLMProvider:
    model = model_id or settings.MODEL_ID
    if not model:
        raise ValueError("MODEL_ID is not configured")

    # Accept either "openai:gpt-4o-mini" or plain "gpt-4o-mini"
    if ":" not in model:
        # default to OpenAI if no provider prefix
        return OpenAIProvider(model_id=model, api_key=settings.OPENAI_API_KEY)

    prefix, _, actual = model.partition(":")
    if prefix == "openai":
        return OpenAIProvider(model_id=actual or "gpt-4o-mini", api_key=settings.OPENAI_API_KEY)

    raise ValueError(f"Unknown model provider prefix: {prefix}")
