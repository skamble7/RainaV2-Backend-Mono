from typing import Protocol, List, Dict, Any

class ChatMessage(Dict[str, str]): ...
# e.g. {"role": "user", "content": "..."}

class LLMProvider(Protocol):
    model_id: str
    async def chat(self, messages: List[ChatMessage], **kwargs) -> str: ...
