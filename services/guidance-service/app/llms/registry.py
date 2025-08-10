from typing import Optional
from app.config import settings

class LLMProvider:
    async def complete(self, system: str, user: str, model_id: Optional[str], temperature: Optional[float], max_tokens: Optional[int]) -> str:
        raise NotImplementedError

# --- OpenAI ---
class OpenAIProvider(LLMProvider):
    async def complete(self, system, user, model_id, temperature, max_tokens):
        if not settings.OPENAI_API_KEY:
            raise RuntimeError("OPENAI_API_KEY is not set")
        from openai import AsyncOpenAI
        client = AsyncOpenAI(api_key=settings.OPENAI_API_KEY)
        resp = await client.chat.completions.create(
            model=model_id or settings.LLM_MODEL_ID,
            temperature=temperature if temperature is not None else settings.LLM_TEMP,
            max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
        )
        return resp.choices[0].message.content

# --- Azure OpenAI ---
class AzureOpenAIProvider(LLMProvider):
    async def complete(self, system, user, model_id, temperature, max_tokens):
        if not (settings.AZURE_OPENAI_API_KEY and settings.AZURE_OPENAI_ENDPOINT and settings.AZURE_OPENAI_DEPLOYMENT):
            raise RuntimeError("Azure OpenAI env vars not set")
        from openai import AsyncAzureOpenAI
        client = AsyncAzureOpenAI(
            api_key=settings.AZURE_OPENAI_API_KEY,
            azure_endpoint=settings.AZURE_OPENAI_ENDPOINT,
            api_version="2024-06-01",
        )
        resp = await client.chat.completions.create(
            model=settings.AZURE_OPENAI_DEPLOYMENT,
            temperature=temperature if temperature is not None else settings.LLM_TEMP,
            max_tokens=max_tokens or settings.LLM_MAX_TOKENS,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": user}
            ],
        )
        return resp.choices[0].message.content

def get_provider(name: Optional[str] = None) -> LLMProvider:
    name = (name or settings.LLM_PROVIDER).lower()
    if name == "openai": return OpenAIProvider()
    if name == "azure":  return AzureOpenAIProvider()
    raise ValueError(f"Unknown LLM provider: {name}")
