from __future__ import annotations

from datetime import datetime

from src.utils.dates import parse_date


class RepostService:
    def should_repost(self, expiration_date: str | None, last_posted_at: str | None, now: datetime) -> bool:
        if not expiration_date:
            return last_posted_at is None

        expiration = parse_date(expiration_date)
        if expiration is None:
            return last_posted_at is None

        days_left = (expiration.date() - now.date()).days
        if days_left < 0:
            return False

        if last_posted_at is None:
            return True

        last_posted = parse_date(last_posted_at)
        if last_posted is None:
            return True

        days_since_last = (now.date() - last_posted.date()).days

        if days_left > 15:
            return days_since_last >= 7
        if 8 <= days_left <= 15:
            return days_since_last >= 4
        if 3 <= days_left <= 7:
            return days_since_last >= 2
        return days_since_last >= 1
