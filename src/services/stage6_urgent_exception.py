"""Exceções editoriais de urgência: opt-in, rastreáveis, sem publicar por conta própria.

Uma segunda publicação de carrossel no dia depende simultaneamente de flag
operacional, decisão editorial para a data/IDs e risco real <= 48 horas.
"""
from __future__ import annotations

import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo

from src.services.opportunity_guard import opportunity_gate, _parse

POLICY_FILE = Path(__file__).resolve().parents[2] / 'data' / 'excecoes_editoriais_etapa6.json'


def read_exception_policy(path: Path = POLICY_FILE) -> dict[str, Any]:
    try:
        value = json.loads(path.read_text(encoding='utf-8'))
    except (OSError, ValueError):
        return {}
    if not isinstance(value, dict) or value.get('versao') != 1:
        return {}
    return value


def feed_batches_today(history: list[dict[str, Any]], now: datetime) -> int:
    """Número de carrosséis (mídia única), não número de itens do carrossel."""
    groups: set[str] = set()
    for row in history:
        if str(row.get('status') or '').lower() != 'success':
            continue
        try:
            raw = datetime.fromisoformat(str(row.get('data_publicacao') or '').replace('Z','+00:00'))
            timestamp = raw.replace(tzinfo=now.tzinfo) if raw.tzinfo is None else raw.astimezone(now.tzinfo)
        except ValueError:
            continue
        if timestamp.date() != now.date():
            continue
        media = str(row.get('feed_media_id') or '').strip()
        message = str(row.get('mensagem') or '').lower()
        if media:
            groups.add('media:'+media)
        elif 'feed' in message:
            # Na ausência de mídia, não inferir que linhas distintas sejam o mesmo carrossel.
            groups.add('legacy:'+str(row.get('edital_id') or '')+':'+str(row.get('data_publicacao') or ''))
    return len(groups)


def select_urgent_exception(
    eligible_unpublished: list[dict[str, Any]],
    history: list[dict[str, Any]],
    now: datetime,
    daily_limit: int,
    enabled: bool,
    policy: dict[str, Any],
    timezone_name: str = 'America/Sao_Paulo',
) -> tuple[list[dict[str, Any]], str]:
    zone = ZoneInfo(timezone_name)
    now = now.replace(tzinfo=zone) if now.tzinfo is None else now.astimezone(zone)
    if not enabled:
        return [], 'excecao_desabilitada'
    if daily_limit <= 0:
        return [], 'capacidade_regular_zero'
    if not isinstance(policy, dict) or policy.get('versao') != 1:
        return [], 'politica_invalida'
    if policy.get('data') != now.date().isoformat():
        return [], 'decisao_nao_valida_para_hoje'
    if policy.get('autorizada') is not True or not str(policy.get('responsavel') or '').strip() or len(str(policy.get('justificativa') or '').strip()) < 20:
        return [], 'autorizacao_ou_justificativa_ausente'
    ids = policy.get('ids_autorizados')
    if not isinstance(ids, list) or not ids or len(ids) != len(set(map(str, ids))):
        return [], 'ids_nao_autorizados'
    if feed_batches_today(history, now) != 1:
        return [], 'exige_exatamente_um_carrossel_regular_hoje'
    # No máximo 10 itens na exceção e 1 segundo carrossel no dia.
    already = {str(row.get('edital_id') or '') for row in history
               if str(row.get('status') or '').lower() == 'success'
               and str(row.get('feed_media_id') or '').strip()}
    by_id = {str(x.get('id') or ''):x for x in eligible_unpublished}
    accepted = []
    for key in ids:
        if not isinstance(key,str) or key in already or key not in by_id:
            return [], 'item_nao_inédito_ou_ausente'
        item = by_id[key]
        allowed, _, _ = opportunity_gate(item, now=now, timezone_name=timezone_name)
        parsed = _parse(item.get('data_expiracao'), zone)
        if not allowed or not parsed:
            return [], 'item_sem_prazo_valido'
        deadline, precise = parsed
        if not precise:
            # Sem hora, vencer amanhã é o único caso seguro de urgência.
            urgent = deadline.date() == (now + timedelta(days=1)).date()
        else:
            urgent = timedelta(0) < deadline - now <= timedelta(hours=48)
        if not urgent:
            return [], 'prazo_nao_urgente'
        accepted.append(item)
    if len(accepted) > 10:
        return [], 'excede_dez_itens'
    return accepted, 'excecao_autorizada'
