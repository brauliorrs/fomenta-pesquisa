"""Auditoria diaria e conservadora de prazos no corpus Bot Editais.

O resultado e um relatorio diagnostico, nunca uma instrucao de postagem.
Nao modifica o edital original, prazos, flags nem filas de publicacao.
"""
from __future__ import annotations

import io
import ipaddress
import re
import logging
from concurrent.futures import ThreadPoolExecutor
from threading import Lock, Semaphore
from datetime import date, timedelta
from typing import Any, Callable
from urllib.parse import urljoin, urlsplit

import requests
from bs4 import BeautifulSoup
from pypdf import PdfReader

from src.services.deadline_evidence import assess_deadline, extract_registration_deadlines
from src.services.opportunity_guard import is_listing_page


class DeadlineAuditService:
    MAX_READY = 8
    MAX_MISSING = 48
    MAX_BYTES = 5_000_000
    MAX_PDF_PAGES = 14
    MAX_PDF_PAGES_SECOND_PASS = 40
    MAX_RETRIES_TRANSIENT = 1
    MAX_CONCURRENT_REQUESTS = 4
    MAX_CONCURRENT_PER_HOST = 2

    def __init__(
        self, logger: logging.Logger,
        fetch_text: Callable[[str], tuple[str, str, str]] | None = None,
    ) -> None:
        self.logger = logger
        self.fetch_text = fetch_text or self._fetch_text
        self._parallel_fetch = fetch_text is None

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

    @classmethod
    def _single_official_pdf(cls, soup: BeautifulSoup, base_url: str) -> str | None:
        """Somente um anexo PDF identificável na MESMA origem oficial.

        Páginas com vários editais ou anexos são ambíguas e não fornecem
        prazo automaticamente. Não seguir documentos externos ou imagens.
        """
        host = (urlsplit(base_url).hostname or '').lower()
        candidates: set[str] = set()
        for anchor in soup.select('a[href]'):
            label = anchor.get_text(' ', strip=True).casefold()
            if not any(term in label for term in ('edital', 'chamada', 'errata', 'retifica')):
                continue
            candidate = urljoin(base_url, str(anchor.get('href') or ''))
            parsed = urlsplit(candidate)
            if not parsed.path.lower().endswith('.pdf'):
                continue
            if (parsed.hostname or '').lower() != host or not cls.safe_url(candidate):
                continue
            candidates.add(candidate)
            if len(candidates) > 1:
                return None
        return next(iter(candidates)) if candidates else None

    def _fetch_text(self, url: str, follow_pdf: bool = True) -> tuple[str, str, str]:
        if not self.safe_url(url):
            return '', '', 'link_invalido'
        original_host = (urlsplit(url).hostname or '').lower()
        current = url
        retries = 0
        # Repetir no máximo uma vez falhas transitórias do mesmo domínio,
        # sem tentar contornar respostas 401/403, CAPTCHA ou anti-bot.
        for _ in range(5):
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
                if r.status_code in (502, 503, 504) and retries < self.MAX_RETRIES_TRANSIENT:
                    retries += 1
                    continue
                r.raise_for_status()
                if len(r.content) > self.MAX_BYTES:
                    return '', current, 'documento_muito_grande'
                ctype = str(r.headers.get('content-type') or '').lower()
                if 'pdf' in ctype or urlsplit(current).path.lower().endswith('.pdf'):
                    reader = PdfReader(io.BytesIO(r.content), strict=False)
                    pages = min(self.MAX_PDF_PAGES, len(reader.pages))
                    raw = '\n'.join((reader.pages[i].extract_text() or '') for i in range(pages))
                    # Algumas instituições põem o cronograma depois das
                    # páginas iniciais. Segunda passagem limitada a 40 páginas
                    # apenas quando a primeira não trouxe prazo de inscrição.
                    if not extract_registration_deadlines(raw) and len(reader.pages) > pages:
                        end = min(self.MAX_PDF_PAGES_SECOND_PASS, len(reader.pages))
                        raw += '\n' + '\n'.join(
                            (reader.pages[i].extract_text() or '') for i in range(pages, end)
                        )
                    return raw, current, '' if raw.strip() else 'pdf_sem_texto_extraivel'
                if ctype.startswith('image/') or urlsplit(current).path.lower().endswith(('.jpg','.jpeg','.png','.webp','.gif')):
                    return '', current, 'imagem_nao_e_documento_textual'
                if ctype and 'text/html' not in ctype and 'application/xhtml' not in ctype:
                    return '', current, 'tipo_de_documento_nao_suportado'
                soup = BeautifulSoup(r.text, 'html.parser')
                for node in soup.select('script, style, nav, footer, header'):
                    node.decompose()
                section = soup.select_one('main, article, .entry-content') or soup.body or soup
                original = section.get_text('\n', strip=True)[:600_000]
                if follow_pdf and not extract_registration_deadlines(original):
                    linked = self._single_official_pdf(section, current)
                    if linked:
                        # Não aceitar um PDF de outro órgão ou uma página
                        # agregadora contendo vários anexos de editais.
                        extended, retrieved, err = self._fetch_text(linked, follow_pdf=False)
                        if not err and extract_registration_deadlines(extended):
                            return extended, retrieved, ''
                return original, current, ''
            except requests.HTTPError as exc:
                status = exc.response.status_code if exc.response is not None else None
                self.logger.warning('HTTP %s na auditoria da URL %s', status, current)
                return '', current, f'falha_http_{status}' if status else 'falha_http_ou_documento'
            except requests.Timeout as exc:
                self.logger.warning('Timeout na auditoria do link %s: %s', current, exc)
                if retries < self.MAX_RETRIES_TRANSIENT:
                    retries += 1
                    continue
                return '', current, 'timeout_http'
            except requests.exceptions.SSLError as exc:
                self.logger.warning('Falha TLS na auditoria do link %s: %s', current, exc)
                return '', current, 'falha_tls_verificacao'
            except requests.ConnectionError as exc:
                self.logger.warning('Conexao falhou na auditoria do link %s: %s', current, exc)
                if retries < self.MAX_RETRIES_TRANSIENT:
                    retries += 1
                    continue
                return '', current, 'falha_conexao_http'
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
        # Priorizar registros nunca lidos (ou cuja URL mudou) para cobrir
        # o catalogo; somente depois repetir os que ja tiveram diagnostico.
        first_pass = [
            x for x in rotated
            if str(x.get('id')) not in prior
            or prior[str(x.get('id'))].get('link_cadastrado') != x.get('link')
        ]
        remaining = [
            x for x in rotated
            if str(x.get('id')) in prior
            and prior[str(x.get('id'))].get('link_cadastrado') == x.get('link')
        ]
        # Após cobrir links ainda não visitados, dar preferência à
        # recuperação de falhas transitórias. 403 e documentos-imagem não
        # são contornados por repetição incessante.
        transient = {'falha_http_502','falha_http_503','falha_http_504',
                     'falha_http_429','falha_conexao_http','timeout_http',
                     'falha_http_ou_documento'}
        retryable = [x for x in remaining if
                     str(prior.get(str(x.get('id')), {}).get('classificacao') or '') in transient]
        other = [x for x in remaining if x not in retryable]
        selected_missing = (first_pass + retryable + other)[:self.MAX_MISSING]
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
        ][:8]
        selected = ready_to_check + selected_missing + ambiguity_rechecks
        checked = 0
        new_recoveries = 0
        divergences = 0

        # A consulta de rede é paralelizada com teto por origem para evitar
        # que uma instituição indisponível monopolize todo o ciclo.
        # Ordem dos resultados permanece determinística para o relatório.
        if self._parallel_fetch and len(selected) > 1:
            locks = Lock()
            limits: dict[str, Semaphore] = {}

            def fetch_one(edital: dict[str, Any]) -> tuple[str, str, str]:
                url = str(edital['link']).strip()
                host = (urlsplit(url).hostname or '').lower()
                with locks:
                    if host not in limits:
                        limits[host] = Semaphore(self.MAX_CONCURRENT_PER_HOST)
                    limiter = limits[host]
                with limiter:
                    return self.fetch_text(url)

            with ThreadPoolExecutor(max_workers=self.MAX_CONCURRENT_REQUESTS) as executor:
                retrieved_rows = list(executor.map(fetch_one, selected))
        else:
            # Mantém testes e provedores injetados em ordem sequencial.
            retrieved_rows = [
                self.fetch_text(str(edital['link']).strip())
                for edital in selected
            ]
        for edital, (content, retrieved, error) in zip(selected, retrieved_rows):
            url = str(edital['link']).strip()
            checked += 1
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

        def category(error: str) -> str:
            if error in {'falha_http_502','falha_http_503','falha_http_504',
                         'falha_conexao_http','timeout_http','falha_http_429'}:
                return 'transitoria_reatentar'
            if error.startswith(('falha_http_401','falha_http_403','falha_tls')):
                return 'acesso_restrito_ou_tls'
            if error in {'tipo_de_documento_nao_suportado',
                         'imagem_nao_e_documento_textual',
                         'pdf_sem_texto_extraivel','documento_muito_grande'}:
                return 'formato_ou_documento_nao_textual'
            if error.startswith(('falha_', 'excesso_redirecionamentos')):
                return 'erro_generico_revisar'
            return ''

        recovered_access = 0
        for edital in selected:
            key = str(edital.get('id') or '')
            old = old_state.get('registros', {}).get(key, {})
            current = prior.get(key, {})
            if category(str(old.get('classificacao') or '')) and not category(
                str(current.get('classificacao') or '')
            ):
                recovered_access += 1
        failure_sources: dict[str, dict[str, int]] = {}
        for record in prior.values():
            if not isinstance(record, dict):
                continue
            error_class = category(str(record.get('classificacao') or ''))
            if error_class:
                source = str(record.get('fonte') or 'desconhecida')
                by_source = failure_sources.setdefault(source, {})
                by_source[error_class] = by_source.get(error_class, 0) + 1
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
                'falhas_por_fonte':dict(sorted(failure_sources.items())),
                'falhas_de_acesso_recuperadas_na_execucao':recovered_access,
                'registros_auditados_acumulados': len(prior),
                'classificacoes_acumuladas': dict(sorted(tally.items())),
            },
            'registros': prior,
        }
