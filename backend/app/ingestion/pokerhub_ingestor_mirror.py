from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any, Optional

from sqlalchemy import and_, func, or_, select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.exc import DBAPIError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.analytics import PhUserMirrorReplica, RawBotUser


class PokerHubIngestorMirrorMixin:
    async def _apply_mirror(self, session: AsyncSession, rows: list[dict[str, Any]]) -> None:
        """Apply ph_user_mirror data keyed by ph_id — one synthetic record per PH user."""
        await self._upsert_mirror_replica_rows(session, rows)
        ph_rows: list[dict[str, Any]] = []
        mirror_updates: dict[int, dict[str, Any]] = {}

        for row in rows:
            try:
                ph_id = int(str(row.get("ph_id")))
            except (TypeError, ValueError):
                continue
            if ph_id <= 0:
                continue

            auth_date = row.get("authorization_date")
            if isinstance(auth_date, str):
                # Strip timezone offset so mirror's local time is stored as-is (naive),
                # keeping week groupings consistent with ph_user_mirror display.
                import re as _re
                auth_date_naive = _re.sub(r'[+-]\d{2}:?\d{2}$', '', auth_date.rstrip('Z')).strip()
                parsed_auth_date = self._parse_datetime(auth_date_naive)
            else:
                parsed_auth_date = None

            utm = self._extract_utm_from_payload(row)

            learn_start_date = self._extract_learn_start_from_mirror(row)
            start_course = self._extract_course_from_mirror(row)
            completed_course_at = self._extract_course_completion_from_mirror(row)
            mirror_updates[ph_id] = {
                "ph_user_id": ph_id,
                "platform_registered_at": parsed_auth_date,
                "learn_start_date": learn_start_date,
                "started_learning": bool(learn_start_date is not None),
                "start_course": start_course,
                "completed_course": bool(completed_course_at),
                "completed_course_at": completed_course_at,
                "utm": utm,
                "referer": self._normalize_mirror_text(row.get("referer")),
                "raw_link": self._normalize_mirror_text(row.get("raw_link")),
                "bot_raw": self._normalize_mirror_text(row.get("bot_raw")),
                "ph_raw": self._normalize_mirror_text(row.get("ph_raw")),
                "last_activity": self._normalize_mirror_text(row.get("last_activity")),
                "ph_group": self._normalize_mirror_text(row.get("group")),
            }

            ph_rows.append(
                {
                    "bot_key": "lead",
                    "tg_user_id": -ph_id,
                    "ph_user_id": ph_id,
                    "username": None,
                    "created_at": parsed_auth_date or datetime.utcnow(),
                    "ingested_at": datetime.utcnow(),
                    "registered_platform": True,
                    "platform_registered_at": parsed_auth_date,
                    "learn_start_date": learn_start_date,
                    "started_learning": bool(learn_start_date is not None),
                    "start_course": start_course,
                    "completed_course": bool(completed_course_at),
                    "completed_course_at": completed_course_at,
                    "converted_to_lead": True,
                    "utm_source": utm.get("utm_source"),
                    "utm_campaign": utm.get("utm_campaign"),
                    "utm_medium": utm.get("utm_medium"),
                    "utm_content": utm.get("utm_content"),
                    "utm_term": utm.get("utm_term"),
                    "platform_utm_source": utm.get("utm_source"),
                    "platform_utm_campaign": utm.get("utm_campaign"),
                    "platform_utm_medium": utm.get("utm_medium"),
                    "platform_utm_content": utm.get("utm_content"),
                    "platform_utm_term": utm.get("utm_term"),
                    "referer": self._normalize_mirror_text(row.get("referer")),
                    "raw_link": self._normalize_mirror_text(row.get("raw_link")),
                    "bot_raw": self._normalize_mirror_text(row.get("bot_raw")),
                    "ph_raw": self._normalize_mirror_text(row.get("ph_raw")),
                    "last_activity": self._normalize_mirror_text(row.get("last_activity")),
                    "ph_group": self._normalize_mirror_text(row.get("group")),
                }
            )

        await self._upsert_ph_only_rows(session, ph_rows)
        await self._apply_mirror_to_existing_rows(session, mirror_updates)
        # Backfill ph_user_id = -tg_user_id for synthetic rows where it's still NULL
        # (covers rows inserted before the ph_user_id column was added)
        await session.execute(
            update(RawBotUser)
            .where(RawBotUser.bot_key == "lead")
            .where(RawBotUser.tg_user_id < 0)
            .where(RawBotUser.ph_user_id.is_(None))
            .values(ph_user_id=(-RawBotUser.tg_user_id))
        )
        await session.execute(
            update(RawBotUser)
            .where(RawBotUser.ph_user_id.is_not(None))
            .values(registered_platform=True)
        )

    async def _upsert_mirror_replica_rows(self, session: AsyncSession, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        payload_rows: list[dict[str, Any]] = []
        now = datetime.utcnow()

        def _json_list(value: Any) -> list[Any]:
            parsed = self._parse_json_value(value)
            return parsed if isinstance(parsed, list) else []

        def _json_dict(value: Any) -> dict[str, Any]:
            parsed = self._parse_json_value(value)
            return parsed if isinstance(parsed, dict) else {}

        for row in rows:
            mirror_id = row.get("id")
            try:
                mirror_id = int(str(mirror_id))
            except (TypeError, ValueError):
                continue
            payload_rows.append(
                {
                    "id": mirror_id,
                    "ph_id": self._normalize_mirror_text(row.get("ph_id")),
                    "username": self._normalize_mirror_text(row.get("username")),
                    "first_name": self._normalize_mirror_text(row.get("first_name")),
                    "last_name": self._normalize_mirror_text(row.get("last_name")),
                    "ph_registration": self._normalize_mirror_text(row.get("ph_registration")),
                    "ph_registration_at": self._normalize_mirror_text(row.get("ph_registration_at")),
                    "authorization_date": self._normalize_mirror_text(row.get("authorization_date")),
                    "last_activity": self._normalize_mirror_text(row.get("last_activity")),
                    "last_visit_date": self._normalize_mirror_text(row.get("last_visit_date")),
                    "is_blocked": row.get("is_blocked"),
                    "utm": _json_dict(row.get("utm")),
                    "ph_utm": _json_dict(row.get("ph_utm")),
                    "referer": self._normalize_mirror_text(row.get("referer")),
                    "raw_link": self._normalize_mirror_text(row.get("raw_link")),
                    "bot_raw": self._normalize_mirror_text(row.get("bot_raw")),
                    "ph_raw": self._normalize_mirror_text(row.get("ph_raw")),
                    "rc": self._normalize_mirror_text(row.get("rc")),
                    "group": self._normalize_mirror_text(row.get("group")),
                    "groups": _json_list(row.get("groups")),
                    "courses": _json_dict(row.get("courses")),
                    "lessons": _json_list(row.get("lessons")),
                    "course_memberships": _json_list(row.get("course_memberships")),
                    "custom_tests": _json_list(row.get("custom_tests")),
                    "source_updated_at": row.get("source_updated_at"),
                    "synced_at": row.get("synced_at") or now,
                }
            )
        if not payload_rows:
            return

        chunk_size = 200
        for i in range(0, len(payload_rows), chunk_size):
            chunk = payload_rows[i : i + chunk_size]
            stmt = pg_insert(PhUserMirrorReplica).values(chunk)
            stmt = stmt.on_conflict_do_update(
                index_elements=[PhUserMirrorReplica.id],
                set_={
                    "ph_id": stmt.excluded.ph_id,
                    "username": stmt.excluded.username,
                    "first_name": stmt.excluded.first_name,
                    "last_name": stmt.excluded.last_name,
                    "ph_registration": stmt.excluded.ph_registration,
                    "ph_registration_at": stmt.excluded.ph_registration_at,
                    "authorization_date": stmt.excluded.authorization_date,
                    "last_activity": stmt.excluded.last_activity,
                    "last_visit_date": stmt.excluded.last_visit_date,
                    "is_blocked": stmt.excluded.is_blocked,
                    "utm": stmt.excluded.utm,
                    "ph_utm": stmt.excluded.ph_utm,
                    "referer": stmt.excluded.referer,
                    "raw_link": stmt.excluded.raw_link,
                    "bot_raw": stmt.excluded.bot_raw,
                    "ph_raw": stmt.excluded.ph_raw,
                    "rc": stmt.excluded.rc,
                    "group": getattr(stmt.excluded, "group"),
                    "groups": stmt.excluded.groups,
                    "courses": stmt.excluded.courses,
                    "lessons": stmt.excluded.lessons,
                    "course_memberships": stmt.excluded.course_memberships,
                    "custom_tests": stmt.excluded.custom_tests,
                    "source_updated_at": func.coalesce(stmt.excluded.source_updated_at, PhUserMirrorReplica.source_updated_at),
                    "synced_at": stmt.excluded.synced_at,
                },
            )
            await session.execute(stmt)
        await session.commit()

    async def _apply_mirror_to_existing_rows(
        self,
        session: AsyncSession,
        mirror_updates: dict[int, dict[str, Any]],
    ) -> None:
        if not mirror_updates:
            return
        chunk_size = 100
        processed = 0
        for ph_id, payload in mirror_updates.items():
            await self._apply_single_mirror_update(session, ph_id, payload)
            processed += 1
            if processed % chunk_size == 0:
                await session.commit()
        if processed % chunk_size:
            await session.commit()

    async def _apply_single_mirror_update(
        self,
        session: AsyncSession,
        ph_id: int,
        payload: dict[str, Any],
    ) -> None:
        for attempt in range(8):
            try:
                match_condition = or_(
                    RawBotUser.ph_user_id == ph_id,
                    and_(
                        RawBotUser.bot_key == "lead",
                        RawBotUser.tg_user_id == ph_id,
                    ),
                )
                base_values = {
                    "registered_platform": True,
                    "ph_user_id": ph_id,
                    "ingested_at": datetime.utcnow(),
                }
                if payload.get("platform_registered_at") is not None:
                    base_values["platform_registered_at"] = payload["platform_registered_at"]
                if payload.get("learn_start_date") is not None:
                    base_values["learn_start_date"] = payload["learn_start_date"]
                if payload.get("started_learning"):
                    base_values["started_learning"] = True
                if payload.get("start_course"):
                    base_values["start_course"] = payload["start_course"]
                if payload.get("completed_course_at") is not None:
                    base_values["completed_course"] = True
                    base_values["completed_course_at"] = payload["completed_course_at"]
                for field in ("referer", "raw_link", "bot_raw", "ph_raw", "last_activity", "ph_group"):
                    if payload.get(field):
                        base_values[field] = payload[field]
                await session.execute(
                    update(RawBotUser)
                    .where(match_condition)
                    .values(**base_values)
                )

                utm = payload.get("utm") or {}
                for key in ("utm_source", "utm_campaign", "utm_medium", "utm_content", "utm_term"):
                    value = utm.get(key)
                    if not value:
                        continue
                    await session.execute(
                        update(RawBotUser)
                        .where(match_condition)
                        .where(or_(getattr(RawBotUser, f"platform_{key}").is_(None), func.btrim(getattr(RawBotUser, f"platform_{key}")) == ""))
                        .values(**{f"platform_{key}": value, "ingested_at": datetime.utcnow()})
                    )
                    await session.execute(
                        update(RawBotUser)
                        .where(match_condition)
                        .where(or_(getattr(RawBotUser, key).is_(None), func.btrim(getattr(RawBotUser, key)) == ""))
                        .values(**{key: value, "ingested_at": datetime.utcnow()})
                    )
                return
            except DBAPIError as exc:
                if not self._is_deadlock(exc) or attempt >= 7:
                    raise
                await session.rollback()
                delay = min(3.0, 0.2 * (2 ** attempt))
                self._logger.warning(
                    "PokerHub mirror enrich deadlock; retrying ph_id=%s attempt=%s delay=%.1fs",
                    ph_id,
                    attempt + 1,
                    delay,
                )
                await asyncio.sleep(delay)

    async def _upsert_ph_only_rows(self, session: AsyncSession, rows: list[dict[str, Any]]) -> None:
        if not rows:
            return
        chunk_size = 50
        for i in range(0, len(rows), chunk_size):
            chunk = rows[i : i + chunk_size]
            for attempt in range(8):
                stmt = pg_insert(RawBotUser).values(chunk)

                def keep_existing_non_empty(column, incoming):
                    return func.coalesce(func.nullif(func.btrim(column), ""), incoming)

                stmt = stmt.on_conflict_do_update(
                    index_elements=[RawBotUser.bot_key, RawBotUser.tg_user_id],
                    set_={
                        "created_at": func.coalesce(RawBotUser.created_at, stmt.excluded.created_at),
                        "ingested_at": stmt.excluded.ingested_at,
                        "ph_user_id": stmt.excluded.ph_user_id,
                        "registered_platform": True,
                        "platform_registered_at": stmt.excluded.platform_registered_at,
                        "learn_start_date": func.coalesce(
                            RawBotUser.learn_start_date,
                            stmt.excluded.learn_start_date,
                        ),
                        "started_learning": RawBotUser.started_learning.is_(True) | stmt.excluded.started_learning,
                        "start_course": func.coalesce(
                            RawBotUser.start_course,
                            stmt.excluded.start_course,
                        ),
                        "completed_course": RawBotUser.completed_course.is_(True) | stmt.excluded.completed_course,
                        "completed_course_at": func.coalesce(
                            RawBotUser.completed_course_at,
                            stmt.excluded.completed_course_at,
                        ),
                        "converted_to_lead": True,
                        "utm_source": keep_existing_non_empty(RawBotUser.utm_source, stmt.excluded.utm_source),
                        "utm_campaign": keep_existing_non_empty(RawBotUser.utm_campaign, stmt.excluded.utm_campaign),
                        "utm_medium": keep_existing_non_empty(RawBotUser.utm_medium, stmt.excluded.utm_medium),
                        "utm_content": keep_existing_non_empty(RawBotUser.utm_content, stmt.excluded.utm_content),
                        "utm_term": keep_existing_non_empty(RawBotUser.utm_term, stmt.excluded.utm_term),
                        "platform_utm_source": keep_existing_non_empty(
                            RawBotUser.platform_utm_source,
                            stmt.excluded.platform_utm_source,
                        ),
                        "platform_utm_campaign": keep_existing_non_empty(
                            RawBotUser.platform_utm_campaign,
                            stmt.excluded.platform_utm_campaign,
                        ),
                        "platform_utm_medium": keep_existing_non_empty(
                            RawBotUser.platform_utm_medium,
                            stmt.excluded.platform_utm_medium,
                        ),
                        "platform_utm_content": keep_existing_non_empty(
                            RawBotUser.platform_utm_content,
                            stmt.excluded.platform_utm_content,
                        ),
                        "platform_utm_term": keep_existing_non_empty(
                            RawBotUser.platform_utm_term,
                            stmt.excluded.platform_utm_term,
                        ),
                    },
                )
                try:
                    await session.execute(stmt)
                    await session.commit()
                    break
                except DBAPIError as exc:
                    if not self._is_deadlock(exc) or attempt >= 7:
                        raise
                    await session.rollback()
                    delay = min(5.0, 0.4 * (2 ** attempt))
                    self._logger.warning(
                        "PokerHub mirror upsert deadlock; retrying chunk=%s-%s attempt=%s delay=%.1fs",
                        i,
                        i + len(chunk),
                        attempt + 1,
                        delay,
                    )
                    await asyncio.sleep(delay)
