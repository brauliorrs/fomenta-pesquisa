"""Política editorial auditável para casos historicamente divulgados.

A fila de monitoramento preserva itens publicados; a publicação/replicação é
independentemente impedida até existir decisão explícita de liberação.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from src.config import DATA_DIR

POLICY_PATH = DATA_DIR / 'decisoes_editoriais_publicados.json'


@lru_cache(maxsize=1)
def read_published_decisions() -> dict[str, dict[str, Any]]:
    # Fail closed: quando a política de segurança falta ou está corrompida,
    # nunca assumir que o repost foi liberado.
    with POLICY_PATH.open('r', encoding='utf-8-sig') as handle:
        content = json.load(handle)
    if not isinstance(content.get('registros'), dict) or not content.get('schema_version'):
        raise ValueError('Politica editorial de publicados malformada')
    return content['registros']


def published_repost_block_reason(edital: dict[str, Any]) -> str:
    row = read_published_decisions().get(str(edital.get('id') or ''), {})
    if row and not row.get('liberar_repostagem', False):
        return (
            'Repostagem suspensa pela auditoria editorial da etapa 1: '
            + str(row.get('estado') or 'HOLD')
        )
    return ''
