"""Inventario completo de oportunidades sem data de inscricao — etapa 2.

Diferencia erro técnico, informação não extraída, inscrição encerrada,
retificação conflituosa e ausência de visita. Não valida abertura por inferência.
"""
from __future__ import annotations

from collections import Counter
from typing import Any

from src.services.opportunity_guard import is_listing_page


def _automatic_classification(
    item: dict[str, Any], evidence: dict[str, Any] | None,
) -> tuple[str, str, bool]:
    if is_listing_page(item.get('titulo'), item.get('link')):
        return ('pagina_agregadora_nao_e_edital', 'URL de listagem; verificar edital individual.', False)
    if item.get('bloqueio_editorial_definitivo'):
        return ('bloqueio_editorial_a_conferir', 'O edital foi excluido da auditoria automatica; revisar motivo.', False)
    if not item.get('link'):
        return ('link_ausente', 'Sem URL de documento oficial para conferencia.', False)
    if not evidence:
        return ('nao_verificado', 'Ainda nao houve leitura documentada da fonte.', False)
    state = str(evidence.get('classificacao') or '')
    if state == 'prazo_de_inscricao_ja_decorrido':
        return ('prazo_de_inscricao_encerrado', 'A fonte visitada inclui prazo de inscricao ja passado; verificar retificacoes.', True)
    if state == 'possivel_recuperacao':
        return ('prazo_localizado_revisao_humana', 'Prazo futuro extraido, mas fase e retificacoes exigem homologacao.', True)
    if state == 'prazo_hoje_horario_nao_confirmado':
        return ('prazo_hoje_sem_horario', 'Nao publicar sem hora de fechamento confirmada.', True)
    if state in {'multiplos_prazos_revisao', 'prazo_divergente'}:
        return ('datas_ambiguas', 'Prazos distintos requerem reconciliacao oficial.', True)
    if state == 'sem_evidencia_de_inscricao':
        return ('nao_extraido_do_link', 'Leitura nao encontrou prazo; isso NAO prova que o orgao omitiu a informacao.', True)
    return ('falha_de_acesso_ou_formato', f'Coleta nao concluiu: {state or "erro desconhecido"}.', True)


def build_stage2_inventory(
    editais: list[dict[str, Any]],
    audit: dict[str, Any],
    confrontos: dict[str, Any],
    checked_at: str,
) -> dict[str, Any]:
    audit_rows = audit.get('registros') or {}
    manual = (confrontos or {}).get('registros') or {}
    rows: list[dict[str, Any]] = []
    present_ids: set[str] = set()
    for item in editais:
        if item.get('data_expiracao'):
            continue
        key = str(item.get('id') or '')
        present_ids.add(key)
        evidence = audit_rows.get(key)
        # Nunca reutilizar evidência do link antigo se o catálogo foi alterado.
        if evidence and evidence.get('link_cadastrado') != item.get('link'):
            evidence = None
            stale = True
        else:
            stale = False
        category, explanation, visited = _automatic_classification(item, evidence)
        official = manual.get(key)
        if stale:
            category = 'link_alterado_requer_nova_auditoria'
            explanation = 'Documento cadastrado mudou; evidência anterior não valida o link atual.'
        if official:
            category = str(official.get('decisao') or category)
            explanation = str(official.get('fundamento') or explanation)
        rows.append({
            'id': key,
            'titulo': item.get('titulo'), 'fonte': item.get('fonte'),
            'link_catalogado': item.get('link'),
            'status': category, 'motivo': explanation,
            'origem_do_diagnostico': 'confronto_oficial' if official else 'auditoria_automatica',
            'fonte_de_evidencia': official.get('fontes_oficiais', []) if official else [],
            'data_candidata': official.get('prazo_candidato') if official else (
                (evidence.get('datas_identificadas') or [None])[-1] if evidence else None
            ),
            'fase': official.get('fase') if official else None,
            'auditoria_automatica_executada': visited,
            'ultima_verificacao_automatica': evidence.get('verificado_em') if evidence else None,
            'evidencia_extrator': (evidence.get('evidencias') or [])[:3] if evidence else [],
            'confronto_oficial': bool(official),
            'revisao_editorial_concluida': False,
            'publicacao_autorizada': False,
        })
    rows.sort(key=lambda x: (str(x['fonte'] or ''), str(x['id'])))
    historical = [
        {
            'id': key, 'titulo': value.get('titulo'),
            'status': 'fora_do_catalogo_atual_preservado_para_revisao',
            'motivo': value.get('fundamento'),
            'fontes_oficiais': value.get('fontes_oficiais', []),
            'publicacao_autorizada': False,
        }
        for key, value in sorted(manual.items()) if key not in present_ids
    ]
    counts = dict(sorted(Counter(x['status'] for x in rows).items()))
    return {
        'gerado_em': checked_at, 'etapa': 2, 'status_etapa': 'EM_ANDAMENTO',
        'metodo': 'inventario_todos_sem_prazo_com_diagnostico_sem_promocao_automatica',
        'sumario': {
            'total_catalogo': len(editais),
            'sem_prazo_atuais': len(rows),
            'linha_de_base_historica': 168,
            'com_auditoria_de_link': sum(x['auditoria_automatica_executada'] for x in rows),
            'nao_visitados_automaticamente': sum(not x['auditoria_automatica_executada'] for x in rows),
            'status_por_categoria': counts,
            'confrontos_oficiais_no_catalogo': sum(x['confronto_oficial'] for x in rows),
            'casos_historicos_fora_do_catalogo': len(historical),
            'recuperacoes_autorizadas': 0,
        },
        'registros': rows,
        'casos_historicos_fora_do_catalogo': historical,
    }
