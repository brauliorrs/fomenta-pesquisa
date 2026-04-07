from __future__ import annotations

from typing import Any


def prune_history_rows(history_rows: list[dict[str, Any]], active_editais: list[dict[str, Any]]) -> list[dict[str, Any]]:
    active_ids = {str(edital.get('id', '')).strip() for edital in active_editais if str(edital.get('id', '')).strip()}
    if not active_ids:
        return []
    return [row for row in history_rows if str(row.get('edital_id', '')).strip() in active_ids]
