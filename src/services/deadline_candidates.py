"""Pré-reconciliação de prazos: propostas rastreáveis, nunca aprovação automática.

O auditor pode reconhecer uma data em texto oficial, mas não pode garantir
sozinho público, fase e última errata. Apenas candidatos entram neste arquivo.
A reconciliação definitiva, sob HOLD, continua em recovered_deadlines.py após
registro documental validado por ID.
"""
from __future__ import annotations

from datetime import date
from typing import Any
from urllib.parse import urlsplit

from src.services.source_triage import is_clear_non_application_news
from src.services.deadline_evidence import fold

OFFICIAL_FACEPE = {'facepe.br', 'www.facepe.br', 'www2.facepe.br'}


def _same_official_origin(registered: str, retrieved: str) -> bool:
    a, b = urlsplit(registered), urlsplit(retrieved)
    if a.scheme != 'https' or b.scheme != 'https' or not a.hostname or not b.hostname:
        return False
    if a.username or a.password or b.username or b.password:
        return False
    if a.hostname.lower() == b.hostname.lower():
        return True
    return {a.hostname.lower(), b.hostname.lower()}.issubset(OFFICIAL_FACEPE)


def _phase(text: str) -> str:
    normalized = fold(text)
    if 'pre-proposta' in normalized or 'pre proposta' in normalized:
        return 'pre_proposta'
    if 'submissao' in normalized or 'submeter' in normalized:
        return 'submissao_proposta'
    if 'candidatura' in normalized:
        return 'candidatura'
    return 'inscricao'


def build_deadline_candidates(
    catalog: list[dict[str, Any]],
    audit: dict[str, Any],
    today: date,
) -> dict[str, Any]:
    """Extrai apenas datas futuras únicas, provenientes do MESMO órgão.

    Não modifica o catálogo, não preenche data_expiracao e não libera postagem.
    Datas anteriores/hoje, múltiplas, documento externo e notícia são HOLD.
    """
    audited = audit.get('registros') or {}
    result: dict[str, Any] = {}
    rejected: dict[str, int] = {}
    for item in catalog:
        ident = str(item.get('id') or '')
        record = audited.get(ident)
        if not ident or not isinstance(record, dict):
            continue
        if item.get('data_expiracao') or item.get('instagram_feed_publicado') or item.get('bloqueio_editorial_definitivo'):
            continue
        if is_clear_non_application_news(item):
            continue
        if record.get('classificacao') != 'possivel_recuperacao':
            continue
        stored_url = str(item.get('link') or '')
        retrieved = str(record.get('url_consultada') or '')
        if record.get('link_cadastrado') != stored_url or not _same_official_origin(stored_url, retrieved):
            rejected['link_ou_dominio_divergente'] = rejected.get('link_ou_dominio_divergente', 0) + 1
            continue
        dates = record.get('datas_identificadas')
        evidences = record.get('evidencias')
        if not isinstance(dates, list) or len(dates) != 1 or not isinstance(evidences, list) or not evidences:
            rejected['data_ou_evidencia_ambigua'] = rejected.get('data_ou_evidencia_ambigua', 0) + 1
            continue
        try:
            deadline = date.fromisoformat(str(dates[0]))
        except ValueError:
            rejected['formato_data_invalido'] = rejected.get('formato_data_invalido', 0) + 1
            continue
        if deadline <= today:
            continue
        excerpt = str(evidences[0].get('trecho') or '')
        if dates[0] != evidences[0].get('data') or not excerpt:
            rejected['evidencia_inconsistente'] = rejected.get('evidencia_inconsistente', 0) + 1
            continue
        result[ident] = {
            'id':ident,
            'fonte':item.get('fonte'),
            'titulo':item.get('titulo'),
            'link_catalogado':stored_url,
            'documento_consultado':retrieved,
            'prazo_candidato':deadline.isoformat(),
            'fase_inferida_a_conferir':_phase(excerpt),
            'trecho_documental':excerpt[:260],
            'ultima_verificacao':record.get('verificado_em'),
            'decisao':'AGUARDANDO_CONFIRMACAO_EDITORIAL',
            'pendencias':['comprovar_edital_e_fase','verificar_erratas_e_ultima_versao',
                          'identificar_publico_alvo','confirmar_hora_e_fuso'],
            'publicacao_autorizada':False,
            'alteracao_do_catalogo_autorizada':False,
        }
    return {
        'schema_version':1,
        'gerado_em':audit.get('generated_at'),
        'sumario':{
            'candidatos_para_validacao':len(result),
            'rejeitados_por_ambiguidade':dict(sorted(rejected.items())),
            'publicacoes_autorizadas':0,
        },
        'registros':dict(sorted(result.items())),
        'observacao':'Candidato não é prazo oficial confirmado. Apenas o ledger documental aprovado é reconciliado sob HOLD.',
    }
