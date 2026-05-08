from __future__ import annotations

from datetime import datetime, timezone
import re
from typing import List, Optional


class GoogleSheetsIngestorHelpersMixin:
    @staticmethod
    def _normalize_key(value: str) -> str:
        value = re.sub(r"\s+", "_", str(value).strip().lower())
        value = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE)
        return re.sub(r"_+", "_", value).strip("_")

    @staticmethod
    def _normalize_username(value: Optional[str]) -> str:
        if not value:
            return ""
        value = str(value).strip()
        if value.startswith("@"):
            value = value[1:]
        return value.lower()

    @staticmethod
    def _to_bool(value: str) -> bool:
        return str(value).strip().lower() in ("1", "true", "yes", "y", "да", "ok")

    def _get_bool(self, row: dict, keys: List[str]) -> Optional[bool]:
        for key in keys:
            if key in row and str(row.get(key)).strip() != "":
                return self._to_bool(row.get(key))
        return None

    @staticmethod
    def _normalize_cell(value: str) -> str:
        value = str(value).strip().lower()
        value = re.sub(r"\s+", " ", value)
        value = re.sub(r"[^\w]+", "_", value, flags=re.UNICODE)
        return re.sub(r"_+", "_", value).strip("_")

    def _get_status(
        self,
        row: dict,
        keys: List[str],
        true_values: set[str],
        false_values: set[str],
    ) -> Optional[bool]:
        normalized_true_values = {self._normalize_cell(value) for value in true_values}
        normalized_false_values = {self._normalize_cell(value) for value in false_values}
        default_true_values = {"1", "true", "yes", "y", "да", "ok"}
        default_false_values = {"0", "false", "no", "n", "нет"}
        for key in keys:
            if key not in row:
                continue
            raw_value = row.get(key)
            if raw_value is None or str(raw_value).strip() == "":
                return None
            normalized = self._normalize_cell(raw_value)
            if normalized in normalized_true_values or normalized in default_true_values:
                return True
            if normalized in normalized_false_values or normalized in default_false_values:
                return False
            return None
        return None

    @staticmethod
    def _get_raw_value(row: dict, keys: List[str]) -> Optional[str]:
        for key in keys:
            if key not in row:
                continue
            raw_value = row.get(key)
            if raw_value is None or str(raw_value).strip() == "":
                return None
            return str(raw_value).strip()
        return None

    @staticmethod
    def _parse_datetime_value(value: object) -> Optional[datetime]:
        if value is None:
            return None
        text = str(value).strip()
        if not text:
            return None
        text = text.replace("\xa0", " ")
        # Common formats from Google Sheets export.
        patterns = (
            "%d.%m.%Y %H:%M:%S",
            "%d.%m.%Y %H:%M",
            "%d.%m.%Y",
            "%Y-%m-%d %H:%M:%S",
            "%Y-%m-%d %H:%M",
            "%Y-%m-%d",
            "%m/%d/%Y %H:%M:%S",
            "%m/%d/%Y %H:%M",
            "%m/%d/%Y",
        )
        for pattern in patterns:
            try:
                dt = datetime.strptime(text, pattern)
                return dt.replace(tzinfo=timezone.utc)
            except Exception:
                continue
        try:
            dt = datetime.fromisoformat(text.replace("Z", "+00:00"))
            if dt.tzinfo is None:
                dt = dt.replace(tzinfo=timezone.utc)
            return dt
        except Exception:
            return None

    def _get_datetime(self, row: dict, keys: List[str]) -> Optional[datetime]:
        for key in keys:
            if key not in row:
                continue
            parsed = self._parse_datetime_value(row.get(key))
            if parsed is not None:
                return parsed
        return None
