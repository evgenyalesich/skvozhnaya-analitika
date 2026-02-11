from typing import List, Optional

import asyncpg
import hashlib
from fastapi import APIRouter, Query

from app.core.config import settings
from app.core.redis_client import RedisCache
from app.db.postgres_explorer import PostgresExplorer

router = APIRouter(prefix="/api/utm", tags=["utm"])

UTM_MAP = {
    "utm_source": "source",
    "utm_campaign": "campaign",
    "utm_medium": "medium",
    "utm_content": "content",
    "utm_term": "term",
}

UTM_OUTPUT_KEYS = {
    "utm_source": "sources",
    "utm_campaign": "campaigns",
    "utm_medium": "mediums",
    "utm_content": "contents",
    "utm_term": "terms",
}


async def _collect_all_fields(databases: Optional[List[str]]) -> dict[str, list[str]]:
    explorer = PostgresExplorer()
    dbs = databases or await explorer.list_bot_databases()
    dbs = sorted({db for db in dbs if db})
    cache = RedisCache()
    signature = ",".join(dbs)
    cache_key = f"utm:options:{hashlib.md5(signature.encode('utf-8')).hexdigest()}"
    cached = await cache.get_json(cache_key)
    if cached is not None:
        return cached

    sources: set[str] = set()
    campaigns: set[str] = set()
    mediums: set[str] = set()
    contents: set[str] = set()
    terms: set[str] = set()

    query = """
        SELECT
            ARRAY(SELECT DISTINCT source FROM lead_resources WHERE source IS NOT NULL AND source <> '') AS sources,
            ARRAY(SELECT DISTINCT campaign FROM lead_resources WHERE campaign IS NOT NULL AND campaign <> '') AS campaigns,
            ARRAY(SELECT DISTINCT medium FROM lead_resources WHERE medium IS NOT NULL AND medium <> '') AS mediums,
            ARRAY(SELECT DISTINCT content FROM lead_resources WHERE content IS NOT NULL AND content <> '') AS contents,
            ARRAY(SELECT DISTINCT term FROM lead_resources WHERE term IS NOT NULL AND term <> '') AS terms
    """

    for db in dbs:
        kwargs = explorer._connection_kwargs(database=db)
        try:
            conn = await asyncpg.connect(**kwargs)
            try:
                row = await conn.fetchrow(query)
                if row:
                    sources.update(row["sources"] or [])
                    campaigns.update(row["campaigns"] or [])
                    mediums.update(row["mediums"] or [])
                    contents.update(row["contents"] or [])
                    terms.update(row["terms"] or [])
            finally:
                await conn.close()
        except Exception:
            continue

    payload = {
        "sources": sorted(sources),
        "campaigns": sorted(campaigns),
        "mediums": sorted(mediums),
        "contents": sorted(contents),
        "terms": sorted(terms),
    }
    await cache.set_json(cache_key, payload, ttl=settings.cache_ttl_seconds)
    return payload


async def _collect_field(field: str, databases: Optional[List[str]]) -> list[str]:
    payload = await _collect_all_fields(databases)
    return payload.get(UTM_OUTPUT_KEYS[field], [])


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


@router.get("/options", summary="Список всех UTM опций")
async def list_options(databases: Optional[List[str]] = Query(None)):
    return await _collect_all_fields(databases)
