from typing import Any, Dict, List

from pydantic import BaseModel, Field


class DatabaseListResponse(BaseModel):
    databases: List[str] = Field(default_factory=list)


class DatabaseQueryRequest(BaseModel):
    database: str
    query: str
    limit: int = 100


class DatabaseQueryResponse(BaseModel):
    rows: List[Dict[str, Any]] = Field(default_factory=list)
