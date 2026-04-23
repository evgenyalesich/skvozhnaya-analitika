#!/usr/bin/env python3
"""
Cleanup wrong lead TG IDs in analytics.raw_bot_users.

Problem:
- Historical ingestion for `lead` used COALESCE(users.telegram_id, users.id).
- When telegram_id was NULL, internal users.id ended up in raw_bot_users.tg_user_id.

This script fixes that safely:
1) Unambiguous remap:
   raw.tg_user_id == lead.users.id AND lead.users.telegram_id IS NOT NULL
   -> remap raw.tg_user_id to real lead.users.telegram_id
2) Ambiguous records (telegram_id IS NULL):
   - reported by default (no destructive changes)
   - optional conversion to "direct source" synthetic IDs (negative user id)

Usage:
  export ANALYTICS_DB_DSN=...
  export LEAD_DB_DSN=...
  python3 backend/scripts/cleanup_lead_tg_mapping.py --dry-run
  python3 backend/scripts/cleanup_lead_tg_mapping.py --apply
  python3 backend/scripts/cleanup_lead_tg_mapping.py --apply --convert-no-tg-to-direct
"""

from __future__ import annotations

import argparse
import asyncio
import os
from dataclasses import dataclass
from typing import Any

import asyncpg


def _normalize_dsn(value: str | None) -> str | None:
    if not value:
        return None
    value = value.strip()
    if value.startswith("postgresql+asyncpg://"):
        return value.replace("postgresql+asyncpg://", "postgresql://", 1)
    return value


@dataclass
class Candidate:
    raw_id: int
    old_tg: int
    lead_user_id: int
    lead_telegram_id: int | None
    lead_username: str | None
    has_funnel: bool
    ph_user_id: int | None


async def _load_candidates(analytics: asyncpg.Connection, lead: asyncpg.Connection) -> list[Candidate]:
    lead_rows = await lead.fetch(
        """
        WITH funnel_users AS (
            SELECT DISTINCT user_id FROM funnel_history
            UNION
            SELECT DISTINCT user_id FROM user_funnel
        )
        SELECT
            u.id AS user_id,
            u.telegram_id AS telegram_id,
            u.username AS username,
            (fu.user_id IS NOT NULL) AS has_funnel
        FROM users u
        LEFT JOIN funnel_users fu ON fu.user_id = u.id
        """
    )
    by_user_id: dict[int, dict[str, Any]] = {}
    for row in lead_rows:
        by_user_id[int(row["user_id"])] = {
            "telegram_id": int(row["telegram_id"]) if row["telegram_id"] is not None else None,
            "username": row["username"],
            "has_funnel": bool(row["has_funnel"]),
        }

    raw_rows = await analytics.fetch(
        """
        SELECT id, tg_user_id, ph_user_id
        FROM raw_bot_users
        WHERE lower(trim(coalesce(bot_key, ''))) = 'lead'
          AND tg_user_id > 0
        """
    )
    candidates: list[Candidate] = []
    for row in raw_rows:
        tg = int(row["tg_user_id"])
        lead_u = by_user_id.get(tg)
        if not lead_u:
            continue
        candidates.append(
            Candidate(
                raw_id=int(row["id"]),
                old_tg=tg,
                lead_user_id=tg,
                lead_telegram_id=lead_u["telegram_id"],
                lead_username=lead_u["username"],
                has_funnel=lead_u["has_funnel"],
                ph_user_id=int(row["ph_user_id"]) if row["ph_user_id"] is not None else None,
            )
        )
    return candidates


async def _merge_and_move_row(
    conn: asyncpg.Connection,
    *,
    source_id: int,
    old_tg: int,
    new_tg: int,
    desired_ph_user_id: int | None = None,
) -> None:
    target = await conn.fetchrow(
        """
        SELECT id
        FROM raw_bot_users
        WHERE bot_key = 'lead' AND tg_user_id = $1
        LIMIT 1
        """,
        new_tg,
    )
    if target and int(target["id"]) != source_id:
        target_id = int(target["id"])
        # Merge essential payload fields into existing target row before deleting source.
        await conn.execute(
            """
            UPDATE raw_bot_users t
            SET
                username = COALESCE(NULLIF(BTRIM(t.username), ''), s.username),
                utm_source = COALESCE(NULLIF(BTRIM(t.utm_source), ''), s.utm_source),
                utm_campaign = COALESCE(NULLIF(BTRIM(t.utm_campaign), ''), s.utm_campaign),
                utm_medium = COALESCE(NULLIF(BTRIM(t.utm_medium), ''), s.utm_medium),
                utm_content = COALESCE(NULLIF(BTRIM(t.utm_content), ''), s.utm_content),
                utm_term = COALESCE(NULLIF(BTRIM(t.utm_term), ''), s.utm_term),
                platform_utm_source = COALESCE(NULLIF(BTRIM(t.platform_utm_source), ''), s.platform_utm_source),
                platform_utm_campaign = COALESCE(NULLIF(BTRIM(t.platform_utm_campaign), ''), s.platform_utm_campaign),
                platform_utm_medium = COALESCE(NULLIF(BTRIM(t.platform_utm_medium), ''), s.platform_utm_medium),
                platform_utm_content = COALESCE(NULLIF(BTRIM(t.platform_utm_content), ''), s.platform_utm_content),
                platform_utm_term = COALESCE(NULLIF(BTRIM(t.platform_utm_term), ''), s.platform_utm_term),
                converted_to_lead = (t.converted_to_lead IS TRUE OR s.converted_to_lead IS TRUE),
                registered_platform = (t.registered_platform IS TRUE OR s.registered_platform IS TRUE),
                started_learning = (t.started_learning IS TRUE OR s.started_learning IS TRUE),
                completed_course = (t.completed_course IS TRUE OR s.completed_course IS TRUE),
                ph_user_id = COALESCE(t.ph_user_id, s.ph_user_id, $3),
                created_at = LEAST(t.created_at, s.created_at),
                ingested_at = GREATEST(t.ingested_at, s.ingested_at)
            FROM raw_bot_users s
            WHERE t.id = $1 AND s.id = $2
            """,
            target_id,
            source_id,
            desired_ph_user_id,
        )
        await conn.execute("DELETE FROM raw_bot_users WHERE id = $1", source_id)
        return

    await conn.execute(
        """
        UPDATE raw_bot_users
        SET tg_user_id = $1,
            ph_user_id = COALESCE(ph_user_id, $2)
        WHERE id = $3 AND tg_user_id = $4
        """,
        new_tg,
        desired_ph_user_id,
        source_id,
        old_tg,
    )


async def _run(args: argparse.Namespace) -> None:
    analytics_dsn = _normalize_dsn(
        os.getenv("ANALYTICS_DB_DSN") or os.getenv("DATABASE_URL")
    )
    lead_dsn = _normalize_dsn(
        os.getenv("LEAD_DB_DSN") or os.getenv("LEAD_DB_URL")
    )
    if not analytics_dsn or not lead_dsn:
        raise SystemExit("Set ANALYTICS_DB_DSN and LEAD_DB_DSN before running.")

    analytics = await asyncpg.connect(analytics_dsn)
    lead = await asyncpg.connect(lead_dsn)
    try:
        candidates = await _load_candidates(analytics, lead)
        remap_candidates = [c for c in candidates if c.lead_telegram_id and c.lead_telegram_id != c.old_tg]
        no_tg_candidates = [c for c in candidates if c.lead_telegram_id is None]
        no_tg_with_funnel = [c for c in no_tg_candidates if c.has_funnel]
        no_tg_without_funnel = [c for c in no_tg_candidates if not c.has_funnel]

        print(f"Found wrong lead rows by users.id match: {len(candidates)}")
        print(f"  remap to real telegram_id: {len(remap_candidates)}")
        print(f"  no telegram_id in lead.users: {len(no_tg_candidates)}")
        print(f"    with funnel history: {len(no_tg_with_funnel)}")
        print(f"    without funnel history: {len(no_tg_without_funnel)}")

        if args.dry_run and not args.apply:
            return

        async with analytics.transaction():
            for c in remap_candidates:
                await _merge_and_move_row(
                    analytics,
                    source_id=c.raw_id,
                    old_tg=c.old_tg,
                    new_tg=int(c.lead_telegram_id),
                    desired_ph_user_id=c.ph_user_id or c.lead_user_id,
                )

            if args.convert_no_tg_to_direct:
                for c in no_tg_candidates:
                    if args.respect_funnel_history and c.has_funnel:
                        continue
                    await _merge_and_move_row(
                        analytics,
                        source_id=c.raw_id,
                        old_tg=c.old_tg,
                        new_tg=-abs(c.lead_user_id),
                        desired_ph_user_id=c.ph_user_id or c.lead_user_id,
                    )

        print("Cleanup applied.")
        if args.convert_no_tg_to_direct:
            skipped = len(no_tg_with_funnel) if args.respect_funnel_history else 0
            print(
                f"Converted no-tg rows to direct source: "
                f"{len(no_tg_candidates) - skipped}, skipped by funnel-history rule: {skipped}"
            )
    finally:
        await analytics.close()
        await lead.close()


def main() -> None:
    parser = argparse.ArgumentParser(description="Cleanup wrong lead tg_user_id mappings")
    parser.add_argument("--dry-run", action="store_true", help="Only print what would be changed")
    parser.add_argument("--apply", action="store_true", help="Apply changes")
    parser.add_argument(
        "--convert-no-tg-to-direct",
        action="store_true",
        help="Convert lead rows with no telegram_id to direct-source synthetic IDs",
    )
    parser.add_argument(
        "--ignore-funnel-history",
        action="store_true",
        help="When converting no-tg rows, do not preserve users with funnel_history/user_funnel activity",
    )
    args = parser.parse_args()
    args.respect_funnel_history = not args.ignore_funnel_history
    asyncio.run(_run(args))


if __name__ == "__main__":
    main()
