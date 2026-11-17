from __future__ import annotations

from typing import Any


def prune_history_rows(history_rows: list[dict[str, Any]], active_editais: list[dict[str, Any]]) -> list[dict[str, Any]]:
    # Historico de publicacoes deve ser auditavel mesmo apos o edital expirar
    # ou ser bloqueado como noticia. Nao apagar publicacoes ja efetuadas.
    return history_rows
