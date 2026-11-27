"""Relatório de cobertura e recuperação P1, gerado após cada auditoria documental.

As métricas distinguem fontes efetivamente visitadas de registros bloqueados
por regras editoriais e coleções agregadoras. Apenas diagnóstico: nunca
modifica datas, flags, filas nem decisões editoriais.
"""
from __future__ import annotations

from collections import Counter, defaultdict
from datetime import datetime
from typing import Any


NON_VISITABLE = {'bloqueio_editorial_a_conferir', 'pagina_agregadora_nao_e_edital'}
ERROR_PREFIXES = ('falha_', 'timeout_', 'documento_muito_grande', 'pdf_sem_texto_extraivel',
                  'tipo_de_documento_nao_suportado', 'imagem_nao_e_documento_textual',
                  'excesso_redirecionamentos', 'redirecionamento_de_dominio_externo')


def _is_access_error(status: Any) -> bool:
    return str(status or '').startswith(ERROR_PREFIXES)


def build_p1_operational_report(
    catalog: list[dict[str, Any]],
    previous: dict[str, Any],
    current: dict[str, Any],
    inventory: dict[str, Any],
) -> dict[str, Any]:
    catalog_by_id = {str(row.get('id')):row for row in catalog if row.get('id')}
    previous_records = previous.get('registros') or {}
    current_records = current.get('registros') or {}
    entries = inventory.get('registros') or []
    by_source = defaultdict(lambda: Counter())
    ineligible_reasons = Counter()
    unseen_eligible = []
    recovered_access = []
    newly_visited = []
    for entry in entries:
        ident = str(entry.get('id') or '')
        source = str(entry.get('fonte') or 'desconhecida')
        status = str(entry.get('status') or '')
        counts = by_source[source]
        counts['sem_prazo'] += 1
        if status in NON_VISITABLE:
            counts['excluidos_da_auditoria'] += 1
            ineligible_reasons[status] += 1
            continue
        counts['elegiveis_para_visita'] += 1
        if not entry.get('auditoria_automatica_executada'):
            counts['ainda_nao_visitados'] += 1
            unseen_eligible.append(ident)
            continue
        counts['visitados'] += 1
        if status == 'falha_de_acesso_ou_formato':
            counts['falha_de_acesso_ou_formato'] += 1
        elif status == 'nao_extraido_do_link':
            counts['sem_prazo_extraivel'] += 1
        elif status in {'prazo_de_inscricao_encerrado',
                        'inscricoes_encerradas_confirmadas_por_errata'}:
            counts['prazo_encerrado'] += 1
        elif status not in NON_VISITABLE:
            counts['outra_classificacao'] += 1

        current_row = current_records.get(ident)
        prev_row = previous_records.get(ident)
        actual_url = catalog_by_id.get(ident, {}).get('link')
        if current_row and current_row.get('link_cadastrado') == actual_url:
            if not prev_row or prev_row.get('link_cadastrado') != actual_url:
                newly_visited.append(ident)
                counts['primeira_visita_nesta_execucao'] += 1
            elif (_is_access_error(prev_row.get('classificacao'))
                  and not _is_access_error(current_row.get('classificacao'))):
                recovered_access.append(ident)
                counts['acesso_recuperado_na_execucao'] += 1

    summary = inventory.get('sumario') or {}
    return {
        'versao':1,
        'gerado_em':current.get('generated_at'),
        'escopo':'P1 operacao diagnostica; sem alteracao do catalogo ou autorizacao de publicacao',
        'baseline_sem_prazo_2026_11_27':208,
        'catalogo_total':len(catalog),
        'sem_prazo':len(entries),
        'elegiveis_para_visita':sum(v['elegiveis_para_visita'] for v in by_source.values()),
        'visitados_elegiveis':sum(v['visitados'] for v in by_source.values()),
        'pendentes_de_visita_elegiveis':len(unseen_eligible),
        'ids_pendentes_visita':sorted(unseen_eligible),
        'excluidos_da_visita_por_filtro_editorial':dict(sorted(ineligible_reasons.items())),
        'novos_links_visitados_nesta_execucao':len(newly_visited),
        'ids_primeira_visita':sorted(newly_visited),
        'falhas_de_acesso_recuperadas_nesta_execucao':len(recovered_access),
        'ids_acesso_recuperado':sorted(recovered_access),
        'erros_de_acesso_ou_formato_atuais':summary.get('status_por_categoria', {}).get(
            'falha_de_acesso_ou_formato',0),
        'fontes_sem_prazo_extraivel_atuais':summary.get('status_por_categoria', {}).get(
            'nao_extraido_do_link',0),
        'fontes':{k:dict(sorted(v.items())) for k,v in sorted(by_source.items())},
        'observacao':'Um acesso recuperado significa leitura concluída, NÃO nova inscrição vigente. Caso sem prazo extraível continua em HOLD.',
    }
