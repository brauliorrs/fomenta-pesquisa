from __future__ import annotations

import hashlib
import re
import unicodedata


def slugify(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = normalized.lower()
    normalized = re.sub(r"[^a-z0-9]+", "_", normalized)
    return normalized.strip("_")


def short_hash(value: str, size: int = 6) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()[:size]
