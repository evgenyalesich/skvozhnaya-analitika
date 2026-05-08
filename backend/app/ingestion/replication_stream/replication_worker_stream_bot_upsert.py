from __future__ import annotations

from datetime import datetime
from typing import Any, Dict, Optional

from psycopg2.extras import Json


class _BotStreamUpsertMixin:
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
        mirror_id = _BotStreamUpsertMixin._to_int(row.get("id"))
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
            "is_blocked": _BotStreamUpsertMixin._to_bool(row.get("is_blocked")),
            "utm": _BotStreamUpsertMixin._to_json(row.get("utm"), default="{}"),
            "ph_utm": _BotStreamUpsertMixin._to_json(row.get("ph_utm"), default="{}"),
            "referer": _BotStreamUpsertMixin._normalize_nullable_text(row.get("referer")),
            "raw_link": _BotStreamUpsertMixin._normalize_nullable_text(row.get("raw_link")),
            "bot_raw": _BotStreamUpsertMixin._normalize_nullable_text(row.get("bot_raw")),
            "ph_raw": _BotStreamUpsertMixin._normalize_nullable_text(row.get("ph_raw")),
            "rc": row.get("rc"),
            "group": row.get("group"),
            "groups": _BotStreamUpsertMixin._to_json(row.get("groups"), default="[]"),
            "courses": _BotStreamUpsertMixin._to_json(row.get("courses"), default="{}"),
            "lessons": _BotStreamUpsertMixin._to_json(row.get("lessons"), default="[]"),
            "course_memberships": _BotStreamUpsertMixin._to_json(row.get("course_memberships"), default="[]"),
            "custom_tests": _BotStreamUpsertMixin._to_json(row.get("custom_tests"), default="[]"),
            "source_updated_at": _BotStreamUpsertMixin._to_ts(row.get("source_updated_at")),
            "synced_at": _BotStreamUpsertMixin._to_ts(row.get("synced_at")),
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
