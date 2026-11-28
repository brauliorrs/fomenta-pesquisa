"""Evidencias rastreaveis de prazos de INSCRICAO (nao datas genericas).

A rotina e conservadora: datas em noticias, resultados, eventos e
contratacoes nao justificam liberar um edital para publicacao.
"""
from __future__ import annotations

import re
import unicodedata
from datetime import date
from typing import Any


MONTHS = {
    'janeiro': 1, 'fevereiro': 2, 'marco': 3, 'abril': 4,
    'maio': 5, 'junho': 6, 'julho': 7, 'agosto': 8,
    'setembro': 9, 'outubro': 10, 'novembro': 11, 'dezembro': 12,
    'january': 1, 'february': 2, 'march': 3, 'april': 4,
    'may': 5, 'june': 6, 'july': 7, 'august': 8,
    'september': 9, 'october': 10, 'november': 11, 'december': 12,
}

DATE_TOKEN = re.compile(
    r'\b(?:'
    r'\d{1,2}/\d{1,2}/\d{4}'
    r'|\d{4}-\d{2}-\d{2}'
    r'|\d{1,2}\s+de\s+[a-z]+\s+de\s+\d{4}'
    r'|(?:january|february|march|april|may|june|july|august|'
    r'september|october|november|december)\s+\d{1,2},?\s+\d{4}'
    r')\b',
    re.IGNORECASE,
)
REGISTRATION = re.compile(
    r'\b(?:inscric(?:ao|oes)|submiss(?:ao|oes)|submeter|'
    r'candidatur(?:a|as)|'
    r'(?:recepcao|envio|entrega|apresentacao)\s+de\s+propostas?|'
    r'(?:receipt|submission)\s+of\s+proposals?|'
    r'application(?:s)?|submission(?:s)?)\b',
    re.IGNORECASE,
)
DEADLINE = re.compile(
    r'\b(?:ate|prazo|data[\s-]*limite|data[\s-]*final|'
    r'encerrament[oa]|encerra(?:m)?|termina(?:m)?|'
    r'ultimo\s+dia|deadline|closing\s+date|due\s+date)\b',
    re.IGNORECASE,
)
RANGE_END = re.compile(r'\b(?:a|ate)\s*$', re.IGNORECASE)
NEGATIVE_PHASE = re.compile(
    r'\b(?:contratac(?:ao|oes)|assinatura\s+do\s+contrato|'
    r'prestacao\s+de\s+contas|resultado(?:s)?|'
    r'homologac(?:ao|oes)|realizacao\s+(?:do|da)\s+(?:evento|feira)|'
    r'divulgacao\s+(?:do|dos|da)\s+resultado|'
    r'publicacao\s+do\s+resultado|'
    r'recursos?|contestac(?:ao|oes)|impugnac(?:ao|oes)|'
    r'inelegiv(?:el|eis)|elegiv(?:el|eis)|elegibilidade|'
    r'divulgacao\s+(?:final|preliminar)|'
    r'analise\s+de\s+merito|prestacao\s+de\s+contas|'
    r'avaliac(?:ao|oes)(?:\s+d(?:e|as|os)\s+inscric(?:ao|oes))?|'
    r'julgamento\s+d(?:e|as|os)\s+inscric(?:ao|oes))\b',
    re.IGNORECASE,
)


# Rótulos frequentes em tabelas de cronogramas (inclusive PDFs em colunas).
TABULAR_RANGE = re.compile(r'\b(?:periodo|intervalo|de\s+\d|entre\s+\d)\b', re.IGNORECASE)
TABULAR_END = re.compile(
    r'\b(?:fim|termino|data\s+final|data\s+limite|encerramento|ate)\b',
    re.IGNORECASE,
)

OPENING_PHASE = re.compile(
    r'\b(?:inicio|abertura|comeco)\s+'
    r'(?:(?:d[aeo]s?|do\s+prazo\s+para|do\s+prazo\s+de)\s+)?'
    r'(?:prazo\s+(?:de|para)\s+)?'
    r'(?:inscric(?:ao|oes)|submiss(?:ao|oes)|envio\s+de\s+propostas)\b',
    re.IGNORECASE,
)


def fold(text: Any) -> str:
    return ''.join(
        char for char in unicodedata.normalize('NFKD', str(text or '').lower())
        if not unicodedata.combining(char)
    )


def parse_date_token(token: str) -> str | None:
    normalized = fold(token).strip()
    try:
        if re.fullmatch(r'\d{4}-\d{2}-\d{2}', normalized):
            return date.fromisoformat(normalized).isoformat()
        slash = re.fullmatch(r'(\d{1,2})/(\d{1,2})/(\d{4})', normalized)
        if slash:
            day, month, year = (int(x) for x in slash.groups())
            return date(year, month, day).isoformat()
        literal = re.fullmatch(r'(\d{1,2}) de ([a-z]+) de (\d{4})', normalized)
        if literal:
            day, month_name, year = literal.groups()
            month = MONTHS.get(month_name)
            return date(int(year), month, int(day)).isoformat() if month else None
        english = re.fullmatch(r'([a-z]+) (\d{1,2}),? (\d{4})', normalized)
        if english:
            month_name, day, year = english.groups()
            month = MONTHS.get(month_name)
            return date(int(year), month, int(day)).isoformat() if month else None
    except ValueError:
        pass
    return None


def extract_registration_deadlines(text: str) -> list[dict[str, str]]:
    """Extrai somente datas com contexto explicito de inscricao/submissao.

    Nao inferir ano ausente nem assumir que a ultima data da pagina
    corresponde ao encerramento de inscricoes. Multiplas datas distintas
    permanecem multiplas para revisao humana.
    """
    original_lines = [
        re.sub(r'\s+', ' ', line).strip()
        for line in str(text or '').splitlines()
        if line and line.strip()
    ]
    found: dict[str, dict[str, str]] = {}
    prior_label = ''
    for raw_line in original_lines[:12000]:
        line = raw_line[:1500]
        normalized = fold(line)
        matches = list(DATE_TOKEN.finditer(normalized))
        if not matches:
            prior_label = line if len(line) <= 150 and REGISTRATION.search(fold(line)) else ''
            continue

        # Formatos PDF/HTML quebram um rotulo e sua data em linhas separadas.
        evidence_line = (prior_label + ' ' + line).strip() if prior_label else line
        normalized_evidence = fold(evidence_line)
        label_offset = len(fold(prior_label)) + 1 if prior_label else 0
        for m in matches:
            token = m.group(0)
            parsed = parse_date_token(token)
            if not parsed:
                continue
            # "Prazo de inscricao: 06/10 a 19/10" representa um
            # INTERVALO, nao dois encerramentos. O primeiro extremo
            # e abertura; apenas o segundo pode ser prazo final.
            following = normalized_evidence[label_offset + m.end():]
            connector = re.match(r'\s*(?:a|ate|[-–])\s+', following)
            if connector and DATE_TOKEN.match(following[connector.end():]):
                continue
            before = normalized_evidence[max(0, label_offset + m.start() - 180): label_offset + m.start()]
            registration = REGISTRATION.search(before)
            end_marker = DEADLINE.search(before) or RANGE_END.search(before)
            if not registration or not end_marker:
                continue
            # O contexto de fase deve estar no mesmo rotulo, nao misturado
            # com uma data de contratacao/resultado na linha.
            local = normalized_evidence[max(0, label_offset + m.start() - 135): label_offset + m.start()]
            if NEGATIVE_PHASE.search(local) or OPENING_PHASE.search(local):
                continue
            found.setdefault(parsed, {
                'data': parsed,
                'trecho': evidence_line[:260],
            })
        prior_label = ''
    # Complemento para cronogramas com células/linhas separadas.
    # Só considera o final do PERÍODO de inscrições ou o rótulo explícito
    # de encerramento; nunca datas de resultado, recurso ou contratação.
    for offset, raw in enumerate(original_lines[:12000]):
        normalized = fold(raw[:1500])
        if not REGISTRATION.search(normalized) or NEGATIVE_PHASE.search(normalized):
            continue
        tokens = list(DATE_TOKEN.finditer(normalized))
        if len(tokens) == 2 and (TABULAR_RANGE.search(normalized) or '|' in raw):
            first = parse_date_token(tokens[0].group(0))
            last = parse_date_token(tokens[1].group(0))
            if first and last and first < last:
                found.setdefault(last, {
                    'data':last, 'trecho':raw[:260],
                    'contexto':'termino_periodo_de_inscricao_em_tabela',
                })
        if tokens:
            continue
        # Um rótulo de fase seguido por até duas linhas/células. Não
        # atravessar título de fase nova ou captar o início das inscrições.
        for next_line in original_lines[offset + 1:offset + 3]:
            context = fold(next_line[:500])
            if NEGATIVE_PHASE.search(context) or OPENING_PHASE.search(context):
                break
            if REGISTRATION.search(context) and not TABULAR_END.search(context):
                break
            dates = list(DATE_TOKEN.finditer(context))
            if not dates:
                continue
            if re.search(r'^(?:inicio|abertura|data inicial)\b', context):
                continue
            if TABULAR_END.search(context) and len(dates) == 1:
                parsed = parse_date_token(dates[0].group(0))
                if parsed:
                    found.setdefault(parsed, {
                        'data':parsed,
                        'trecho':(raw + ' | ' + next_line)[:260],
                        'contexto':'rotulo_fim_cronograma',
                    })
            # Datas sem "fim"/"término" são ambíguas e não entram.
            break
    return sorted(found.values(), key=lambda x: x['data'])


def assess_deadline(
    edital: dict[str, Any],
    source_text: str,
    checked_at: str,
    retrieved_url: str,
) -> dict[str, Any]:
    evidences = extract_registration_deadlines(source_text)
    dates = [e['data'] for e in evidences]
    stored = str(edital.get('data_expiracao') or '').strip()[:10]
    today = date.fromisoformat(checked_at[:10]).isoformat()
    if not evidences:
        status = 'sem_evidencia_de_inscricao'
    elif max(dates) < today:
        # Mesmo com duas fases identificadas, todas as datas de submissao
        # sao anteriores a hoje. Retificacoes posteriores continuam sujeitas
        # a conferência e nunca liberam publicação automaticamente.
        status = 'prazo_de_inscricao_ja_decorrido'
    elif len(dates) > 1:
        status = 'multiplos_prazos_revisao'
    elif dates[0] == today:
        status = 'prazo_hoje_horario_nao_confirmado'
    elif stored and stored != dates[0]:
        status = 'prazo_divergente'
    elif stored:
        status = 'prazo_corroborado_por_trecho'
    else:
        status = 'possivel_recuperacao'
    return {
        'id': edital.get('id'), 'titulo': edital.get('titulo'),
        'fonte': edital.get('fonte'), 'link_cadastrado': edital.get('link'),
        'url_consultada': retrieved_url, 'verificado_em': checked_at,
        'prazo_cadastrado': stored or None,
        'datas_identificadas': dates,
        'evidencias': evidences[:5],
        'classificacao': status,
        'publicacao_autorizada_pela_auditoria': False,
        'observacao': (
            'Evidencia automatica no link cadastrado; verificar fase, '
            'documento completo, erratas e oficialidade antes de corrigir a base.'
        ),
    }
