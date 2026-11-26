"""Auditoria diaria e conservadora de prazos no corpus Bot Editais.

O resultado e um relatorio diagnostico, nunca uma instrucao de postagem.
Nao modifica o edital original, prazos, flags nem filas de publicacao.
"""
from __future__ import annotations

import io
import ipaddress
import re
import logging
from datetime import date, timedelta
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.services.deadline_evidence import assess_deadline
from src.services.opportunity_guard import is_listing_page


class DeadlineAuditService:
    MAX_READY = 8
    MAX_MISSING = 12
    MAX_BYTES = 5_000_000
    MAX_PDF_PAGES = 14

    def __init__(
        self, logger: logging.Logger,
        fetch_text: Callable[[str], tuple[str, str, str]] | None = None,
    ) -> None:
        self.logger = logger
        self.fetch_text = fetch_text or self._fetch_text

    @staticmethod
    def safe_url(url: str) -> bool:
        try:
            parts = urlsplit(str(url or '').strip())
            host = (parts.hostname or '').lower()
            if parts.scheme not in ('https', 'http') or not host:
                return False
            if parts.username or parts.password or parts.port not in (None, 80, 443):
                return False
            if host in {'localhost', '0.0.0.0'} or host.endswith(
                ('.localhost', '.local', '.internal', '.test')
            ):
                return False
            if '.' not in host:
                return False
            try:
                ipaddress.ip_address(host)
                return False
            except ValueError:
                pass
            return True
        except ValueError:
            return False

    def _fetch_text(self, url: str) -> tuple[str, str, str]:
        if not self.safe_url(url):
            return '', '', 'link_invalido'
        original_host = (urlsplit(url).hostname or '').lower()
        current = url
        for _ in range(4):
            try:
                r = requests.get(
                    current, timeout=(5, 14),
                    headers={'User-Agent': 'editais-bot-deadline-audit/1.0'},
                    allow_redirects=False,
                )
                if r.status_code in (301, 302, 303, 307, 308):
                    target = urljoin(current, r.headers.get('location', ''))
                    if (
                        not self.safe_url(target)
                        or (urlsplit(target).hostname or '').lower() != original_host
                    ):
                        return '', current, 'redirecionamento_de_dominio_externo'
                    current = target
                    continue
                r.raise_for_status()
                if len(r.content) > self.MAX_BYTES:
                    return '', current, 'documento_muito_grande'
                ctype = str(r.headers.get('content-type') or '').lower()
                if 'pdf' in ctype or urlsplit(current).path.lower().endswith('.pdf'):
                    reader = PdfReader(io.BytesIO(r.content), strict=False)
                    pages = min(self.MAX_PDF_PAGES, len(reader.pages))
                    raw = '\n'.join((reader.pages[i].extract_text() or '') for i in range(pages))
                    return raw, current, '' if raw.strip() else 'pdf_sem_texto_extraivel'
                if ctype and 'text/html' not in ctype and 'application/xhtml' not in ctype:
                    return '', current, 'tipo_de_documento_nao_suportado'
                soup = BeautifulSoup(r.text, 'html.parser')
                for node in soup.select('script, style, nav, footer, header'):
                    node.decompose()
                section = soup.select_one('main, article, .entry-content') or soup.body or soup
                return section.get_text('\n', strip=True)[:600_000], current, ''
            except (requests.RequestException, ValueError, KeyError) as exc:
                self.logger.warning('Falha de auditoria no link %s: %s', current, exc)
                return '', current, 'falha_http_ou_documento'
            except Exception as exc:
                self.logger.warning('Documento inacessivel no link %s: %s', current, exc)
                return '', current, 'falha_leitura_documento'
        return '', current, 'excesso_redirecionamentos'

    @staticmethod
    def _eligible_item(item: dict[str, Any]) -> bool:
        return bool(
            item.get('id') and item.get('link')
            and not is_listing_page(item.get('titulo'), item.get('link'))
            and not item.get('bloqueio_editorial_definitivo')
        )

    def run(
        self,
        editais: list[dict[str, Any]],
        old_state: dict[str, Any],
        now_iso: str,
    ) -> dict[str, Any]:
        now_date = date.fromisoformat(now_iso[:10])
        prior = dict(old_state.get('registros') or {})
        known = [x for x in editais if self._eligible_item(x)]
        ready = sorted(
            (
                x for x in known if x.get('data_expiracao')
                and str(x['data_expiracao'])[:10] >= now_iso[:10]
                and x.get('pronto_para_postagem')
            ),
            key=lambda x: (str(x.get('data_expiracao')), str(x.get('id'))),
        )
        # O grupo de itens sem prazo avanca por cursor. Nenhum item bloqueado
        # e descartado por nao ser considerado "promissor" pelo algoritmo.
        # Rodizio entre instituicoes: evita uma primeira amostra composta
        # quase exclusivamente por editais antigos de uma unica fonte.
        # O cursor percorre a lista COMPLETA sem descartar fontes ou datas.
        source_groups: dict[str, list[dict[str, Any]]] = {}
        for record in known:
            if not record.get('data_expiracao'):
                source_groups.setdefault(str(record.get('fonte') or ''), []).append(record)
        for records in source_groups.values():
            records.sort(key=lambda item: str(item.get('id') or ''))
        maximum_depth = max((len(group) for group in source_groups.values()), default=0)
        missing = [
            source_groups[source][offset]
            for offset in range(maximum_depth)
            for source in sorted(source_groups)
            if offset < len(source_groups[source])
        ]
        total_missing = len(missing)
        cursor = int(old_state.get('cursor_sem_prazo') or 0) % total_missing if total_missing else 0
        rotated = missing[cursor:] + missing[:cursor]
        selected_missing = rotated[:self.MAX_MISSING]
        next_cursor = (cursor + len(selected_missing)) % total_missing if total_missing else 0

        # Reavaliar prioritariamente vencimentos proximos; nao repetir o
        # mesmo registro no mesmo dia numa execucao manual.
        ready_to_check = [
            x for x in ready
            if (
                str(prior.get(x['id'], {}).get('verificado_em') or '')[:10] != now_iso[:10]
                or prior.get(x['id'], {}).get('classificacao') in {
                    'prazo_divergente', 'multiplos_prazos_revisao'
                }
            )
        ][:self.MAX_READY]
        # Reexaminar ate dois casos ambiguos fora do rodizio: uma
        # correcao do extrator nao deve manter falsos alertas por dias.
        selected_ids = {str(x.get('id')) for x in ready_to_check + selected_missing}
        ambiguity_rechecks = [
            x for x in known
            if str(x.get('id')) not in selected_ids
            and prior.get(str(x.get('id')), {}).get('classificacao')
            in {'multiplos_prazos_revisao', 'prazo_divergente'}
        ][:2]
        selected = ready_to_check + selected_missing + ambiguity_rechecks
        checked = 0
        new_recoveries = 0
        divergences = 0
        for edital in selected:
            url = str(edital['link']).strip()
            checked += 1
            content, retrieved, error = self.fetch_text(url)
            if error:
                record = {
                    'id': edital['id'], 'titulo': edital.get('titulo'),
                    'fonte': edital.get('fonte'),
                    'prazo_cadastrado': edital.get('data_expiracao'),
                    'link_cadastrado': url, 'url_consultada': retrieved,
                    'verificado_em': now_iso,
                    'classificacao': error,
                    'publicacao_autorizada_pela_auditoria': False,
                    'datas_identificadas': [], 'evidencias': [],
                }
            else:
                record = assess_deadline(edital, content, now_iso, retrieved)
            prior[str(edital['id'])] = record
            new_recoveries += record['classificacao'] == 'possivel_recuperacao'
            divergences += record['classificacao'] == 'prazo_divergente'

        tally: dict[str, int] = {}
        for row in prior.values():
            state = str(row.get('classificacao') or 'indefinida')
            tally[state] = tally.get(state, 0) + 1
        return {
            'generated_at': now_iso,
            'metodologia': 'evidencia_textual_em_link_cadastrado_sem_alterar_publicacao',
            'cursor_sem_prazo': next_cursor,
            'sumario': {
                'total_catalogo': len(editais),
                'sem_prazo_catalogados': len([x for x in editais if not x.get('data_expiracao')]),
                'sem_prazo_elegiveis_para_auditoria': total_missing,
                'triados_com_prazo_vigente': len(ready),
                'consultados_nesta_execucao': checked,
                'fontes_distintas_sem_prazo_consultadas': len({
                    str(x.get('fonte') or '') for x in selected_missing
                }),
                'revisoes_ambiguas_nesta_execucao': len(ambiguity_rechecks),
                'novos_candidatos_a_recuperacao': new_recoveries,
                'novas_divergencias': divergences,
                'registros_auditados_acumulados': len(prior),
                'classificacoes_acumuladas': dict(sorted(tally.items())),
            },
            'registros': prior,
        }
