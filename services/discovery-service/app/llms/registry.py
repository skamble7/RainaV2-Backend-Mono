from app.config import settings
from .base import LLMProvider
from .openai_provider import OpenAIProvider

def get_provider(model_id: str | None = None) -> LLMProvider:
    model = model_id or settings.MODEL_ID
    prefix, _, actual = model.partition(":")
    match prefix:
        case "openai":
            return OpenAIProvider(model_id=actual or "gpt-4o-mini", api_key=settings.OPENAI_API_KEY)
        # case "anthropic": return AnthropicProvider(...)
        # case "azure": return AzureOpenAIProvider(...)
        # case "ollama": return OllamaProvider(...)
        case _:
            raise ValueError(f"Unknown model provider prefix: {prefix}")
