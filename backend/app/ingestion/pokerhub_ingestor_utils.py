from __future__ import annotations

import json
import logging
import os
import re
from datetime import datetime
from typing import Any, Optional
from urllib.parse import parse_qs, parse_qsl, unquote, urlparse

import asyncpg
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import DBAPIError

from app.core.config import settings
from app.services.utm_normalization import normalize_utm_key, normalize_utm_value

logger = logging.getLogger(__name__)


class PokerHubIngestorUtilsMixin:
    def __init__(self):
        self._logger = logging.getLogger("pokerhub_ingestor")
        try:
            import asyncpg as _asyncpg  # type: ignore
        except Exception:  # pragma: no cover
            _asyncpg = None
        self._asyncpg = _asyncpg

    def _is_deadlock(self, exc: Exception) -> bool:
        if not isinstance(exc, DBAPIError):
            return False
        orig = exc.orig
        if orig is None:
            return False
        if self._asyncpg is not None and isinstance(orig, self._asyncpg.exceptions.DeadlockDetectedError):
            return True
        return "DeadlockDetectedError" in str(orig) or "deadlock detected" in str(orig).lower()

    @staticmethod
    def _normalize_utm_struct(utm_obj: Any) -> dict[str, str]:
        if isinstance(utm_obj, str):
            try:
                utm_obj = json.loads(utm_obj)
            except json.JSONDecodeError:
                return {}
        if not isinstance(utm_obj, dict):
            return {}
        result: dict[str, str] = {}
        for raw_key, raw_value in utm_obj.items():
            target_key = normalize_utm_key(raw_key)
            if not target_key:
                continue
            value = normalize_utm_value(raw_value)
            if not value:
                continue
            result[target_key] = value
        return result

    @staticmethod
    def _parse_utm_from_link(raw_link: str) -> dict[str, str]:
        if not raw_link or not isinstance(raw_link, str):
            return {}
        result: dict[str, str] = {}
        try:
            candidates = [raw_link, unquote(raw_link)]
            for candidate in candidates:
                parsed = urlparse(candidate)
                pairs = parse_qsl(parsed.query or "", keep_blank_values=False)
                if parsed.fragment and "=" in parsed.fragment:
                    pairs.extend(parse_qsl(parsed.fragment, keep_blank_values=False))
                for raw_key, raw_value in pairs:
                    key = normalize_utm_key(raw_key)
                    if not key:
                        continue
                    value = normalize_utm_value(raw_value)
                    if value and key not in result:
                        result[key] = value
        except Exception:
            return {}
        return result

    @staticmethod
    def _normalize_mirror_text(value: Any) -> str | None:
        if value is None:
            return None
        if isinstance(value, bytes):
            value = value.decode("utf-8", errors="ignore")
        text_value = str(value).strip()
        if not text_value or text_value.lower() in {"null", "none"}:
            return None
        return text_value

    async def ingest(self, session: AsyncSession) -> None:
        if not settings.lead_db_dsn:
            return
        dsn = str(settings.lead_db_dsn)
        if dsn.startswith("postgresql+asyncpg://"):
            dsn = dsn.replace("postgresql+asyncpg://", "postgresql://", 1)
        mirror_rows = await self._fetch_ph_user_mirror(dsn)
        if mirror_rows:
            await self._apply_mirror(session, mirror_rows)

    async def _fetch_ph_user_mirror(self, dsn: str) -> list[dict[str, Any]]:
        """Fetch all users from ph_user_mirror — the complete pokerhub user list."""
        conn = await asyncpg.connect(dsn)
        try:
            rows = await conn.fetch(
                """
                SELECT
                    id,
                    ph_id,
                    username,
                    first_name,
                    last_name,
                    ph_registration,
                    ph_registration_at,
                    authorization_date,
                    last_activity,
                    last_visit_date,
                    is_blocked,
                    courses,
                    lessons,
                    groups,
                    course_memberships,
                    custom_tests,
                    utm,
                    ph_utm,
                    referer,
                    raw_link,
                    bot_raw,
                    ph_raw,
                    rc,
                    "group",
                    synced_at,
                    source_updated_at
                FROM ph_user_mirror
                """
            )
            result: list[dict[str, Any]] = []
            for row in rows:
                result.append({
                    "id": row["id"],
                    "ph_id": row["ph_id"],
                    "username": row["username"],
                    "first_name": row["first_name"],
                    "last_name": row["last_name"],
                    "ph_registration": row["ph_registration"],
                    "ph_registration_at": row["ph_registration_at"],
                    "authorization_date": row["authorization_date"],
                    "last_activity": row["last_activity"],
                    "last_visit_date": row["last_visit_date"],
                    "is_blocked": row["is_blocked"],
                    "courses": row["courses"],
                    "lessons": row["lessons"],
                    "groups": row["groups"],
                    "course_memberships": row["course_memberships"],
                    "custom_tests": row["custom_tests"],
                    "utm": row["utm"],
                    "ph_utm": row["ph_utm"],
                    "referer": row["referer"],
                    "raw_link": row["raw_link"],
                    "bot_raw": row["bot_raw"],
                    "ph_raw": row["ph_raw"],
                    "rc": row["rc"],
                    "group": row["group"],
                    "synced_at": row["synced_at"],
                    "source_updated_at": row["source_updated_at"],
                })
            return result
        finally:
            await conn.close()

    def _extract_utm_from_payload(self, payload: dict[str, Any]) -> dict[str, str]:
        """Extract UTM params from pokerhub payload.

        Merges structured 'utm' object (primary) with params parsed from raw
        link fields (referer, raw_link, bot_raw, ph_raw). Structured object wins
        on conflict; raw links fill in any fields missing from the object.
        """
        utm: dict[str, str] = {}

        for utm_field_name in ("utm", "ph_utm"):
            utm.update(self._normalize_utm_struct(payload.get(utm_field_name)))

        for field in ("referer", "raw_link", "bot_raw", "ph_raw"):
            raw = payload.get(field)
            if not raw or not isinstance(raw, str):
                continue
            parsed_link_utm = self._parse_utm_from_link(raw)
            for key, value in parsed_link_utm.items():
                if key not in utm and value:
                    utm[key] = value

        return utm
