from __future__ import annotations

from datetime import datetime
from zoneinfo import ZoneInfo


def now_in_timezone(timezone_name: str) -> datetime:
    return datetime.now(ZoneInfo(timezone_name))


def to_iso(dt: datetime | None) -> str | None:
    if dt is None:
        return None
    return dt.isoformat()


def parse_date(value: str | None) -> datetime | None:
    if not value:
        return None

    normalized = value.strip()
    for fmt in ("%Y-%m-%d", "%d/%m/%Y", "%Y-%m-%dT%H:%M:%S", "%Y-%m-%dT%H:%M:%S%z"):
        try:
            return datetime.strptime(normalized, fmt)
        except ValueError:
            continue

    try:
        return datetime.fromisoformat(normalized)
    except ValueError:
        return None
