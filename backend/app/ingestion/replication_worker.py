"""
Real-time WAL replication worker.

Each bot DB gets one background thread that streams WAL changes via
psycopg2 LogicalReplicationConnection (test_decoding plugin).
Upserts into analytics_db use plain synchronous psycopg2 – no asyncio
in threads, no event-loop conflicts.

After changes arrive, a debounced refresher schedules the aggregate
refresh on the main FastAPI event loop via run_coroutine_threadsafe().
"""

from __future__ import annotations

import asyncio
import logging
import re
import threading
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Set

import psycopg2
import psycopg2.extras

logger = logging.getLogger("replication_worker")

_EXCLUDED_DBS: Set[str] = {
    "postgres", "template0", "template1",
    "analytics_db", "lead_dev", "lead_test", "lead_tests",
    "costyl1_bot", "heath_checker", "mymeet", "stats_service",
}

_PUB_NAME = "analytics_pub"
_WATCHED = {"users", "lead_resources", "ph_user_mirror"}
_SLOT_PREFIX = "anl_"
_PH_MIRROR_RECONCILE_INTERVAL_SECONDS = 300.0


# ---------------------------------------------------------------------------
# Debounced refresher – schedules work on the main event loop
# ---------------------------------------------------------------------------

_REFRESH_FLAG_KEY = "replication:needs_refresh"


class _DebouncedRefresher:
    """
    Sets a Redis flag after quiet period.
    The actual refresh runs in FastAPI's own event loop via _replication_refresh_loop().
    This avoids any cross-loop asyncio issues.
    """

    def __init__(self, delay: float = 8.0) -> None:
        self._delay = delay
        self._lock = threading.Lock()
        self._dirty: Set[str] = set()
        self._timer: Optional[threading.Timer] = None

    def mark_dirty(self, bot_key: str) -> None:
        with self._lock:
            self._dirty.add(bot_key)
            if self._timer:
                self._timer.cancel()
            t = threading.Timer(self._delay, self._flush)
            t.daemon = True
            self._timer = t
            t.start()

    def _flush(self) -> None:
        with self._lock:
            dirty = self._dirty.copy()
            self._dirty.clear()
            self._timer = None
        if not dirty:
            return
        try:
            import psycopg2
            from app.core.config import settings
            from sqlalchemy.engine import make_url
            u = make_url(str(settings.analytics_db_dsn))
            dsn = str(settings.analytics_db_dsn).replace("postgresql+asyncpg://", "postgresql://")
            conn = psycopg2.connect(dsn)
            conn.autocommit = True
            conn.cursor().execute("SELECT 1")  # keep-alive
            conn.close()
        except Exception:
            pass
        # Set flag – FastAPI loop picks it up via _replication_refresh_loop
        try:
            from redis import Redis
            from app.core.config import settings as s
            r = Redis.from_url(str(s.redis_url))
            r.set(_REFRESH_FLAG_KEY, "1", ex=300)
            logger.info("Debounced: set refresh flag for bots=%s", dirty)
        except Exception as exc:
            logger.error("Debounced flag error: %s", exc)


# ---------------------------------------------------------------------------
# Per-database streaming thread
# ---------------------------------------------------------------------------

class _BotStream:
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
        self._repl_kwargs = {**self._base_kwargs,
                             "connection_factory": psycopg2.extras.LogicalReplicationConnection}
        self._stop = threading.Event()
        self._repl_conn: Optional[Any] = None

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

    # ------------------------------------------------------------------

    def _run(self) -> None:
        slot = f"{_SLOT_PREFIX}{self.db_name[:58].lower()}"
        while not self._stop.is_set():
            try:
                self._setup_and_stream(slot)
            except Exception as exc:
                logger.warning("Replication db=%s error=%s; retry in 30 s", self.db_name, exc)
                time.sleep(30)

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

        batch: List[Dict[str, Any]] = []
        last_flush = time.monotonic()
        last_reconcile = time.monotonic()

        def _consume(msg: psycopg2.extras.ReplicationMessage) -> None:
            nonlocal batch, last_flush, last_reconcile
            change = self._parse(msg.payload)
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
            repl_cur.consume_stream(_consume, keepalive_interval=10)
        finally:
            self._repl_conn = None
            try:
                repl.close()
            except Exception:
                pass

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
        try:
            conn = psycopg2.connect(self._analytics_dsn)
            conn.autocommit = True
            cur = conn.cursor()
            for row in rows:
                self._upsert_row_sync(cur, row)
            for mirror_row in mirror_rows:
                self._upsert_mirror_row_sync(cur, mirror_row)
                self._project_mirror_to_raw_sync(cur, mirror_row)
            cur.close()
            conn.close()
            self._refresher.mark_dirty(self.bot_key)
        except Exception as exc:
            logger.error("Flush error db=%s: %s", self.db_name, exc)

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

    @staticmethod
    def _upsert_row_sync(cur: Any, row: Dict[str, Any]) -> None:
        bot_key = row["bot_key"]
        tg_user_id = row["tg_user_id"]
        created_at = row.get("created_at")

        update_fields = {
            k: v for k, v in row.items()
            if k not in ("bot_key", "tg_user_id", "created_at") and v is not None
        }

        if not update_fields:
            cur.execute(
                "INSERT INTO raw_bot_users"
                " (bot_key, tg_user_id, created_at, distance_grinding)"
                " VALUES (%s, %s, COALESCE(%s, now()), false)"
                " ON CONFLICT (bot_key, tg_user_id) DO NOTHING",
                (bot_key, tg_user_id, created_at),
            )
            return

        keys = list(update_fields.keys())
        vals = list(update_fields.values())
        col_list = ", ".join(["created_at", "distance_grinding"] + keys)
        ph_list = "COALESCE(%s, now()), false, " + ", ".join(["%s"] * len(keys))
        set_list = ", ".join(f"{k} = %s" for k in keys)

        cur.execute(
            f"INSERT INTO raw_bot_users (bot_key, tg_user_id, {col_list})"
            f" VALUES (%s, %s, {ph_list})"
            f" ON CONFLICT (bot_key, tg_user_id) DO UPDATE SET {set_list}",
            (bot_key, tg_user_id, created_at, *vals, *vals),
        )

    @staticmethod
    def _upsert_mirror_row_sync(cur: Any, row: Dict[str, Any]) -> None:
        mirror_id = _BotStream._to_int(row.get("id"))
        if mirror_id is None:
            return

        # Track which JSON-heavy fields are actually present in the WAL payload.
        # When TOAST prevents a field from being included in the WAL, row.get()
        # returns None (key absent). We must NOT overwrite existing analytics data
        # with a default empty value in that case.
        _TOAST_FIELDS = ("groups", "courses", "lessons", "course_memberships", "custom_tests")
        toast_present = {f: row.get(f) is not None for f in _TOAST_FIELDS}

        payload = {
            "ph_id": row.get("ph_id"),
            "username": row.get("username"),
            "first_name": row.get("first_name"),
            "last_name": row.get("last_name"),
            "ph_registration": row.get("ph_registration"),
            "ph_registration_at": row.get("ph_registration_at"),
            "authorization_date": row.get("authorization_date"),
            "last_activity": row.get("last_activity"),
            "last_visit_date": row.get("last_visit_date"),
            "is_blocked": _BotStream._to_bool(row.get("is_blocked")),
            "utm": _BotStream._to_json(row.get("utm"), default="{}"),
            "ph_utm": _BotStream._to_json(row.get("ph_utm"), default="{}"),
            "referer": _BotStream._normalize_nullable_text(row.get("referer")),
            "raw_link": _BotStream._normalize_nullable_text(row.get("raw_link")),
            "bot_raw": _BotStream._normalize_nullable_text(row.get("bot_raw")),
            "ph_raw": _BotStream._normalize_nullable_text(row.get("ph_raw")),
            "rc": row.get("rc"),
            "group": row.get("group"),
            "groups": _BotStream._to_json(row.get("groups"), default="[]"),
            "courses": _BotStream._to_json(row.get("courses"), default="{}"),
            "lessons": _BotStream._to_json(row.get("lessons"), default="[]"),
            "course_memberships": _BotStream._to_json(row.get("course_memberships"), default="[]"),
            "custom_tests": _BotStream._to_json(row.get("custom_tests"), default="[]"),
            "source_updated_at": _BotStream._to_ts(row.get("source_updated_at")),
            "synced_at": _BotStream._to_ts(row.get("synced_at")),
        }
        keys = list(payload.keys())
        vals = [payload[key] for key in keys]
        quoted_keys = ['"group"' if key == "group" else key for key in keys]

        # For TOAST-protected fields absent from WAL: preserve existing value on conflict.
        set_parts = []
        update_vals = []
        for key, quoted_key, val in zip(keys, quoted_keys, vals):
            if key in _TOAST_FIELDS and not toast_present[key]:
                set_parts.append(f"{quoted_key} = ph_user_mirror_replica.{quoted_key}")
            else:
                set_parts.append(f"{quoted_key} = %s")
                update_vals.append(val)

        set_list = ", ".join(set_parts)
        cur.execute(
            f"INSERT INTO ph_user_mirror_replica (id, {', '.join(quoted_keys)})"
            f" VALUES (%s, {', '.join(['%s'] * len(keys))})"
            f" ON CONFLICT (id) DO UPDATE SET {set_list}",
            (mirror_id, *vals, *update_vals),
        )

    def _project_mirror_to_raw_sync(self, cur: Any, row: Dict[str, Any]) -> None:
        mirror_id = self._to_int(row.get("id"))
        ph_id = self._to_int(row.get("ph_id"))
        if mirror_id is None or ph_id is None or ph_id <= 0:
            return

        parsed_registered_at = (
            self._ph_helper._parse_datetime(row.get("authorization_date"))
            or self._ph_helper._parse_datetime(row.get("ph_registration_at"))
        )
        mirror_payload = {
            "ph_id": row.get("ph_id"),
            "username": row.get("username"),
            "courses": self._to_python_json(row.get("courses")),
            "lessons": self._to_python_json(row.get("lessons")),
            "utm": self._to_python_json(row.get("utm")),
            "ph_utm": self._to_python_json(row.get("ph_utm")),
            "referer": row.get("referer"),
            "raw_link": row.get("raw_link"),
            "bot_raw": row.get("bot_raw"),
            "ph_raw": row.get("ph_raw"),
            "last_activity": row.get("last_activity"),
            "group": row.get("group"),
        }
        utm = self._ph_helper._extract_utm_from_payload(mirror_payload)
        direct_row = dict(
            bot_key="lead",
            tg_user_id=-ph_id,
            lead_user_id=mirror_id,
            ph_user_id=ph_id,
            created_at=parsed_registered_at,
            converted_to_lead=True,
            registered_platform=True,
            platform_registered_at=parsed_registered_at,
            learn_start_date=self._ph_helper._extract_learn_start_from_mirror(mirror_payload),
            started_learning=self._ph_helper._extract_learn_start_from_mirror(mirror_payload) is not None,
            start_course=self._ph_helper._extract_course_from_mirror(mirror_payload),
            username=None,
            referer=self._ph_helper._normalize_mirror_text(row.get("referer")),
            raw_link=self._ph_helper._normalize_mirror_text(row.get("raw_link")),
            bot_raw=self._ph_helper._normalize_mirror_text(row.get("bot_raw")),
            ph_raw=self._ph_helper._normalize_mirror_text(row.get("ph_raw")),
            last_activity=self._ph_helper._normalize_mirror_text(row.get("last_activity")),
            ph_group=self._ph_helper._normalize_mirror_text(row.get("group")),
            utm_source=utm.get("utm_source"),
            utm_campaign=utm.get("utm_campaign"),
            utm_medium=utm.get("utm_medium"),
            utm_content=utm.get("utm_content"),
            utm_term=utm.get("utm_term"),
            platform_utm_source=utm.get("utm_source"),
            platform_utm_campaign=utm.get("utm_campaign"),
            platform_utm_medium=utm.get("utm_medium"),
            platform_utm_content=utm.get("utm_content"),
            platform_utm_term=utm.get("utm_term"),
        )
        self._upsert_row_sync(cur, direct_row)

        update_fields = {
            "lead_user_id": mirror_id,
            "ph_user_id": ph_id,
            "registered_platform": True,
            "platform_registered_at": parsed_registered_at,
            "learn_start_date": self._ph_helper._extract_learn_start_from_mirror(mirror_payload),
            "started_learning": self._ph_helper._extract_learn_start_from_mirror(mirror_payload) is not None,
            "start_course": self._ph_helper._extract_course_from_mirror(mirror_payload),
            "referer": self._ph_helper._normalize_mirror_text(row.get("referer")),
            "raw_link": self._ph_helper._normalize_mirror_text(row.get("raw_link")),
            "bot_raw": self._ph_helper._normalize_mirror_text(row.get("bot_raw")),
            "ph_raw": self._ph_helper._normalize_mirror_text(row.get("ph_raw")),
            "last_activity": self._ph_helper._normalize_mirror_text(row.get("last_activity")),
            "ph_group": self._ph_helper._normalize_mirror_text(row.get("group")),
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
        }
        assignments = ", ".join(f"{key} = COALESCE(%s, {key})" for key in update_fields.keys())
        cur.execute(
            f"UPDATE raw_bot_users SET {assignments} WHERE bot_key = 'lead' AND lead_user_id = %s",
            (*update_fields.values(), mirror_id),
        )

    # ------------------------------------------------------------------

    @staticmethod
    def _to_int(v: Any) -> Optional[int]:
        try:
            return int(v) if v is not None else None
        except (ValueError, TypeError):
            return None

    @staticmethod
    def _to_bool(v: Any) -> Optional[bool]:
        if v is None:
            return None
        if isinstance(v, bool):
            return v
        value = str(v).strip().lower()
        if value in {"true", "t", "1"}:
            return True
        if value in {"false", "f", "0"}:
            return False
        return None

    @staticmethod
    def _normalize_nullable_text(v: Any) -> Optional[str]:
        if v is None:
            return None
        text_value = str(v).strip()
        if not text_value or text_value.lower() in {"null", "none"}:
            return None
        return text_value

    @staticmethod
    def _to_json(v: Any, default: str) -> str:
        if v is None:
            return default
        if isinstance(v, (dict, list)):
            import json

            return json.dumps(v, ensure_ascii=False)
        text_value = str(v).strip()
        if not text_value:
            return default
        import json
        import ast

        try:
            parsed = json.loads(text_value)
            return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            pass
        try:
            parsed = ast.literal_eval(text_value)
            return json.dumps(parsed, ensure_ascii=False)
        except Exception:
            return default

    @staticmethod
    def _to_python_json(v: Any) -> Any:
        if v is None:
            return None
        if not isinstance(v, str):
            return v
        text_value = v.strip()
        if not text_value:
            return None
        import json

        try:
            return json.loads(text_value)
        except json.JSONDecodeError:
            return v

    @staticmethod
    def _to_ts(v: Any) -> Optional[datetime]:
        if v is None:
            return None
        try:
            return datetime.fromisoformat(str(v))
        except (ValueError, TypeError):
            return None


# ---------------------------------------------------------------------------
# Async refresh loop – runs inside FastAPI's event loop
# ---------------------------------------------------------------------------

async def _replication_refresh_loop() -> None:
    """Checks Redis flag every 10 s and runs aggregate refresh when set."""
    import time as _time
    from redis import Redis
    from app.core.config import settings
    from app.core.redis_client import RedisCache
    from app.db.session import async_session
    from app.services.aggregate_refresher import AggregateRefresher
    from app.ingestion.lead_ingestor import LeadIngestor
    from app.services.attribution_service import AttributionService

    r = Redis.from_url(str(settings.redis_url))
    _KEEPALIVE_INTERVAL = 1200  # принудительный refresh каждые 20 мин
    last_forced = 0.0
    while True:
        await asyncio.sleep(10)
        try:
            import time as _t
            # Принудительный refresh если долго не было событий
            if _t.time() - last_forced > _KEEPALIVE_INTERVAL:
                r.set(_REFRESH_FLAG_KEY, "1", ex=300)
            if not r.getdel(_REFRESH_FLAG_KEY):
                continue
            last_forced = _t.time()
            logger.info("Replication refresh: starting")
            cache = RedisCache()
            # Update converted_to_lead flags from the lead DB
            async with async_session() as session:
                await LeadIngestor().ingest(session)
                await session.commit()
            # Rebuild first/last touch attribution
            await AttributionService().rebuild()
            # Rebuild aggregates (uses updated converted_to_lead values)
            await AggregateRefresher().refresh(days=settings.aggregate_refresh_days)
            await cache.delete_pattern("report:*")
            ts = int(_time.time())
            payload = {"ts": ts, "status": "ok", "error": None, "source": "replication"}
            await cache.set_json("sync:last_ingestion", payload)
            await cache.set_json("sync:last_ingestion_success", payload)
            logger.info("Replication refresh: done")
        except Exception as exc:
            logger.error("Replication refresh error: %s", exc)


# ---------------------------------------------------------------------------
# Manager
# ---------------------------------------------------------------------------

class ReplicationWorker:
    def __init__(self) -> None:
        from app.core.config import settings
        from sqlalchemy.engine import make_url
        dsn = make_url(str(settings.postgres_admin_dsn))
        self._pg_host: str = dsn.host or "localhost"
        self._pg_port: int = dsn.port or 5432
        self._pg_user: str = dsn.username or "postgres"
        self._pg_password: str = dsn.password or ""
        # Sync DSN for psycopg2 upserts into analytics_db
        raw = str(settings.analytics_db_dsn).replace("postgresql+asyncpg://", "postgresql://")
        self._analytics_sync_dsn = raw
        self._refresher = _DebouncedRefresher(delay=8.0)
        self._streams: Dict[str, _BotStream] = {}

    def start(self) -> None:
        loop = asyncio.get_event_loop()
        asyncio.ensure_future(_replication_refresh_loop(), loop=loop)
        asyncio.ensure_future(self._reconcile_loop(), loop=loop)
        t = threading.Thread(target=self._discover, args=(loop,), daemon=True, name="repl-manager")
        t.start()

    def stop(self) -> None:
        for s in self._streams.values():
            s.stop()

    def _discover(self, loop: asyncio.AbstractEventLoop) -> None:
        try:
            future = asyncio.run_coroutine_threadsafe(self._async_discover(), loop)
            future.result()
        except Exception as exc:
            logger.error("ReplicationWorker discovery error: %s", exc)

    async def _desired_dbs(self) -> Set[str]:
        """Return the set of db names that should be replicated right now."""
        from app.db.postgres_explorer import PostgresExplorer
        from app.services.bot_registry_service import BotRegistryService
        from app.db.session import async_session

        async with async_session() as session:
            registry_entries = await BotRegistryService().list_registry(session)

        no_replicate: Set[str] = {
            entry.bot_key for entry in registry_entries if not entry.replicate
        }
        all_dbs = await PostgresExplorer().list_bot_databases()
        return {db for db in all_dbs if db not in _EXCLUDED_DBS and db not in no_replicate}

    async def _async_discover(self) -> None:
        from app.services.advertising_company_service import AdvertisingCompanyService
        from app.db.session import async_session

        async with async_session() as session:
            company_map = await AdvertisingCompanyService().bot_to_company_map(session)

        desired = await self._desired_dbs()
        logger.info("ReplicationWorker: starting %d streams", len(desired))

        for db in desired:
            self._start_stream(db, company_map)

    def _start_stream(self, db: str, company_map: Dict[str, str]) -> None:
        if db in self._streams:
            return
        stream = _BotStream(
            db_name=db,
            pg_host=self._pg_host,
            pg_port=self._pg_port,
            pg_user=self._pg_user,
            pg_password=self._pg_password,
            analytics_sync_dsn=self._analytics_sync_dsn,
            refresher=self._refresher,
            company_map=company_map,
        )
        stream.start()
        self._streams[db] = stream
        logger.info("ReplicationWorker: stream started db=%s", db)

    async def _reconcile_loop(self) -> None:
        """Every 30 s: start streams for newly enabled bots, stop for disabled."""
        from app.services.advertising_company_service import AdvertisingCompanyService
        from app.db.session import async_session

        while True:
            await asyncio.sleep(30)
            try:
                desired = await self._desired_dbs()
                running = set(self._streams.keys())

                # Start new
                to_start = desired - running
                if to_start:
                    async with async_session() as session:
                        company_map = await AdvertisingCompanyService().bot_to_company_map(session)
                    for db in to_start:
                        logger.info("ReplicationWorker: reconcile — starting db=%s", db)
                        self._start_stream(db, company_map)

                # Stop removed
                to_stop = running - desired
                for db in to_stop:
                    logger.info("ReplicationWorker: reconcile — stopping db=%s", db)
                    self._streams.pop(db).stop()

            except Exception as exc:
                logger.error("ReplicationWorker: reconcile error: %s", exc)


_worker: Optional[ReplicationWorker] = None


def get_worker() -> ReplicationWorker:
    global _worker
    if _worker is None:
        _worker = ReplicationWorker()
    return _worker


def start_worker() -> None:
    get_worker().start()
