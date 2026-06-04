"""Serialize DB timestamps as UTC ISO-8601 for the dashboard (display only)."""
from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def format_ts_for_api(value: Any) -> str | None:
    """Naive SQLite/Postgres values are treated as UTC; output ends with Z."""
    if value is None:
        return None
    if isinstance(value, datetime):
        dt = value
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        else:
            dt = dt.astimezone(timezone.utc)
        return dt.strftime("%Y-%m-%dT%H:%M:%SZ")
    s = str(value).strip()
    if not s:
        return None
    if "T" in s and (s.endswith("Z") or "+" in s[10:]):
        return s
    base = s.replace(" ", "T").split(".")[0]
    return f"{base}Z"
