from pydantic import BaseModel


class BotRegistryItem(BaseModel):
    bot_key: str
    display_name: str | None = None
    canonical_base: str | None = None
    is_active: bool = True
    replicate: bool = True
    exists: bool | None = None


class BotRegistryUpsert(BaseModel):
    bot_key: str
    display_name: str | None = None
    canonical_base: str | None = None
    is_active: bool = True
    replicate: bool = True
