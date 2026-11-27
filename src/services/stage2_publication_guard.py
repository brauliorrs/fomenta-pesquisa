"""Trava editorial da etapa 2: IDs do inventário nunca se liberam por flags locais.

A fonte de aprovação é um registro separado, auditável e restritivo.
Se a política ou o inventário estiver ausente/corrompido, falhar fechado.
"""
from __future__ import annotations

import json
from functools import lru_cache
from typing import Any

from src.config import DATA_DIR

HOLDS_PATH = DATA_DIR / 'holds_etapa2_20261127.json'
APPROVALS_PATH = DATA_DIR / 'homologacoes_etapa2.json'
BLOCK_REASON = 'Etapa 2: homologação editorial registrada e vinculada ao edital é obrigatória.'


@lru_cache(maxsize=1)
def stage2_ids() -> frozenset[str]:
    with HOLDS_PATH.open('r', encoding='utf-8') as handle:
        document = json.load(handle)
    rows = document.get('registro_de_decisao')
    if not isinstance(rows, list) or len(rows) != document.get('total'):
        raise ValueError('Inventário da etapa 2 incompleto ou inválido.')
    ids = [row.get('id') for row in rows if isinstance(row, dict)]
    if len(ids) != len(rows) or any(not isinstance(x, str) or not x for x in ids) or len(set(ids)) != len(ids):
        raise ValueError('IDs da etapa 2 inválidos ou duplicados.')
    return frozenset(ids)


@lru_cache(maxsize=1)
def stage2_approvals() -> dict[str, dict[str, Any]]:
    with APPROVALS_PATH.open('r', encoding='utf-8') as handle:
        document = json.load(handle)
    rows = document.get('registros')
    if document.get('versao') != 1 or not isinstance(rows, dict):
        raise ValueError('Registro de homologações da etapa 2 inválido.')
    return rows


def stage2_block_reason(edital: dict[str, Any]) -> str:
    """Para todo ID do snapshot e toda recuperação explicitamente sinalizada."""
    key = str(edital.get('id') or '')
    # Ler sempre o inventário e as aprovações: erro impede a publicação.
    try:
        tracked = key in stage2_ids()
        approvals = stage2_approvals()
    except (OSError, ValueError, TypeError, json.JSONDecodeError):
        return BLOCK_REASON
    if not tracked and not edital.get('recuperacao_etapa2'):
        return ''
    decision = approvals.get(key, {})
    if not isinstance(decision, dict):
        return BLOCK_REASON
    official_links = decision.get('fontes_oficiais')
    if not (
        decision.get('decisao') == 'HOMOLOGADO'
        and decision.get('id') == key
        and decision.get('link_catalogado') == edital.get('link')
        and decision.get('prazo_homologado') == edital.get('data_expiracao')
        and decision.get('fase')
        and decision.get('responsavel')
        and decision.get('homologado_em')
        and isinstance(official_links, list)
        and any(isinstance(link, str) and link.startswith('https://') for link in official_links)
    ):
        return BLOCK_REASON
    return ''
