"""Previsão conservadora de capacidade editorial — sem acionar publicações.

Uma publicação de feed por dia, no máximo N itens inéditos por carrossel.
Não pressupõe horário de postagem em dias futuros: para segurança, só reserva
dias anteriores ao dia de encerramento. A capacidade do dia atual é potencial,
não uma promessa de postagem. Itens em HOLD nunca entram nesta previsão.
"""
from __future__ import annotations

from datetime import datetime, timedelta
from zoneinfo import ZoneInfo
from typing import Any

from src.services.opportunity_guard import _parse


def _published_today(history_rows: list[dict[str, Any]], now: datetime) -> tuple[set[str], bool]:
    ids: set[str] = set()
    feed_occurred = False
    for row in history_rows:
        if str(row.get('status') or '').lower() != 'success':
            continue
        raw = str(row.get('data_publicacao') or '').strip()
        try:
            when = datetime.fromisoformat(raw.replace('Z', '+00:00'))
            when = when.replace(tzinfo=now.tzinfo) if when.tzinfo is None else when.astimezone(now.tzinfo)
        except (ValueError, TypeError):
            continue
        if when.date() != now.date():
            continue
        # Histórico legado pode não ter IDs de mídia; a mensagem reconhece o feed.
        feed = bool(str(row.get('feed_media_id') or '').strip()) or (
            'feed' in str(row.get('mensagem') or '').lower()
        )
        if not feed:
            continue
        feed_occurred = True
        key = str(row.get('edital_id') or '').strip()
        if key:
            ids.add(key)
    return ids, feed_occurred


def forecast_capacity(
    ineditos: list[dict[str, Any]],
    history_rows: list[dict[str, Any]],
    reference_now: datetime,
    daily_limit: int,
    timezone_name: str = 'America/Sao_Paulo',
    horizon_days: int = 60,
) -> dict[str, Any]:
    """Somente prever, jamais modificar fila, datas ou volume de publicação."""
    zone = ZoneInfo(timezone_name)
    now = reference_now.replace(tzinfo=zone) if reference_now.tzinfo is None else reference_now.astimezone(zone)
    limit = max(0, int(daily_limit))
    used_ids, feed_occurred = _published_today(history_rows, now)
    today_free = max(0, limit - len(used_ids)) if not feed_occurred else 0
    # Caso um feed já tenha ocorrido hoje, não existe um segundo carrossel.
    slots = [today_free] + [limit] * max(0, horizon_days)
    scheduled: list[dict[str, Any]] = []
    risks: list[dict[str, Any]] = []
    beyond: list[str] = []
    seen: set[str] = set()
    for item in ineditos:
        key = str(item.get('id') or '').strip()
        if not key or key in seen:
            continue
        seen.add(key)
        parsed = _parse(item.get('data_expiracao'), zone)
        if not parsed:
            risks.append({'id':key, 'motivo':'prazo_invalido', 'prazo':item.get('data_expiracao')})
            continue
        deadline, precise = parsed
        # Publicação no dia do vencimento não é garantida, mesmo com horário conhecido.
        max_offset = (deadline.date() - now.date()).days - 1
        # Hoje é possível se a chamada ainda estiver aberta e houver espaço.
        eligible_today = (deadline > now if precise else deadline.date() > now.date())
        found = None
        if eligible_today and slots[0] > 0:
            found = 0
        elif max_offset >= 1:
            for day in range(1, min(max_offset, horizon_days) + 1):
                if slots[day] > 0:
                    found = day
                    break
        if found is not None:
            slots[found] -= 1
            scheduled.append({'id':key, 'data_prevista':(now.date()+timedelta(days=found)).isoformat(),
                              'prazo':item.get('data_expiracao'), 'horario_publicacao_confirmado':False})
        elif max_offset > horizon_days:
            beyond.append(key)
        else:
            risks.append({'id':key, 'motivo':'sem_vaga_antes_do_vencimento',
                          'prazo':item.get('data_expiracao')})
    return {
        'gerado_em':now.isoformat(),
        'modelo':'previsao_conservadora_um_carrossel_por_dia_sem_postagem_automatica',
        'capacidade_diaria':limit,
        'publicacoes_feed_hoje':len(used_ids),
        'carrossel_ja_publicado_hoje':feed_occurred,
        'capacidade_restante_hoje':today_free,
        'total_ineditos':len(seen),
        'previstos_no_horizonte':len(scheduled),
        'em_risco_antes_do_vencimento':len(risks),
        'itens_em_risco':risks,
        'fora_do_horizonte':len(beyond),
        'ids_fora_do_horizonte':beyond,
        'previsoes':scheduled,
        'alerta_gargalo':bool(risks),
        'horizonte_dias':horizon_days,
        'observacao':'Previsão, não agendamento. Dias futuros no próprio vencimento não são considerados sem hora comprovada de publicação.',
    }
