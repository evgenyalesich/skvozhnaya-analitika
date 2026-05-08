#!/usr/bin/env python3
from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

import psycopg2


@dataclass
class SlotState:
    slot_name: str
    database: str | None
    active: bool
    inactive_since: str | None
    retained_mb: int


def _env_int(name: str, default: int) -> int:
    value = os.getenv(name)
    if value is None:
        return default
    try:
        return int(value)
    except ValueError:
        return default


def _env_bool(name: str, default: bool = False) -> bool:
    value = os.getenv(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}


def _dsn() -> str:
    raw = os.getenv("POSTGRES_ADMIN_DSN") or ""
    if not raw:
        raise RuntimeError("POSTGRES_ADMIN_DSN is not set")
    return raw.replace("postgresql+asyncpg://", "postgresql://")


def _fetch_slots(conn) -> list[SlotState]:
    cur = conn.cursor()
    cur.execute(
        """
        SELECT EXISTS (
            SELECT 1
            FROM information_schema.columns
            WHERE table_schema = 'pg_catalog'
              AND table_name = 'pg_replication_slots'
              AND column_name = 'inactive_since'
        )
        """
    )
    has_inactive_since = bool(cur.fetchone()[0])
    if has_inactive_since:
        cur.execute(
            """
            SELECT
                slot_name,
                database,
                active,
                inactive_since,
                COALESCE(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint, 0) AS retained_bytes
            FROM pg_replication_slots
            ORDER BY active DESC, slot_name
            """
        )
    else:
        cur.execute(
            """
            SELECT
                slot_name,
                database,
                active,
                NULL::timestamptz AS inactive_since,
                COALESCE(pg_wal_lsn_diff(pg_current_wal_lsn(), restart_lsn)::bigint, 0) AS retained_bytes
            FROM pg_replication_slots
            ORDER BY active DESC, slot_name
            """
        )
    rows = cur.fetchall()
    slots: list[SlotState] = []
    for slot_name, database, active, inactive_since, retained_bytes in rows:
        inactive_iso = inactive_since.astimezone(timezone.utc).isoformat() if inactive_since else None
        slots.append(
            SlotState(
                slot_name=str(slot_name),
                database=str(database) if database else None,
                active=bool(active),
                inactive_since=inactive_iso,
                retained_mb=int((retained_bytes or 0) / (1024 * 1024)),
            )
        )
    return slots


def _minutes_since(iso_dt: str | None) -> int:
    if not iso_dt:
        return 0
    dt = datetime.fromisoformat(iso_dt)
    return int((datetime.now(timezone.utc) - dt).total_seconds() / 60)


def _drop_slot(conn, slot_name: str) -> None:
    cur = conn.cursor()
    cur.execute("SELECT pg_drop_replication_slot(%s)", (slot_name,))


def main() -> int:
    threshold_mb = _env_int("REPL_GUARD_MAX_SLOT_MB", 4096)
    inactive_minutes = _env_int("REPL_GUARD_INACTIVE_MINUTES", 30)
    slot_prefix = os.getenv("REPL_GUARD_SLOT_PREFIX", "analytics_")
    apply_drop = _env_bool("REPL_GUARD_DROP_INACTIVE", False)

    conn = psycopg2.connect(_dsn())
    conn.autocommit = True
    try:
        slots = _fetch_slots(conn)
        oversized = [s for s in slots if s.retained_mb >= threshold_mb]

        stale_inactive: list[SlotState] = []
        for slot in slots:
            if slot.active:
                continue
            if slot_prefix and not slot.slot_name.startswith(slot_prefix):
                continue
            if _minutes_since(slot.inactive_since) >= inactive_minutes:
                stale_inactive.append(slot)

        dropped: list[str] = []
        drop_errors: dict[str, str] = {}
        if apply_drop:
            for slot in stale_inactive:
                try:
                    _drop_slot(conn, slot.slot_name)
                    dropped.append(slot.slot_name)
                except Exception as exc:  # pragma: no cover
                    drop_errors[slot.slot_name] = str(exc)

        payload: dict[str, Any] = {
            "ok": len(oversized) == 0 and len(drop_errors) == 0,
            "threshold_mb": threshold_mb,
            "inactive_minutes": inactive_minutes,
            "slot_prefix": slot_prefix,
            "drop_enabled": apply_drop,
            "slots_total": len(slots),
            "oversized_slots": [asdict(s) for s in oversized],
            "stale_inactive_slots": [asdict(s) for s in stale_inactive],
            "dropped_slots": dropped,
            "drop_errors": drop_errors,
        }
        print(json.dumps(payload, ensure_ascii=False))
        return 0 if payload["ok"] else 1
    finally:
        conn.close()


if __name__ == "__main__":
    raise SystemExit(main())
