"""Bloqueio editorial central: publicar somente oportunidades com inscricoes vigentes.

Noticias de resultados, finalistas e premiacoes nunca entram na fila.
Se o dia de encerramento nao possui horario oficial, suspender nesse dia
para evitar publicacoes depois de um prazo cuja hora real e desconhecida.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import datetime
from typing import Any

from urllib.parse import unquote, urlsplit
from zoneinfo import ZoneInfo


NOT_OPPORTUNITY = 'Noticia de resultados, finalistas ou premiacoes; nao e uma oportunidade de inscricao.'
CLOSED = 'Edital encerrado.'
UNKNOWN_DEADLINE = 'Prazo final nao identificado.'
UNKNOWN_CLOSING_TIME = 'Prazo final hoje sem horario de encerramento confirmado.'
COLLECTION_PAGE = 'Pagina agregadora de editais; nao representa oportunidade individual.'

# O titulo da fase processual importa; um edital valido pode descrever
# "resultados esperados" no resumo e nao deve ser bloqueado por isso.
POST_SELECTION = re.compile(
    r'\b(?:resultados?|finalistas?|premios?|premiac(?:ao|oes)|premiad[oa]s?|'
    r'vencedor(?:es|as)?|vencedora(?:s)?|ganhador(?:es|as)?|ganhadora(?:s)?|'
    r'contemplad[oa]s?|homologad[oa]s?|homologac(?:ao|oes)|'
    r'lista\s+(?:final|de\s+(?:aprovad[oa]s?|selecionad[oa]s?|classificad[oa]s?))|'
    r'classificacao\s+final|selecionad[oa]s?|awards?|winners?|finalists?)\b',
    re.IGNORECASE,
)
CLOSED_REGISTRATION = re.compile(
    r'\b(?:inscric(?:ao|oes)\s+(?:encerrad[ao]s?|finalizad[ao]s?|fechad[ao]s?)|'
    r'prazo\s+(?:de\s+inscric(?:ao|oes)\s+)?(?:encerrad[oa]|esgotado|finalizado)|'
    r'(?:nao\s+)?(?:recebe|aceita)\s+mais\s+inscric(?:ao|oes))\b',
    re.IGNORECASE,
)
CLOSED_STATUSES = {
    'encerrado', 'encerrada', 'fechado', 'fechada',
    'finalizado', 'finalizada', 'concluido', 'concluida',
    'resultado', 'homologado',
}


def _fold(value: Any) -> str:
    return ''.join(
        char for char in unicodedata.normalize('NFKD', str(value or '').lower())
        if not unicodedata.combining(char)
    )


# Paginas com varias oportunidades sao fontes de descoberta, nao editais.
COLLECTION_TITLE = re.compile(
    r'^(?:(?:editais|chamadas|oportunidades)\s+'
    r'(?:lancad[oa]s?|abert[oa]s?|vigentes|disponiveis|'
    r'com\s+(?:prazo|inscric(?:ao|oes)))\b|'
    r'(?:lista|relacao|catalogo|portal|pagina)\s+(?:de|dos|das)\s+'
    r'(?:editais|chamadas|oportunidades)\b)',
    re.IGNORECASE,
)
COLLECTION_URLS = re.compile(
    r'^/(?:noticias/editais-com-prazo-de-submissao-de-propostas-aberto|'
    r'editais|chamadas|oportunidades)/?$',
    re.IGNORECASE,
)


def is_listing_page(title: Any, link: Any = '') -> bool:
    if COLLECTION_TITLE.search(_fold(title).strip()):
        return True
    path = _fold(unquote(urlsplit(str(link or '')).path)).rstrip('/')
    return bool(COLLECTION_URLS.fullmatch(path))


def _parse(value: Any, timezone: ZoneInfo) -> tuple[datetime, bool] | None:
    text = str(value or '').strip()
    if not text:
        return None
    if re.fullmatch(r'\d{2}/\d{2}/\d{4}', text):
        return datetime.strptime(text, '%d/%m/%Y').replace(tzinfo=timezone), False
    try:
        parsed = datetime.fromisoformat(text.replace('Z', '+00:00'))
    except ValueError:
        return None
    has_time = 'T' in text or bool(re.search(r'\d{4}-\d{2}-\d{2}\s+\d{2}:\d{2}', text))
    parsed = parsed.replace(tzinfo=timezone) if parsed.tzinfo is None else parsed.astimezone(timezone)
    return parsed, has_time


def opportunity_gate(
    edital: dict[str, Any],
    now: datetime | None = None,
    timezone_name: str = 'America/Sao_Paulo',
) -> tuple[bool, str, bool]:
    """Retorna (pode_publicar, motivo, bloqueio_definitivo)."""
    zone = ZoneInfo(timezone_name)
    now = now or datetime.now(zone)
    now = now.replace(tzinfo=zone) if now.tzinfo is None else now.astimezone(zone)
    title = _fold(edital.get('titulo'))
    summary = _fold(edital.get('resumo'))
    status = _fold(edital.get('status')).strip()

    if is_listing_page(edital.get('titulo'), edital.get('link')):
        return False, COLLECTION_PAGE, True
    if POST_SELECTION.search(title):
        return False, NOT_OPPORTUNITY, True
    if status in CLOSED_STATUSES:
        return False, CLOSED, True
    if CLOSED_REGISTRATION.search(title) or CLOSED_REGISTRATION.search(summary):
        return False, CLOSED, True

    opening = _parse(edital.get('data_abertura'), zone)
    if opening:
        start, has_time = opening
        if (start > now) if has_time else (start.date() > now.date()):
            return False, 'Inscricoes ainda nao abertas.', False

    # A data de encerramento atualizada no catalogo e verificada a cada tentativa.
    # Nao depender de aprovacao manual da antiga etapa 2 para avaliar vigencia.
    expiration = _parse(edital.get('data_expiracao'), zone)
    if not expiration:
        reason = UNKNOWN_DEADLINE if not edital.get('data_expiracao') else 'Prazo final invalido; revisar fonte oficial.'
        return False, reason, False

    deadline, has_time = expiration
    if has_time:
        if now >= deadline:
            return False, CLOSED, True
    else:
        if now.date() > deadline.date():
            return False, CLOSED, True
        if now.date() == deadline.date():
            return False, UNKNOWN_CLOSING_TIME, False
    return True, '', False
