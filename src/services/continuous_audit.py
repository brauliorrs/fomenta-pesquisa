"""Auditoria incremental em cada exportacao das filas; nunca altera publicacao."""
from __future__ import annotations

import hashlib
import json
import os
from collections import Counter
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import urlsplit, urlunsplit

from src.services.opportunity_guard import opportunity_gate, _parse, NOT_OPPORTUNITY
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


def _deadline_evidence(path: Path) -> dict[str, dict[str, Any]]:
    """Dados de consulta acumulados, sem confundir extracao com homologacao."""
    if not path.exists():
        return {}
    data = json.loads(path.read_text(encoding='utf-8'))
    return data.get('registros', {}) if isinstance(data, dict) and isinstance(data.get('registros'), dict) else {}


def _enrich_with_evidence(
    item: dict[str, Any], row: dict[str, Any], evidence: dict[str, Any] | None,
) -> None:
    if row.get('motivo') == NOT_OPPORTUNITY:
        row['anomalias'].append('fase_resultado_ou_premiacao')
    if not evidence:
        row['auditoria_documental'] = 'sem_consulta_registrada'
        return
    if evidence.get('link_cadastrado') != item.get('link'):
        row['auditoria_documental'] = 'link_alterado_auditoria_obsoleta'
        row['anomalias'].append('link_alterado_auditoria_obsoleta')
        return
    status = str(evidence.get('classificacao') or '')
    row['auditoria_documental'] = status or 'classificacao_ausente'
    row['ultima_auditoria_documental'] = evidence.get('verificado_em')
    if status.startswith(('falha_http', 'erro_', 'falha_')) or status in ('pdf_inacessivel',):
        row['anomalias'].append('falha_acesso_documento')
    if status in ('prazo_divergente', 'multiplos_prazos_revisao'):
        row['anomalias'].append('prazo_conflitante_ou_ambiguo')
    if status == 'sem_evidencia_de_inscricao':
        row['anomalias'].append('sem_evidencia_de_inscricao')
    if status == 'prazo_de_inscricao_ja_decorrido' and row.get('decisao') == 'inedito_apto':
        row['anomalias'].append('possivel_fase_encerrada')
    if evidence.get('prazo_cadastrado') != item.get('data_expiracao'):
        row['anomalias'].append('prazo_alterado_apos_auditoria')


def run_continuous_audit(
    catalog: list[dict[str, Any]], history: list[dict[str, Any]],
    now: datetime, timezone_name: str,
    snapshot_path: Path, events_path: Path,
    *, queue1_ids: set[str] | None = None, queue2_ids: set[str] | None = None,
) -> dict[str, Any]:
    """Trilha de mudancas em JSONL e snapshot atomico; sem chamadas externas."""
    history_ids = _published_ids(history)
    previous: dict[str, str] = {}
    previous_rows: dict[str, dict[str, Any]] = {}
    if snapshot_path.exists():
        old = json.loads(snapshot_path.read_text(encoding='utf-8'))
        if not isinstance(old, dict) or old.get('schema_version') != 1:
            raise ValueError('Snapshot de auditoria corrompido')
        previous_rows = {str(row['id']):row for row in old.get('registros', [])
                         if isinstance(row,dict) and row.get('id')}
        previous = {key:str(row['fingerprint']) for key,row in previous_rows.items()}
    unique: dict[str, dict[str, Any]] = {}
    for item in catalog:
        ident = str(item.get('id') or '').strip()
        if not ident:
            continue
        prior = unique.get(ident)
        if prior is None or (_is_published(item, history_ids)
                             and not _is_published(prior, history_ids)):
            unique[ident] = item
    evidence_by_id = _deadline_evidence(snapshot_path.parent / 'auditoria_prazos.json')
    rows = []
    for ident,item in sorted(unique.items()):
        row = classify_record(item, history_ids, now, timezone_name)
        _enrich_with_evidence(item, row, evidence_by_id.get(ident))
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
    recovered = sorted(row['id'] for row in rows
                       if previous_rows.get(row['id'], {}).get('anomalias')
                       and not row['anomalias'])
    persistent = sorted(row['id'] for row in rows
                        if set(row['anomalias']) & set(
                            previous_rows.get(row['id'], {}).get('anomalias', [])))
    new_ids = sorted(ident for ident in current if ident not in previous)
    deadline_risks = []
    for row in rows:
        if row['decisao'] != 'inedito_apto':
            continue
        parsed = _parse(row.get('data_expiracao'), now.tzinfo)
        if parsed and 0 <= (parsed[0].date() - now.date()).days <= 3:
            deadline_risks.append(row['id'])
    by_source: dict[str, Counter[str]] = {}
    for row in rows:
        if row['anomalias']:
            by_source.setdefault(row['fonte'] or 'desconhecida',Counter()).update(row['anomalias'])
    failed = [row for row in history if str(row.get('status') or '').lower() == 'failed']
    summary = {
        'catalogo_distinto':len(rows),
        'novos_desde_ultimo_snapshot':len(new_ids),
        'ids_novos':new_ids,
        'auditados_documentalmente':sum(1 for row in rows if row.get('auditoria_documental') not in ('sem_consulta_registrada','link_alterado_auditoria_obsoleta')),
        'aprovados_para_fila_automatica':sum(row['decisao']=='inedito_apto' for row in rows),
        'bloqueados_ou_hold':sum(row['decisao'].startswith('HOLD') for row in rows),
        'publicados_no_catalogo':sum(row['publicado_feed'] for row in rows),
        'risco_de_expiracao_em_ate_3_dias':len(deadline_risks),
        'ids_em_risco_de_expiracao':deadline_risks,
        'falhas_recuperadas_desde_ultimo_snapshot':len(recovered),
        'ids_recuperados':recovered,
        'anomalias_persistentes_desde_ultimo_snapshot':len(persistent),
        'ids_anomalias_persistentes':persistent,
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
