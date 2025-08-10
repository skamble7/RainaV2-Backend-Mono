from typing import Protocol

class PlaybookResolver(Protocol):
    async def resolve(self, playbook_id: str) -> dict: ...
