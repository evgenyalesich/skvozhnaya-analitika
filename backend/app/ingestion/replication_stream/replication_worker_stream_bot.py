from __future__ import annotations

import json
import random
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

import psycopg2

from app.ingestion.replication_stream.replication_worker_stream_constants import (
    _PH_MIRROR_RECONCILE_INTERVAL_SECONDS,
    _PUB_NAME,
    _REPL_BACKOFF_MAX_SECONDS,
    _REPL_BACKOFF_MIN_SECONDS,
    _REPL_DLQ_PAYLOAD_LIMIT,
    _REPL_METRICS_TTL_SECONDS,
    _REPL_WATCHDOG_ERROR_THRESHOLD,
    _REPL_WATCHDOG_ERROR_WINDOW_SECONDS,
    _REPL_WATCHDOG_LAG_BYTES_THRESHOLD,
    _REPL_WATCHDOG_STALL_SECONDS,
    _SLOT_PREFIX,
    _WATCHED,
    logger,
)
from app.ingestion.replication_stream.replication_worker_stream_bot_upsert import _BotStreamUpsertMixin
from app.ingestion.replication_stream.replication_worker_stream_refresher import _DebouncedRefresher


class _BotStream(_BotStreamUpsertMixin):
    def __init__(
        self,
        db_name: str,
        pg_host: str,
        pg_port: int,
        pg_user: str,
        pg_password: str,
        analytics_sync_dsn: str,
        refresher: _DebouncedRefresher,
        company_map: Dict[str, str],
    ) -> None:
        from app.ingestion.pokerhub_ingestor import PokerHubIngestor

        self.db_name = db_name
        self.bot_key = db_name
        self._analytics_dsn = analytics_sync_dsn
        self._refresher = refresher
        self._company_map = company_map
        self._ph_helper = PokerHubIngestor()
        self._base_kwargs: Dict[str, Any] = dict(
            host=pg_host, port=pg_port,
            user=pg_user, password=pg_password,
            database=db_name,
        )
        self._repl_kwargs = {
            **self._base_kwargs,
            "connection_factory": psycopg2.extras.LogicalReplicationConnection,
            # Detect silent TCP drops within ~105s instead of 30 minutes.
            "keepalives": 1,
            "keepalives_idle": 60,
            "keepalives_interval": 15,
            "keepalives_count": 3,
        }
        self._stop = threading.Event()
        self._repl_conn: Optional[Any] = None
        self._restarts = 0
        self._errors_last_minute: List[float] = []
        self._last_event_ts = 0
        self._last_error_ts = 0
        self._dlq_ready = False

    def start(self) -> None:
        t = threading.Thread(target=self._run,
                             name=f"repl-{self.db_name[:28]}",
                             daemon=True)
        t.start()

    def stop(self) -> None:
        self._stop.set()
        conn = self._repl_conn
        if conn is not None:
            try:
                conn.close()
            except Exception:
                pass

    def _metrics_key(self) -> str:
        return f"replication:stream:{self.db_name}:metrics"

    @staticmethod
    def _error_retention_seconds() -> int:
        # Keep enough history for watchdog error-window checks.
        return max(3600, _REPL_WATCHDOG_ERROR_WINDOW_SECONDS + 60)

    def _record_error(self) -> None:
        now = time.time()
        self._last_error_ts = int(now)
        self._errors_last_minute.append(now)
        cutoff = now - self._error_retention_seconds()
        self._errors_last_minute = [ts for ts in self._errors_last_minute if ts >= cutoff]

    def _errors_in_window(self, window_seconds: int) -> int:
        now = time.time()
        cutoff = now - max(1, window_seconds)
        retention_cutoff = now - self._error_retention_seconds()
        self._errors_last_minute = [ts for ts in self._errors_last_minute if ts >= retention_cutoff]
        return sum(1 for ts in self._errors_last_minute if ts >= cutoff)

    def _set_metrics(self, status: str, retry_in_seconds: float | None = None) -> None:
        now = time.time()
        retention_cutoff = now - self._error_retention_seconds()
        self._errors_last_minute = [ts for ts in self._errors_last_minute if ts >= retention_cutoff]
        errors_last_minute = sum(1 for ts in self._errors_last_minute if ts >= now - 60)
        payload: Dict[str, Any] = {
            "db_name": self.db_name,
            "bot_key": self.bot_key,
            "status": status,
            "restarts": self._restarts,
            "errors_last_minute": errors_last_minute,
            "last_event_ts": self._last_event_ts or None,
            "last_error_ts": self._last_error_ts or None,
            "updated_at": int(now),
        }
        if retry_in_seconds is not None:
            payload["retry_in_seconds"] = round(retry_in_seconds, 2)
        try:
            from redis import Redis
            from app.core.config import settings

            redis_conn = Redis.from_url(str(settings.redis_url))
            redis_conn.set(self._metrics_key(), json.dumps(payload, ensure_ascii=False), ex=_REPL_METRICS_TTL_SECONDS)
        except Exception:
            logger.debug("Failed to publish replication stream metrics for db=%s", self.db_name, exc_info=True)

    def _write_dlq_sync(self, reason: str, payload: Any, error: str | None = None) -> None:
        text_payload = str(payload)
        if len(text_payload) > _REPL_DLQ_PAYLOAD_LIMIT:
            text_payload = text_payload[:_REPL_DLQ_PAYLOAD_LIMIT] + "...[truncated]"
        conn = psycopg2.connect(self._analytics_dsn)
        conn.autocommit = True
        cur = conn.cursor()
        try:
            if not self._dlq_ready:
                cur.execute(
                    """
                    CREATE TABLE IF NOT EXISTS replication_dlq (
                        id BIGSERIAL PRIMARY KEY,
                        db_name TEXT NOT NULL,
                        bot_key TEXT NOT NULL,
                        reason TEXT NOT NULL,
                        payload TEXT,
                        error TEXT,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT now()
                    )
                    """
                )
                self._dlq_ready = True
            cur.execute(
                """
                INSERT INTO replication_dlq (db_name, bot_key, reason, payload, error)
                VALUES (%s, %s, %s, %s, %s)
                """,
                (self.db_name, self.bot_key, reason, text_payload, (error or "")[:1024]),
            )
        finally:
            try:
                cur.close()
            except Exception:
                pass
            conn.close()

    # ------------------------------------------------------------------

    def _run(self) -> None:
        slot = f"{_SLOT_PREFIX}{self.db_name[:58].lower()}"
        backoff_seconds = max(1.0, _REPL_BACKOFF_MIN_SECONDS)
        while not self._stop.is_set():
            try:
                self._set_metrics("starting")
                self._setup_and_stream(slot)
                backoff_seconds = max(1.0, _REPL_BACKOFF_MIN_SECONDS)
            except Exception as exc:
                self._record_error()
                self._restarts += 1
                sleep_seconds = min(_REPL_BACKOFF_MAX_SECONDS, backoff_seconds)
                sleep_seconds *= random.uniform(0.8, 1.2)
                self._set_metrics("error", retry_in_seconds=sleep_seconds)
                logger.warning(
                    "Replication db=%s error=%s; retry in %.1f s (restart=%s)",
                    self.db_name,
                    exc,
                    sleep_seconds,
                    self._restarts,
                )
                time.sleep(sleep_seconds)
                backoff_seconds = min(_REPL_BACKOFF_MAX_SECONDS, max(1.0, backoff_seconds * 2))

    def _setup_and_stream(self, slot: str) -> None:
        # --- plain connection: create publication + slot ---
        plain = psycopg2.connect(**self._base_kwargs)
        plain.autocommit = True
        cur = plain.cursor()

        cur.execute("SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='lead_resources' LIMIT 1")
        has_lr = cur.fetchone() is not None
        cur.execute("SELECT 1 FROM information_schema.tables "
                    "WHERE table_schema='public' AND table_name='ph_user_mirror' LIMIT 1")
        has_ph_mirror = cur.fetchone() is not None

        cur.execute(f"SELECT 1 FROM pg_publication WHERE pubname = '{_PUB_NAME}'")
        if not cur.fetchone():
            tables = ["users"]
            if has_lr:
                tables.append("lead_resources")
            if has_ph_mirror:
                tables.append("ph_user_mirror")
            tables_sql = ", ".join(tables)
            cur.execute(f"CREATE PUBLICATION {_PUB_NAME} FOR TABLE {tables_sql}")
            logger.info("Created publication %s on db=%s", _PUB_NAME, self.db_name)

        cur.execute(f"SELECT 1 FROM pg_replication_slots WHERE slot_name = '{slot}'")
        if not cur.fetchone():
            cur.execute(f"SELECT pg_create_logical_replication_slot('{slot}', 'test_decoding')")
            logger.info("Created slot %s on db=%s", slot, self.db_name)

        cur.close()
        plain.close()

        if self.db_name == "lead" and has_ph_mirror:
            self._reconcile_ph_mirror_sync(reason="startup")

        # --- replication connection ---
        repl = psycopg2.connect(**self._repl_kwargs)
        self._repl_conn = repl
        repl_cur = repl.cursor()
        repl_cur.start_replication(slot_name=slot, decode=True,
                                   options={"include-timestamp": "on"})
        logger.info("Replication streaming started: db=%s slot=%s", self.db_name, slot)
        self._set_metrics("streaming")
        self._last_event_ts = int(time.time())

        batch: List[Dict[str, Any]] = []
        last_flush = time.monotonic()
        last_reconcile = time.monotonic()
        last_message_at = time.monotonic()
        last_feedback_at = time.monotonic()
        watchdog_stop = threading.Event()
        restart_requested = threading.Event()
        restart_reason: Dict[str, str] = {"value": ""}

        def _watchdog() -> None:
            nonlocal last_message_at
            last_idle_log_at = 0.0
            while not self._stop.is_set() and not watchdog_stop.is_set():
                time.sleep(5)
                stall_seconds = time.monotonic() - last_message_at
                if stall_seconds < _REPL_WATCHDOG_STALL_SECONDS:
                    continue
                signals: List[str] = []
                errors_recent = self._errors_in_window(_REPL_WATCHDOG_ERROR_WINDOW_SECONDS)
                if errors_recent >= _REPL_WATCHDOG_ERROR_THRESHOLD:
                    signals.append(f"errors={errors_recent}/{_REPL_WATCHDOG_ERROR_WINDOW_SECONDS}s")
                lag_bytes = self._slot_lag_bytes(slot)
                if lag_bytes is not None and lag_bytes >= _REPL_WATCHDOG_LAG_BYTES_THRESHOLD:
                    signals.append(f"lag_bytes={lag_bytes}")
                if not signals:
                    now = time.monotonic()
                    if now - last_idle_log_at >= 60:
                        logger.info(
                            "Replication watchdog: idle stream db=%s for %.1fs without failure signals; keep connection",
                            self.db_name,
                            stall_seconds,
                        )
                        last_idle_log_at = now
                    continue
                logger.warning(
                    "Replication watchdog: stream stalled db=%s for %.1fs with signals=[%s], requesting soft restart",
                    self.db_name,
                    stall_seconds,
                    ", ".join(signals),
                )
                self._record_error()
                self._set_metrics("stalled")
                restart_reason["value"] = f"stalled {stall_seconds:.1f}s; {'; '.join(signals)}"
                restart_requested.set()
                return

        watchdog_thread = threading.Thread(target=_watchdog, name=f"repl-watchdog-{self.db_name[:20]}", daemon=True)
        watchdog_thread.start()

        def _consume(msg: psycopg2.extras.ReplicationMessage) -> None:
            nonlocal batch, last_flush, last_reconcile, last_message_at
            last_message_at = time.monotonic()
            self._last_event_ts = int(time.time())
            try:
                change = self._parse(msg.payload)
            except Exception as exc:
                self._record_error()
                logger.exception("Replication parse error db=%s", self.db_name)
                try:
                    self._write_dlq_sync("parse_error", msg.payload, str(exc))
                except Exception:
                    logger.exception("Replication DLQ write failed db=%s", self.db_name)
                msg.cursor.send_feedback(flush_lsn=msg.data_start)
                return
            if change:
                batch.append(change)
            now = time.monotonic()
            if len(batch) >= 50 or (batch and now - last_flush >= 2.0):
                self._flush_sync(batch.copy())
                batch.clear()
                last_flush = now
            if (
                self.db_name == "lead"
                and has_ph_mirror
                and now - last_reconcile >= _PH_MIRROR_RECONCILE_INTERVAL_SECONDS
            ):
                # WAL keeps replica near real-time; periodic reconcile heals any
                # missed/partial TOAST-heavy mirror rows before reports drift.
                self._reconcile_ph_mirror_sync(reason="periodic")
                last_reconcile = now
            msg.cursor.send_feedback(flush_lsn=msg.data_start)

        try:
            while not self._stop.is_set() and not restart_requested.is_set():
                msg = repl_cur.read_message()
                now = time.monotonic()
                if msg is None:
                    if batch and now - last_flush >= 2.0:
                        self._flush_sync(batch.copy())
                        batch.clear()
                        last_flush = now
                    if (
                        self.db_name == "lead"
                        and has_ph_mirror
                        and now - last_reconcile >= _PH_MIRROR_RECONCILE_INTERVAL_SECONDS
                    ):
                        self._reconcile_ph_mirror_sync(reason="periodic")
                        last_reconcile = now
                    if now - last_feedback_at >= 10:
                        try:
                            repl_cur.send_feedback(reply=True)
                        except Exception:
                            pass
                        last_feedback_at = now
                    time.sleep(0.2)
                    continue
                _consume(msg)
                last_feedback_at = now
            if restart_requested.is_set() and not self._stop.is_set():
                raise RuntimeError(f"soft restart requested by watchdog ({restart_reason['value']})")
        finally:
            watchdog_stop.set()
            self._repl_conn = None
            try:
                repl.close()
            except Exception:
                pass

    def _slot_lag_bytes(self, slot: str) -> Optional[int]:
        try:
            conn = psycopg2.connect(**self._base_kwargs)
            cur = conn.cursor()
            cur.execute(
                """
                SELECT
                  CASE
                    WHEN confirmed_flush_lsn IS NULL THEN NULL
                    ELSE pg_wal_lsn_diff(pg_current_wal_lsn(), confirmed_flush_lsn)
                  END
                FROM pg_replication_slots
                WHERE slot_name = %s
                """,
                (slot,),
            )
            row = cur.fetchone()
            cur.close()
            conn.close()
            if not row or row[0] is None:
                return None
            return int(row[0])
        except Exception:
            logger.debug("Failed to read replication lag for db=%s slot=%s", self.db_name, slot, exc_info=True)
            return None

    # ------------------------------------------------------------------
    # Parsing
    # ------------------------------------------------------------------

    _FIELD_RE = re.compile(r"(\w+)\[[^\]]+\]:(null|'(?:[^']|'')*'|[^ ]+)")

    def _parse(self, payload: str) -> Optional[Dict[str, Any]]:
        payload = payload.strip()
        if payload.startswith(("BEGIN", "COMMIT")):
            return None
        m = re.match(r"table public\.(\w+): (?:INSERT|UPDATE): (.+)", payload)
        if not m:
            return None
        table = m.group(1)
        if table not in _WATCHED:
            return None
        fields: Dict[str, Any] = {}
        for fm in self._FIELD_RE.finditer(m.group(2)):
            val = fm.group(2)
            if val == "null":
                fields[fm.group(1)] = None
            elif val.startswith("'"):
                fields[fm.group(1)] = val[1:-1].replace("''", "'")
            else:
                fields[fm.group(1)] = val
        return {"table": table, "fields": fields}

    # ------------------------------------------------------------------
    # Sync upsert via psycopg2 (no asyncio)
    # ------------------------------------------------------------------

    def _flush_sync(self, changes: List[Dict[str, Any]]) -> None:
        rows = []
        mirror_rows = []
        for ch in changes:
            table, f = ch["table"], ch["fields"]
            if self.db_name == "lead":
                if table == "users":
                    tg_id = self._to_int(f.get("telegram_id"))
                elif table == "ph_user_mirror":
                    mirror_rows.append(f)
                    continue
                else:
                    # lead_resources.user_id points to internal lead users.id, not telegram_id.
                    # We skip realtime lead_resources sync to avoid writing internal IDs into tg_user_id.
                    continue
            else:
                tg_id = self._to_int(
                    (f.get("telegram_id") or f.get("id")) if table == "users" else f.get("user_id")
                )
            if not tg_id:
                continue
            if table == "users":
                rows.append(dict(
                    bot_key=self.bot_key,
                    tg_user_id=tg_id,
                    lead_user_id=self._to_int(f.get("id")) if self.db_name == "lead" else None,
                    username=f.get("username"),
                    created_at=self._to_ts(
                        f.get("timestamp_registration")
                        or f.get("created_at")
                        or f.get("first_seen_at")
                        or f.get("last_seen_at")
                    ),
                    advertising_company=self._company_map.get(self.bot_key),
                ))
            else:
                rows.append(dict(
                    bot_key=self.bot_key,
                    tg_user_id=tg_id,
                    utm_source=f.get("source"),
                    utm_campaign=f.get("campaign"),
                    utm_medium=f.get("medium"),
                    utm_content=f.get("content"),
                    utm_term=f.get("term"),
                ))
        if not rows and not mirror_rows:
            return
        wrote_anything = False
        try:
            conn = psycopg2.connect(self._analytics_dsn)
            conn.autocommit = True
            cur = conn.cursor()
            for row in rows:
                try:
                    self._upsert_row_sync(cur, row)
                    wrote_anything = True
                except Exception as exc:
                    self._record_error()
                    logger.exception("Replication row upsert failed db=%s bot=%s tg=%s", self.db_name, row.get("bot_key"), row.get("tg_user_id"))
                    try:
                        self._write_dlq_sync("row_upsert_error", row, str(exc))
                    except Exception:
                        logger.exception("Replication DLQ write failed db=%s", self.db_name)
            for mirror_row in mirror_rows:
                try:
                    self._upsert_mirror_row_sync(cur, mirror_row)
                    self._project_mirror_to_raw_sync(cur, mirror_row)
                    wrote_anything = True
                except Exception as exc:
                    self._record_error()
                    logger.exception("Replication mirror upsert failed db=%s", self.db_name)
                    try:
                        self._write_dlq_sync("mirror_upsert_error", mirror_row, str(exc))
                    except Exception:
                        logger.exception("Replication DLQ write failed db=%s", self.db_name)
            cur.close()
            conn.close()
            if wrote_anything:
                self._refresher.mark_dirty(self.bot_key)
        except Exception as exc:
            self._record_error()
            logger.error("Flush error db=%s: %s", self.db_name, exc)
            try:
                self._write_dlq_sync("flush_error", {"rows": len(rows), "mirror_rows": len(mirror_rows)}, str(exc))
            except Exception:
                logger.exception("Replication DLQ write failed db=%s", self.db_name)

    def _reconcile_ph_mirror_sync(self, reason: str = "manual") -> None:
        """Heal analytics replica from the authoritative lead mirror snapshot.

        Logical replication only delivers changes after the slot is created. When a
        backend is restarted or analytics is redeployed, relying on WAL alone can
        leave `ph_user_mirror_replica` permanently partial until rows happen to be
        updated again in `lead`. Periodic reconciliation keeps the replica complete
        even if individual WAL payloads are partial or some updates were missed.
        """
        source = psycopg2.connect(**self._base_kwargs)
        source_cur = source.cursor()
        source_cur.execute("SELECT * FROM ph_user_mirror ORDER BY id")

        analytics = psycopg2.connect(self._analytics_dsn)
        analytics.autocommit = True
        analytics_cur = analytics.cursor()

        synced = 0
        source_ids: set[int] = set()
        try:
            columns = [desc[0] for desc in source_cur.description]
            while True:
                batch = source_cur.fetchmany(500)
                if not batch:
                    break
                for record in batch:
                    row = dict(zip(columns, record))
                    mirror_id = _BotStream._to_int(row.get("id"))
                    if mirror_id is not None:
                        source_ids.add(mirror_id)
                    self._upsert_mirror_row_sync(analytics_cur, row)
                    self._project_mirror_to_raw_sync(analytics_cur, row)
                    synced += 1
            if source_ids:
                analytics_cur.execute(
                    "DELETE FROM ph_user_mirror_replica WHERE id <> ALL(%s)",
                    (list(source_ids),),
                )
            if synced:
                self._refresher.mark_dirty(self.bot_key)
            logger.info(
                "Replication ph_user_mirror reconcile completed: db=%s reason=%s rows=%s",
                self.db_name,
                reason,
                synced,
            )
        finally:
            try:
                source_cur.close()
            except Exception:
                pass
            try:
                source.close()
            except Exception:
                pass
            try:
                analytics_cur.close()
            except Exception:
                pass
            try:
                analytics.close()
            except Exception:
                pass
