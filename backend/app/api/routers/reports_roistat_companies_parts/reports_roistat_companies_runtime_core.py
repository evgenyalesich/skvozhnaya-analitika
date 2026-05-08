# Основная логика Roistat-отчёта по рекламным компаниям.
# Принимает до 8 фильтров (bots/companies/UTM) + 3 режима дат (event/first_touch/last_touch) + 2 display_mode (weekly/cohort).
# Строит 3 SQL-запроса (main/bot/week_totals) через reports_roistat_companies_runtime_queries,
# затем передаёт результаты в build_roistat_companies_payload (postprocess).
# Кеш: ключ по всем параметрам + stale-ключ (TTL 7× primary).

from datetime import date
import asyncio
from typing import Any, List, Optional
import json
import os

from fastapi import Depends, Query

from app.api.dependencies import get_db_session
from app.api.routers.reports_roistat_companies_postprocess import build_roistat_companies_payload
from app.api.routers.reports_roistat_companies_runtime_queries import (
    build_bot_query,
    build_main_query,
    build_week_totals_query,
)
from app.core.config import settings
from app.core.redis_client import RedisCache
from app.services.report_bot_scope import normalized_excluded_bot_keys

_HOT_PROFILES_KEY = "reports:roistat_weekly:companies:hot_profiles:v1"
_HOT_PROFILES_MAX = 30


async def _remember_hot_profile(cache: RedisCache, profile: dict[str, Any]) -> None:
    try:
        existing = await cache.get_json(_HOT_PROFILES_KEY)
        profiles = existing if isinstance(existing, list) else []
        canonical = json.dumps(profile, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        next_profiles: list[dict[str, Any]] = [profile]
        for item in profiles:
            if not isinstance(item, dict):
                continue
            item_canonical = json.dumps(item, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
            if item_canonical != canonical:
                next_profiles.append(item)
            if len(next_profiles) >= _HOT_PROFILES_MAX:
                break
        await cache.set_json(_HOT_PROFILES_KEY, next_profiles, ttl=14 * 24 * 60 * 60)
    except Exception:
        # Hot-profile storage is best-effort and must never break report response.
        return


# ===== Roistat companies weekly logic =====
async def roistat_weekly_by_company(
    event_start: Optional[date] = Query(None),
    event_end: Optional[date] = Query(None),
    mode: str = Query("event", pattern="^(event|first_touch|last_touch)$"),
    first_touch_start: Optional[date] = Query(None),
    first_touch_end: Optional[date] = Query(None),
    display_mode: str = Query("weekly", pattern="^(weekly|cohort)$"),
    bots: Optional[List[str]] = Query(None),
    advertising_companies: Optional[List[str]] = Query(None),
    utm_source: Optional[List[str]] = Query(None),
    utm_campaign: Optional[List[str]] = Query(None),
    utm_medium: Optional[List[str]] = Query(None),
    utm_content: Optional[List[str]] = Query(None),
    utm_term: Optional[List[str]] = Query(None),
    session=Depends(get_db_session),
) -> dict[str, Any]:
    from sqlalchemy import text as sa_text

    cache = RedisCache()
    sync_state = await cache.get_json_many(
        ["sync:last_ingestion_success", "sync:last_sm_success", "sync:last_pokerhub_success"]
    )

    def _sync_ts(payload: Any) -> int:
        if isinstance(payload, dict):
            try:
                return int(payload.get("ts") or 0)
            except Exception:
                return 0
        return 0

    data_version = {
        "ingestion_ts": _sync_ts(sync_state.get("sync:last_ingestion_success")),
        "sm_ts": _sync_ts(sync_state.get("sync:last_sm_success")),
        "pokerhub_ts": _sync_ts(sync_state.get("sync:last_pokerhub_success")),
    }

    cache_payload = {
        "event_start": event_start.isoformat() if event_start else None,
        "event_end": event_end.isoformat() if event_end else None,
        "mode": mode,
        "first_touch_start": first_touch_start.isoformat() if first_touch_start else None,
        "first_touch_end": first_touch_end.isoformat() if first_touch_end else None,
        "display_mode": display_mode,
        "bots": sorted(bots or []),
        "advertising_companies": sorted(advertising_companies or []),
        "utm_source": sorted(utm_source or []),
        "utm_campaign": sorted(utm_campaign or []),
        "utm_medium": sorted(utm_medium or []),
        "utm_content": sorted(utm_content or []),
        "utm_term": sorted(utm_term or []),
        "data_version": data_version,
    }
    cache_suffix = json.dumps(cache_payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    cache_key = f"reports:roistat_weekly:companies:v29:{cache_suffix}"
    stale_key = f"{cache_key}:stale"
    lock_key = f"{cache_key}:lock"
    await _remember_hot_profile(cache, cache_payload)

    cached_map = await cache.get_json_many([cache_key, stale_key])
    cached = cached_map.get(cache_key)
    if cached is not None:
        return cached

    stale = cached_map.get(stale_key)
    if stale is not None:
        await cache.set_json(cache_key, stale, ttl=min(settings.weekly_cache_ttl_seconds, 300))
        return stale

    got_lock = await cache.set_if_not_exists(lock_key, "1", ttl=120)
    if not got_lock:
        await asyncio.sleep(0.5)
        cached_map_retry = await cache.get_json_many([cache_key, stale_key])
        ready = cached_map_retry.get(cache_key) or cached_map_retry.get(stale_key)
        if ready is not None:
            return ready

    normalized_company_sql = """
        CASE
            WHEN advertising_company IS NULL
              OR BTRIM(advertising_company) = ''
              OR LOWER(BTRIM(advertising_company)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки')
            THEN 'Без категории'
            ELSE BTRIM(advertising_company)
        END
    """

    # Resolve cohort date bounds
    ft_start = first_touch_start or event_start
    ft_end = first_touch_end or event_end

    params: dict[str, Any] = {
        "start": event_start,
        "end": event_end,
        "ft_start": ft_start,
        "ft_end": ft_end,
        "mode": mode,
        "use_bot_filter": bool(bots),
        "channel_id": os.environ.get("TELEGRAM_CHANNEL_ID"),
        "community_id": os.environ.get("TELEGRAM_COMMUNITY_ID"),
        "excluded_bot_keys": normalized_excluded_bot_keys(),
    }

    def _normalize_filter_values(values: Optional[List[str]]) -> list[str]:
        if not values:
            return []
        return [value.strip().lower() for value in values if isinstance(value, str) and value.strip()]

    def build_row_filters(alias: str) -> str:
        conditions: list[str] = []
        normalized_company_expr = normalized_company_sql.replace("advertising_company", f"{alias}.advertising_company")
        if bots:
            conditions.append(f"{alias}.bot_key = ANY(:filter_bots)")
            params["filter_bots"] = bots
        if advertising_companies:
            conditions.append(f"{normalized_company_expr} = ANY(:filter_advertising_companies)")
            params["filter_advertising_companies"] = advertising_companies

        normalized_utm_campaign = _normalize_filter_values(utm_campaign)
        if normalized_utm_campaign:
            conditions.append(
                f"""(
                    LOWER(TRIM(COALESCE({alias}.utm_campaign, ''))) = ANY(:filter_utm_campaign)
                    OR LOWER(TRIM(COALESCE({alias}.platform_utm_campaign, ''))) = ANY(:filter_utm_campaign)
                )"""
            )
            params["filter_utm_campaign"] = normalized_utm_campaign

        normalized_utm_source = _normalize_filter_values(utm_source)
        if normalized_utm_source:
            conditions.append(
                f"""(
                    LOWER(TRIM(COALESCE({alias}.utm_source, ''))) = ANY(:filter_utm_source)
                    OR LOWER(TRIM(COALESCE({alias}.platform_utm_source, ''))) = ANY(:filter_utm_source)
                )"""
            )
            params["filter_utm_source"] = normalized_utm_source

        normalized_utm_medium = _normalize_filter_values(utm_medium)
        if normalized_utm_medium:
            conditions.append(
                f"""(
                    LOWER(TRIM(COALESCE({alias}.utm_medium, ''))) = ANY(:filter_utm_medium)
                    OR LOWER(TRIM(COALESCE({alias}.platform_utm_medium, ''))) = ANY(:filter_utm_medium)
                )"""
            )
            params["filter_utm_medium"] = normalized_utm_medium

        normalized_utm_content = _normalize_filter_values(utm_content)
        if normalized_utm_content:
            conditions.append(
                f"""(
                    LOWER(TRIM(COALESCE({alias}.utm_content, ''))) = ANY(:filter_utm_content)
                    OR LOWER(TRIM(COALESCE({alias}.platform_utm_content, ''))) = ANY(:filter_utm_content)
                )"""
            )
            params["filter_utm_content"] = normalized_utm_content

        normalized_utm_term = _normalize_filter_values(utm_term)
        if normalized_utm_term:
            conditions.append(
                f"""(
                    LOWER(TRIM(COALESCE({alias}.utm_term, ''))) = ANY(:filter_utm_term)
                    OR LOWER(TRIM(COALESCE({alias}.platform_utm_term, ''))) = ANY(:filter_utm_term)
                )"""
            )
            params["filter_utm_term"] = normalized_utm_term

        return "".join(f"\n              AND {condition}" for condition in conditions)

    utm_filter_sql = build_row_filters("r")
    cohort_filter_sql = build_row_filters("raw_bot_users")
    utm_users_filter_sql = build_row_filters("u")

    has_utm_filter = bool(
        _normalize_filter_values(utm_source)
        or _normalize_filter_values(utm_campaign)
        or _normalize_filter_values(utm_medium)
        or _normalize_filter_values(utm_content)
        or _normalize_filter_values(utm_term)
    )

    # In cohort mode, UTM params live on advertising/source records, not on lead
    # records. Pre-select user IDs that have any record matching the UTM filter,
    # then join against lead_rows instead of filtering lead_rows directly.
    if has_utm_filter:
        cohort_utm_users_cte = f"""
        utm_users AS (
            SELECT DISTINCT u.tg_user_id
            FROM raw_bot_users u
            WHERE u.created_at IS NOT NULL
              AND LOWER(TRIM(COALESCE(u.bot_key, ''))) <> ALL(:excluded_bot_keys)
              {utm_users_filter_sql}
        ),"""
        cohort_lead_utm_filter = "\n              AND r.tg_user_id IN (SELECT tg_user_id FROM utm_users)"
    else:
        cohort_utm_users_cte = ""
        cohort_lead_utm_filter = ""

    budget_filter_sql = ""
    if advertising_companies:
        budget_filter_sql += "\n                AND CASE\n                    WHEN campaign IS NULL\n                      OR BTRIM(campaign) = ''\n                      OR LOWER(BTRIM(campaign)) IN ('-', '—', '(none)', 'none', 'null', 'нет метки')\n                    THEN 'Без категории'\n                    ELSE BTRIM(campaign)\n                END = ANY(:filter_advertising_companies)"
    if bots:
        budget_filter_sql += "\n                AND COALESCE(NULLIF(BTRIM(bot_key), ''), 'Без бота') = ANY(:filter_bots)"

    if mode == "first_touch":
        first_touch_bot_filter_having = "TRUE"
        if bots:
            first_touch_bot_filter_having = "BOOL_OR(r.first_touch_bot = ANY(:filter_bots))"
        cohort_cte = f"""
        cohort AS (
            SELECT r.tg_user_id
            FROM raw_bot_users r
            WHERE r.tg_user_id > 0
              AND r.first_touch_bot IS NOT NULL
              AND BTRIM(r.first_touch_bot) <> ''
              AND LOWER(BTRIM(r.first_touch_bot)) <> 'нет метки'
              AND LOWER(BTRIM(r.first_touch_bot)) <> ALL(:excluded_bot_keys)
            GROUP BY r.tg_user_id
            HAVING (
                CAST(:ft_start AS date) IS NULL
                OR MIN((CASE WHEN r.bot_key = r.first_touch_bot THEN r.created_at END) AT TIME ZONE 'Europe/Moscow')::date >= CAST(:ft_start AS date)
            )
               AND (
                CAST(:ft_end AS date) IS NULL
                OR MIN((CASE WHEN r.bot_key = r.first_touch_bot THEN r.created_at END) AT TIME ZONE 'Europe/Moscow')::date <= CAST(:ft_end AS date)
            )
               AND ({first_touch_bot_filter_having})
        ),"""
    elif mode == "last_touch":
        last_touch_bot_filter_having = "TRUE"
        if bots:
            last_touch_bot_filter_having = "BOOL_OR(r.last_touch_bot = ANY(:filter_bots))"
        cohort_cte = f"""
        cohort AS (
            SELECT r.tg_user_id
            FROM (
                SELECT
                    ru.tg_user_id,
                    MIN(ru.platform_registered_at) AS first_platform_registered_at
                FROM raw_bot_users ru
                WHERE ru.ph_user_id IS NOT NULL
                  AND ru.platform_registered_at IS NOT NULL
                GROUP BY ru.tg_user_id
            ) pu
            JOIN raw_bot_users r ON r.tg_user_id = pu.tg_user_id
            WHERE r.tg_user_id > 0
              AND r.last_touch_bot IS NOT NULL
              AND BTRIM(r.last_touch_bot) <> ''
              AND LOWER(BTRIM(r.last_touch_bot)) <> 'нет метки'
              AND LOWER(BTRIM(r.last_touch_bot)) <> ALL(:excluded_bot_keys)
            GROUP BY r.tg_user_id
            HAVING (
                CAST(:ft_start AS date) IS NULL
                OR MAX(
                    (
                        CASE
                            WHEN r.bot_key = r.last_touch_bot AND r.created_at <= pu.first_platform_registered_at
                            THEN r.created_at
                        END
                    ) AT TIME ZONE 'Europe/Moscow'
                )::date >= CAST(:ft_start AS date)
            )
               AND (
                CAST(:ft_end AS date) IS NULL
                OR MAX(
                    (
                        CASE
                            WHEN r.bot_key = r.last_touch_bot AND r.created_at <= pu.first_platform_registered_at
                            THEN r.created_at
                        END
                    ) AT TIME ZONE 'Europe/Moscow'
                )::date <= CAST(:ft_end AS date)
            )
               AND ({last_touch_bot_filter_having})
        ),"""
    else:
        cohort_cte = ""

    cohort_join = "JOIN cohort c ON c.tg_user_id = r.tg_user_id" if mode in ("first_touch", "last_touch") else ""
    event_date_filter = "" if mode in ("first_touch", "last_touch") else """
              AND (CAST(:start AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date >= CAST(:start AS date))
              AND (CAST(:end AS date) IS NULL OR (r.created_at AT TIME ZONE 'Europe/Moscow')::date <= CAST(:end AS date))"""
    cohort_all_starts_join = "JOIN cohort c ON c.tg_user_id = r.tg_user_id" if mode in ("first_touch", "last_touch") else ""

    lc_company_sql = normalized_company_sql.replace("advertising_company", "r.advertising_company")
    source_touch_filter_sql = build_row_filters("src")

    query = build_main_query(
        sa_text=sa_text,
        display_mode=display_mode,
        cohort_cte=cohort_cte,
        cohort_join=cohort_join,
        cohort_utm_users_cte=cohort_utm_users_cte,
        cohort_lead_utm_filter=cohort_lead_utm_filter,
        event_date_filter=event_date_filter,
        cohort_all_starts_join=cohort_all_starts_join,
        utm_filter_sql=utm_filter_sql,
        normalized_company_sql=normalized_company_sql,
        source_touch_filter_sql=source_touch_filter_sql,
        budget_filter_sql=budget_filter_sql,
        lc_company_sql=lc_company_sql,
    )
    try:
        result = await session.execute(query, params)
        db_rows = result.fetchall()

        db_week_totals_rows = []
        if display_mode == "weekly":
            week_totals_query = build_week_totals_query(
                sa_text=sa_text,
                cohort_cte=cohort_cte,
                cohort_join=cohort_join,
                utm_filter_sql=utm_filter_sql,
                budget_filter_sql=budget_filter_sql,
            )
            week_totals_result = await session.execute(week_totals_query, params)
            db_week_totals_rows = week_totals_result.fetchall()

        bot_query = build_bot_query(
            sa_text=sa_text,
            display_mode=display_mode,
            cohort_cte=cohort_cte,
            cohort_join=cohort_join,
            event_date_filter=event_date_filter,
            cohort_all_starts_join=cohort_all_starts_join,
            utm_filter_sql=utm_filter_sql,
            normalized_company_sql=normalized_company_sql,
            source_touch_filter_sql=source_touch_filter_sql,
            budget_filter_sql=budget_filter_sql,
            lc_company_sql=lc_company_sql,
        )
        bot_result = await session.execute(bot_query, params)
        db_bot_rows = bot_result.fetchall()

        return await build_roistat_companies_payload(
            session=session,
            sa_text=sa_text,
            params=params,
            db_rows=db_rows,
            db_bot_rows=db_bot_rows,
            db_week_totals_rows=db_week_totals_rows,
            normalized_company_sql=normalized_company_sql,
            source_touch_filter_sql=source_touch_filter_sql,
            display_mode=display_mode,
            cohort_cte=cohort_cte,
            cohort_join=cohort_join,
            utm_filter_sql=utm_filter_sql,
            cache=cache,
            cache_key=cache_key,
            stale_key=stale_key,
            settings=settings,
        )
    finally:
        if got_lock:
            await cache.delete(lock_key)
