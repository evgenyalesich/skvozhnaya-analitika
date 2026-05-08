from __future__ import annotations

from typing import Any, Optional
from urllib.parse import unquote

UTM_PLACEHOLDERS = {
    "",
    "-",
    "—",
    "none",
    "null",
    "(none)",
    "undefined",
    "n/a",
    "na",
    "нет метки",
}

UTM_KEY_MAP = {
    "utm_source": "utm_source",
    "source": "utm_source",
    "utm_campaign": "utm_campaign",
    "campaign": "utm_campaign",
    "utm_medium": "utm_medium",
    "medium": "utm_medium",
    "utm_content": "utm_content",
    "content": "utm_content",
    "utm_term": "utm_term",
    "term": "utm_term",
}


def normalize_utm_key(raw_key: Any) -> Optional[str]:
    if not isinstance(raw_key, str):
        return None
    return UTM_KEY_MAP.get(raw_key.strip().lower())


def normalize_utm_value(raw_value: Any) -> Optional[str]:
    if raw_value is None:
        return None
    text = str(raw_value).strip()
    if not text:
        return None
    lowered = text.lower()
    if lowered in UTM_PLACEHOLDERS:
        return None
    # Single decode pass catches common encoded values from links/payloads.
    try:
        decoded = unquote(text).strip()
    except Exception:
        decoded = text
    if not decoded:
        return None
    if decoded.lower() in UTM_PLACEHOLDERS:
        return None
    return decoded


def normalize_utm_filter_values(values: list[str] | None) -> list[str]:
    normalized: list[str] = []
    for value in values or []:
        cleaned = normalize_utm_value(value)
        if cleaned:
            normalized.append(cleaned.lower())
    return sorted(set(normalized))
