"""Auditoria incremental em cada exportacao das filas; nunca altera publicacao."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from src.services.opportunity_guard import opportunity_gate
from src.services.published_editorial_guard import published_repost_block_reason


def safe_source_url(value: Any) -> str:
    try:
        parts = urlsplit(str(value or ''))
        if parts.scheme not in ('http', 'https') or not parts.hostname:
            return ''
        host = parts.hostname.lower() + ((':' + str(parts.port)) if parts.port else '')
        return urlunsplit((parts.scheme, host, parts.path, '', ''))
    except (ValueError, TypeError):
        return ''


def _published_ids(history: list[dict[str, Any]]) -> set[str]:
    return {str(row.get('edital_id') or '') for row in history
            if str(row.get('status') or '').lower() == 'success'
            and str(row.get('feed_media_id') or '').strip()}


def _is_published(item: dict[str, Any], history_ids: set[str]) -> bool:
    return bool(item.get('instagram_feed_publicado')
                or str(item.get('instagram_feed_media_id') or '').strip()
                or str(item.get('id') or '') in history_ids)


def classify_record(
    item: dict[str, Any], history_ids: set[str], now: datetime, timezone_name: str,
) -> dict[str, Any]:
    published = _is_published(item, history_ids)
    allowed, reason, definitive = opportunity_gate(item, now=now, timezone_name=timezone_name)
    repost_reason = published_repost_block_reason(item)
    if published:
        state = 'monitoramento_publicado'
        reason = repost_reason or (reason if not allowed else 'Ja publicado no feed; preservar historico.')
    elif not item.get('pronto_para_postagem'):
        state = 'HOLD_nao_pronto'
        reason = str(item.get('motivo_bloqueio_postagem') or reason or 'Nao marcado como pronto.')
    elif allowed:
        state = 'inedito_apto'
        reason = 'Prazo cadastrado vigente; apto a triagem automatica.'
    else:
        state = 'HOLD_vigencia_ou_escopo'
    source = safe_source_url(item.get('link'))
    issues = []
    if not source:
        issues.append('sem_url_fonte_valida')
    if not item.get('data_expiracao'):
        issues.append('sem_prazo')
    if 'horario' in str(reason).lower() or 'invalido' in str(reason).lower():
        issues.append('prazo_ou_horario_pendente')
    if state == 'HOLD_nao_pronto' and not item.get('motivo_bloqueio_postagem'):
        issues.append('hold_sem_motivo_detalhado')
    return {
        'id':str(item.get('id') or '').strip(),
        'fonte':str(item.get('fonte') or ''),
        'url_fonte':source,
        'data_expiracao':item.get('data_expiracao'),
        'data_ultima_coleta':item.get('data_ultima_coleta'),
        'status_catalogo':item.get('status'),
        'decisao':state, 'motivo':reason,
        'bloqueio_definitivo':bool(definitive),
        'publicado_feed':bool(published),
        'repostagem_bloqueada':bool(repost_reason),
        'anomalias':issues,
    }


def run_continuous_audit(
    catalog: list[dict[str, Any]], history: list[dict[str, Any]],
    now: datetime, timezone_name: str,
    snapshot_path: Path, events_path: Path,
    *, queue1_ids: set[str] | None = None, queue2_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Trilha de mudancas em JSONL e snapshot atomico; sem chamadas externas."""
    history_ids = _published_ids(history)
    previous: dict[str, str] = {}
    if snapshot_path.exists():
        old = json.loads(snapshot_path.read_text(encoding='utf-8'))
        if not isinstance(old, dict) or old.get('schema_version') != 1:
            raise ValueError('Snapshot de auditoria corrompido')
        previous = {str(row['id']):str(row['fingerprint'])
                    for row in old.get('registros', [])
                    if isinstance(row,dict) and row.get('id')}
    unique: dict[str, dict[str, Any]] = {}
    for item in catalog:
        ident = str(item.get('id') or '').strip()
        if not ident:
            continue
        prior = unique.get(ident)
        if prior is None or (_is_published(item, history_ids)
                             and not _is_published(prior, history_ids)):
            unique[ident] = item
    rows = []
    for ident,item in sorted(unique.items()):
        row = classify_record(item, history_ids, now, timezone_name)
        raw = json.dumps(row, ensure_ascii=False, sort_keys=True, separators=(',',':'))
        row['fingerprint'] = hashlib.sha256(raw.encode('utf-8')).hexdigest()[:20]
        rows.append(row)
    current = {row['id']:row['fingerprint'] for row in rows}
    changes = [{'em':now.isoformat(), 'tipo':'mudanca_registro', 'id':row['id'],
                'anterior':previous.get(row['id']), 'atual':row['fingerprint'],
                'decisao':row['decisao'], 'motivo':row['motivo']}
               for row in rows if previous.get(row['id']) != row['fingerprint']]
    changes += [{'em':now.isoformat(), 'tipo':'removido_do_catalogo', 'id':ident,
                 'anterior':value} for ident,value in sorted(previous.items())
                if ident not in current]
    anomalies = Counter(a for row in rows for a in row['anomalias'])
    by_source: dict[str, Counter[str]] = {}
    for row in rows:
        if row['anomalias']:
            by_source.setdefault(row['fonte'] or 'desconhecida',Counter()).update(row['anomalias'])
    failed = [row for row in history if str(row.get('status') or '').lower() == 'failed']
    summary = {
        'catalogo_distinto':len(rows),
        'situacoes':dict(sorted(Counter(row['decisao'] for row in rows).items())),
        'anomalias_por_tipo':dict(sorted(anomalies.items())),
        'anomalias_por_fonte':{key:dict(sorted(value.items()))
                              for key,value in sorted(by_source.items())},
        'falhas_de_publicacao_no_historico':len(failed),
        'ids_com_falha_de_publicacao':sorted({
            str(row.get('edital_id')) for row in failed if row.get('edital_id')
        }),
        'sobreposicoes_filas':sorted((queue1_ids or set()) & (queue2_ids or set())),
        'alteracoes_nesta_execucao':len(changes),
    }
    snapshot = {'schema_version':1,'gerado_em':now.isoformat(),
                'metodo':'auditoria_incremental_sem_alterar_publicacao',
                'sumario':summary,'registros':rows}
    snapshot_path.parent.mkdir(parents=True,exist_ok=True)
    if changes:
        events_path.parent.mkdir(parents=True,exist_ok=True)
        with events_path.open('a',encoding='utf-8') as handle:
            for event in changes:
                handle.write(json.dumps(event,ensure_ascii=False,sort_keys=True)+'\n')
    temp = snapshot_path.with_suffix(snapshot_path.suffix+'.tmp')
    try:
        temp.write_text(json.dumps(snapshot,ensure_ascii=False,indent=2)+'\n',encoding='utf-8')
        os.replace(temp,snapshot_path)
    finally:
        if temp.exists():
            temp.unlink()
    return snapshot
