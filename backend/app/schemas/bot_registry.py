from pydantic import BaseModel


class BotRegistryItem(BaseModel):
    bot_key: str
    display_name: str | None = None
    is_active: bool = True
    exists: bool | None = None


class BotRegistryUpsert(BaseModel):
    bot_key: str
    display_name: str | None = None
    is_active: bool = True
