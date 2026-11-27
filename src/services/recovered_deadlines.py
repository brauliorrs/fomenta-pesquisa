"""Aplicar prazos documentados sem liberar publicacoes.

A fonte de verdade para reconciliacoes dirigidas e um registro por ID, com
link atual, fonte oficial, fase e data. O resultado permanece em HOLD ate
decisao editorial especifica posterior. Nunca inferir prazos de resultados.
"""
from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit

from src.config import DATA_DIR
from src.services.opportunity_guard import _parse
from zoneinfo import ZoneInfo

LEDGER_PATH = DATA_DIR / 'prazos_recuperados_etapa2.json'
HOLD_REASON = 'Prazo recuperado: revisao editorial de fase e publico pendente.'


def read_documented_deadlines(path: Path = LEDGER_PATH) -> dict[str, Any]:
    with path.open(encoding='utf-8') as f:
        payload = json.load(f)
    if payload.get('schema_version') != 1 or not isinstance(payload.get('registros'), dict):
        raise ValueError('Registro de prazos recuperados malformado')
    return payload


def reconcile_documented_deadlines(
    editais: list[dict[str, Any]],
    ledger: dict[str, Any],
    timezone_name: str = 'America/Sao_Paulo',
) -> dict[str, int]:
    """Mutacao restritiva: recupera prazo e registra HOLD obrigatorio.

    Falha de validacao bloqueia a aplicacao da evidencia, sem presumir data.
    Nenhuma aprovacao para postagem pode ser transportada do documento.
    """
    if ledger.get('schema_version') != 1 or not isinstance(ledger.get('registros'), dict):
        raise ValueError('Registro de recuperacao invalido')
    by_id = {str(item.get('id') or ''): item for item in editais}
    counters = {'documentados': 0, 'aplicados': 0, 'links_divergentes': 0, 'invalidos': 0}
    zone = ZoneInfo(timezone_name)
    for key, record in ledger['registros'].items():
        counters['documentados'] += 1
        item = by_id.get(key)
        if item is None:
            continue
        if not isinstance(record, dict) or record.get('id') != key:
            counters['invalidos'] += 1
            continue
        if record.get('link_catalogado') != item.get('link'):
            counters['links_divergentes'] += 1
            continue
        source = str(record.get('fonte_documental') or '')
        if (urlsplit(source).scheme != 'https' or not urlsplit(source).hostname
            or not record.get('fase') or not record.get('publico_alvo')
            or record.get('decisao') != 'DOCUMENTADO_PENDENTE_LIBERACAO'):
            counters['invalidos'] += 1
            continue
        deadline = str(record.get('prazo_inscricao') or '')
        parsed = _parse(deadline, zone)
        start = _parse(record.get('inicio_inscricao'), zone)
        if not parsed or not start or parsed[0] <= start[0]:
            counters['invalidos'] += 1
            continue
        # Nao aceitar uma data posterior como alternativa sem contexto.
        secondary = str(record.get('prazo_secundario') or '')
        if secondary and (not record.get('prazo_secundario_fase')
                          or _parse(secondary, zone) is None):
            counters['invalidos'] += 1
            continue
        item['data_expiracao'] = deadline
        item['data_abertura'] = record['inicio_inscricao']
        item['prazo_fase_recuperada'] = record['fase']
        item['prazo_fonte_documental'] = source
        item['prazo_documentacao_adicional'] = secondary
        item['publico_alvo'] = record['publico_alvo']
        item['houve_prorrogacao'] = bool(record.get('houve_prorrogacao'))
        item['bloqueio_recuperacao_prazo'] = True
        item['pronto_para_postagem'] = False
        item['revisao_humana_obrigatoria'] = True
        item['motivo_bloqueio_postagem'] = HOLD_REASON
        item['pendencias_editoriais'] = [HOLD_REASON]
        # Se a chamada foi encerrada por data anterior, nao deixar status
        # incoerente com prazo retificado; porem segue bloqueada pelo HOLD.
        if item.get('status') == 'encerrado' and parsed[0] > datetime.now(zone):
            item['status'] = 'atualizado'
        counters['aplicados'] += 1
    return counters
