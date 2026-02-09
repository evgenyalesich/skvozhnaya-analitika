from typing import List, Optional

import asyncpg
from fastapi import APIRouter, Query

from app.db.postgres_explorer import PostgresExplorer

router = APIRouter(prefix="/api/utm", tags=["utm"])

UTM_MAP = {
    "utm_source": "source",
    "utm_campaign": "campaign",
    "utm_medium": "medium",
    "utm_content": "content",
    "utm_term": "term",
}


async def _collect_field(field: str, databases: Optional[List[str]]) -> list[str]:
    explorer = PostgresExplorer()
    dbs = databases or await explorer.list_bot_databases()
    values: set[str] = set()
    column = UTM_MAP[field]
    for db in dbs:
        kwargs = explorer._connection_kwargs(database=db)
        try:
            conn = await asyncpg.connect(**kwargs)
            try:
                rows = await conn.fetch(
                    f"SELECT DISTINCT {column} AS value FROM lead_resources "
                    f"WHERE {column} IS NOT NULL AND {column} <> ''"
                )
                for row in rows:
                    values.add(row["value"])
            finally:
                await conn.close()
        except Exception:
            continue
    return sorted(values)


@router.get("/sources", summary="Список UTM Source")
async def list_sources(databases: Optional[List[str]] = Query(None)):
    return {"sources": await _collect_field("utm_source", databases)}


@router.get("/campaigns", summary="Список UTM Campaign")
async def list_campaigns(databases: Optional[List[str]] = Query(None)):
    return {"campaigns": await _collect_field("utm_campaign", databases)}


@router.get("/mediums", summary="Список UTM Medium")
async def list_mediums(databases: Optional[List[str]] = Query(None)):
    return {"mediums": await _collect_field("utm_medium", databases)}


@router.get("/contents", summary="Список UTM Content")
async def list_contents(databases: Optional[List[str]] = Query(None)):
    return {"contents": await _collect_field("utm_content", databases)}


@router.get("/terms", summary="Список UTM Term")
async def list_terms(databases: Optional[List[str]] = Query(None)):
    return {"terms": await _collect_field("utm_term", databases)}
