from typing import List, Optional

import asyncpg
import hashlib
from fastapi import APIRouter, Query, Depends
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
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


async def _collect_from_raw_users(session: AsyncSession) -> dict[str, set[str]]:
    result = await session.execute(text("""
        SELECT
            ARRAY(
                SELECT DISTINCT value
                FROM (
                    SELECT utm_source AS value FROM raw_bot_users WHERE utm_source IS NOT NULL AND utm_source <> ''
                    UNION
                    SELECT platform_utm_source AS value FROM raw_bot_users WHERE platform_utm_source IS NOT NULL AND platform_utm_source <> ''
                ) t
            ) AS sources,
            ARRAY(
                SELECT DISTINCT value
                FROM (
                    SELECT utm_campaign AS value FROM raw_bot_users WHERE utm_campaign IS NOT NULL AND utm_campaign <> ''
                    UNION
                    SELECT platform_utm_campaign AS value FROM raw_bot_users WHERE platform_utm_campaign IS NOT NULL AND platform_utm_campaign <> ''
                ) t
            ) AS campaigns,
            ARRAY(
                SELECT DISTINCT value
                FROM (
                    SELECT utm_medium AS value FROM raw_bot_users WHERE utm_medium IS NOT NULL AND utm_medium <> ''
                    UNION
                    SELECT platform_utm_medium AS value FROM raw_bot_users WHERE platform_utm_medium IS NOT NULL AND platform_utm_medium <> ''
                ) t
            ) AS mediums,
            ARRAY(
                SELECT DISTINCT value
                FROM (
                    SELECT utm_content AS value FROM raw_bot_users WHERE utm_content IS NOT NULL AND utm_content <> ''
                    UNION
                    SELECT platform_utm_content AS value FROM raw_bot_users WHERE platform_utm_content IS NOT NULL AND platform_utm_content <> ''
                ) t
            ) AS contents,
            ARRAY(
                SELECT DISTINCT value
                FROM (
                    SELECT utm_term AS value FROM raw_bot_users WHERE utm_term IS NOT NULL AND utm_term <> ''
                    UNION
                    SELECT platform_utm_term AS value FROM raw_bot_users WHERE platform_utm_term IS NOT NULL AND platform_utm_term <> ''
                ) t
            ) AS terms
    """))
    row = result.fetchone()
    if not row:
        return {k: set() for k in ("sources", "campaigns", "mediums", "contents", "terms")}
    return {
        "sources": set(row[0] or []),
        "campaigns": set(row[1] or []),
        "mediums": set(row[2] or []),
        "contents": set(row[3] or []),
        "terms": set(row[4] or []),
    }


async def _collect_from_ph_user_mirror() -> dict[str, set[str]]:
    dsn = settings.lead_db_dsn
    if not dsn:
        return {k: set() for k in ("sources", "campaigns", "mediums", "contents", "terms")}
    dsn_str = str(dsn)
    if dsn_str.startswith("postgresql+asyncpg://"):
        dsn_str = dsn_str.replace("postgresql+asyncpg://", "postgresql://", 1)
    conn = await asyncpg.connect(dsn_str)
    try:
        row = await conn.fetchrow(
            """
            SELECT
                ARRAY(
                    SELECT DISTINCT value
                    FROM (
                        SELECT NULLIF(BTRIM(COALESCE(utm->>'utm_source', utm->>'source', ph_utm->>'utm_source', ph_utm->>'source')), '') AS value
                        FROM ph_user_mirror
                    ) s
                    WHERE value IS NOT NULL
                ) AS sources,
                ARRAY(
                    SELECT DISTINCT value
                    FROM (
                        SELECT NULLIF(BTRIM(COALESCE(utm->>'utm_campaign', utm->>'campaign', ph_utm->>'utm_campaign', ph_utm->>'campaign')), '') AS value
                        FROM ph_user_mirror
                    ) s
                    WHERE value IS NOT NULL
                ) AS campaigns,
                ARRAY(
                    SELECT DISTINCT value
                    FROM (
                        SELECT NULLIF(BTRIM(COALESCE(utm->>'utm_medium', utm->>'medium', ph_utm->>'utm_medium', ph_utm->>'medium')), '') AS value
                        FROM ph_user_mirror
                    ) s
                    WHERE value IS NOT NULL
                ) AS mediums,
                ARRAY(
                    SELECT DISTINCT value
                    FROM (
                        SELECT NULLIF(BTRIM(COALESCE(utm->>'utm_content', utm->>'content', ph_utm->>'utm_content', ph_utm->>'content')), '') AS value
                        FROM ph_user_mirror
                    ) s
                    WHERE value IS NOT NULL
                ) AS contents,
                ARRAY(
                    SELECT DISTINCT value
                    FROM (
                        SELECT NULLIF(BTRIM(COALESCE(utm->>'utm_term', utm->>'term', ph_utm->>'utm_term', ph_utm->>'term')), '') AS value
                        FROM ph_user_mirror
                    ) s
                    WHERE value IS NOT NULL
                ) AS terms
            """
        )
        if not row:
            return {k: set() for k in ("sources", "campaigns", "mediums", "contents", "terms")}
        return {
            "sources": set(row["sources"] or []),
            "campaigns": set(row["campaigns"] or []),
            "mediums": set(row["mediums"] or []),
            "contents": set(row["contents"] or []),
            "terms": set(row["terms"] or []),
        }
    finally:
        await conn.close()


async def _collect_all_fields(databases: Optional[List[str]], session: Optional[AsyncSession] = None) -> dict[str, list[str]]:
    explorer = PostgresExplorer()
    dbs = databases or await explorer.list_bot_databases()
    dbs = sorted({db for db in dbs if db})
    cache = RedisCache()
    signature = ",".join(dbs)
    with_raw = "1" if session is not None else "0"
    cache_key = f"utm:options:v4:{with_raw}:{hashlib.md5(signature.encode('utf-8')).hexdigest()}"
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

    if session is not None:
        raw = await _collect_from_raw_users(session)
        sources.update(raw["sources"])
        campaigns.update(raw["campaigns"])
        mediums.update(raw["mediums"])
        contents.update(raw["contents"])
        terms.update(raw["terms"])
    try:
        ph = await _collect_from_ph_user_mirror()
        sources.update(ph["sources"])
        campaigns.update(ph["campaigns"])
        mediums.update(ph["mediums"])
        contents.update(ph["contents"])
        terms.update(ph["terms"])
    except Exception:
        # Optional source: do not fail UTM options when PokerHub mirror is temporarily unavailable.
        pass

    payload = {
        "sources": sorted(sources),
        "campaigns": sorted(campaigns),
        "mediums": sorted(mediums),
        "contents": sorted(contents),
        "terms": sorted(terms),
    }
    await cache.set_json(cache_key, payload, ttl=settings.cache_ttl_seconds)
    return payload


async def _collect_field(field: str, databases: Optional[List[str]], session: Optional[AsyncSession] = None) -> list[str]:
    payload = await _collect_all_fields(databases, session)
    return payload.get(UTM_OUTPUT_KEYS[field], [])


@router.get("/sources", summary="Список UTM Source")
async def list_sources(databases: Optional[List[str]] = Query(None), session: AsyncSession = Depends(get_db_session)):
    return {"sources": await _collect_field("utm_source", databases, session)}


@router.get("/campaigns", summary="Список UTM Campaign")
async def list_campaigns(databases: Optional[List[str]] = Query(None), session: AsyncSession = Depends(get_db_session)):
    return {"campaigns": await _collect_field("utm_campaign", databases, session)}


@router.get("/mediums", summary="Список UTM Medium")
async def list_mediums(databases: Optional[List[str]] = Query(None), session: AsyncSession = Depends(get_db_session)):
    return {"mediums": await _collect_field("utm_medium", databases, session)}


@router.get("/contents", summary="Список UTM Content")
async def list_contents(databases: Optional[List[str]] = Query(None), session: AsyncSession = Depends(get_db_session)):
    return {"contents": await _collect_field("utm_content", databases, session)}


@router.get("/terms", summary="Список UTM Term")
async def list_terms(databases: Optional[List[str]] = Query(None), session: AsyncSession = Depends(get_db_session)):
    return {"terms": await _collect_field("utm_term", databases, session)}


@router.get("/options", summary="Список всех UTM опций")
async def list_options(databases: Optional[List[str]] = Query(None), session: AsyncSession = Depends(get_db_session)):
    return await _collect_all_fields(databases, session)
