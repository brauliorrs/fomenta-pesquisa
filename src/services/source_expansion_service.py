"""Expansao gradual do corpus de fontes de oportunidades de pesquisa.

A descoberta nao publica editais. Uma nova pagina da mesma instituicao so
entra no monitoramento apos evidencias em dois dias distintos. Links externos
ficam pendentes de revisao, sem requisicoes automaticas a seus servidores.
"""
from __future__ import annotations

import hashlib
import ipaddress
import re
import unicodedata
from dataclasses import asdict
from datetime import datetime
from typing import Any, Callable
from urllib.parse import parse_qsl, urlencode, urljoin, urlsplit, urlunsplit

import requests
from bs4 import BeautifulSoup

from src.models import SourceConfig
from src.services.opportunity_guard import POST_SELECTION, is_listing_page


class SourceExpansionService:
    HEADERS = {'User-Agent': 'editais-bot-discovery/1.0'}
    MAX_SEEDS = 20
    MAX_NEW_PAGES = 10
    MAX_PAGES_PER_SEED = 3
    MAX_VALIDATIONS = 8
    MAX_PROMOTIONS = 2
    MAX_HTML_BYTES = 1_500_000

    LISTING_LABELS = {
        'editais', 'editais abertos', 'editais em aberto', 'editais de pesquisa',
        'chamadas', 'chamadas abertas', 'chamadas publicas',
        'oportunidades', 'oportunidades de pesquisa', 'bolsas de pesquisa',
        'fomento a pesquisa', 'chamadas e editais',
    }
    LISTING_PATH = re.compile(
        r'(?:^|/)(?:editais(?:-abertos|-em-aberto)?|chamadas(?:-abertas)?|'
        r'oportunidades|bolsas-de-pesquisa|fomento)(?:/|$)',
        re.IGNORECASE,
    )
    OPPORTUNITY_TITLE = re.compile(
        r'\b(?:edital\s+(?:n[.oº°]*\s*)?\d+|'
        r'chamada(?:\s+publica)?\s+(?:n[.oº°]*\s*)?\d+|'
        r'chamada\s+de\s+propostas|processo\s+seletivo|'
        r'selecao\s+(?:de|para)\s+(?:bolsistas|projetos|pesquisadores)|'
        r'bolsas?\s+(?:de|para)\s+(?:pesquisa|mestrado|doutorado))\b',
        re.IGNORECASE,
    )
    ITEM_SELECTORS = 'article a[href], li a[href], .card a[href], .post a[href]'
    EXCLUDED_HOSTS = {'localhost', '127.0.0.1', '0.0.0.0'}
    EXCLUDED_SUFFIXES = ('.local', '.internal', '.test')
    EXCLUDED_EXTENSIONS = ('.pdf', '.doc', '.docx', '.xls', '.xlsx',
                           '.png', '.jpg', '.jpeg', '.gif', '.zip', '.mp4')
    QUERY_KEYS = {'status', 'situacao', 'filtro', 'categoria', 'category', 'tipo'}

    def __init__(
        self, logger: Any, fetch_html: Callable[[str], str] | None = None
    ) -> None:
        self.logger = logger
        self.fetch_html = fetch_html or self._fetch_html

    @staticmethod
    def fold(value: Any) -> str:
        return ''.join(
            c for c in unicodedata.normalize('NFKD', str(value or '').lower())
            if not unicodedata.combining(c)
        )

    @classmethod
    def normalized_host(cls, url: str) -> str:
        host = (urlsplit(url).hostname or '').lower()
        return host[4:] if host.startswith('www.') else host

    @classmethod
    def clean_url(cls, href: str, base: str) -> str:
        try:
            parts = urlsplit(urljoin(base, str(href or '').strip()))
            hostname = (parts.hostname or '').lower()
            if parts.scheme not in ('http', 'https') or not hostname:
                return ''
            if parts.username or parts.password or parts.port not in (None, 80, 443):
                return ''
            if hostname in cls.EXCLUDED_HOSTS or hostname.endswith(cls.EXCLUDED_SUFFIXES):
                return ''
            try:
                ipaddress.ip_address(hostname)
                return ''
            except ValueError:
                pass
            if '.' not in hostname or not re.fullmatch(r'[a-z0-9.-]+', hostname):
                return ''
            path = parts.path.rstrip('/') or '/'
            if path.lower().endswith(cls.EXCLUDED_EXTENSIONS):
                return ''
            query = urlencode([
                (k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False)
                if k.lower() in cls.QUERY_KEYS
            ])
            return urlunsplit((parts.scheme.lower(), parts.netloc.lower(), path, query, ''))
        except (ValueError, TypeError):
            return ''

    @classmethod
    def same_scope(cls, source: dict[str, Any], url: str) -> bool:
        root = str(source.get('site_oficial') or source.get('pagina_editais') or '')
        if cls.normalized_host(root) != cls.normalized_host(url):
            return False
        hostname = cls.normalized_host(root)
        original_path = urlsplit(root).path.strip('/').split('/')
        if hostname.endswith('.gov.br') or hostname == 'gov.br':
            if original_path and original_path[0]:
                return urlsplit(url).path.strip('/').split('/')[0] == original_path[0]
        return True

    @classmethod
    def is_listing_candidate(cls, title: str, url: str) -> bool:
        title_folded = cls.fold(title).strip()
        if is_listing_page(title, url) or title_folded in cls.LISTING_LABELS:
            return True
        path = urlsplit(url).path.lower().rstrip('/')
        if re.search(r'/editais?/\d{4}/(?:edital|chamada|n-)', path):
            return False
        if re.search(r'/(?:edital|chamada)[-_]?(?:n|no|n-|numero)?[-_]?\d', path):
            return False
        parts = [p for p in path.split('/') if p]
        return bool(cls.LISTING_PATH.search(path) and parts and len(parts) <= 4)

    def links_from_page(self, html: str, page_url: str) -> list[tuple[str, str]]:
        soup = BeautifulSoup(html, 'html.parser')
        found: list[tuple[str, str]] = []
        seen: set[str] = set()
        base = self.clean_url(page_url, page_url)
        for anchor in soup.select('a[href]'):
            title = anchor.get_text(' ', strip=True)[:180]
            url = self.clean_url(str(anchor.get('href') or ''), page_url)
            if not url or url == base or url in seen:
                continue
            if not self.is_listing_candidate(title, url):
                continue
            # Nao visitar destinos externos por descoberta automatica.
            if self.normalized_host(url) != self.normalized_host(page_url):
                if urlsplit(url).scheme != 'https':
                    continue
            seen.add(url)
            found.append((url, title))
        return found

    def preview_individual_calls(self, html: str, listing_url: str) -> list[str]:
        soup = BeautifulSoup(html, 'html.parser')
        good: list[str] = []
        urls: set[str] = set()
        for anchor in soup.select(self.ITEM_SELECTORS):
            title = self.fold(anchor.get_text(' ', strip=True)).strip()
            href = urljoin(listing_url, str(anchor.get('href') or ''))
            parsed = urlsplit(href)
            if parsed.scheme not in ('http', 'https') or not parsed.hostname:
                continue
            if self.is_listing_candidate(title, href) or POST_SELECTION.search(title):
                continue
            if not self.OPPORTUNITY_TITLE.search(title) or href in urls:
                continue
            urls.add(href)
            good.append(title[:140])
            if len(good) == 5:
                break
        return good

    def _fetch_html(self, url: str) -> str:
        # Redirecionamentos sao validados para impedir consulta a hosts
        # nao previamente confiaveis. O timeout limita o custo diario.
        original_host = self.normalized_host(url)
        current = url
        try:
            for _ in range(3):
                response = requests.get(
                    current, headers=self.HEADERS, timeout=(4, 12),
                    allow_redirects=False,
                )
                if response.status_code in (301, 302, 303, 307, 308):
                    next_url = self.clean_url(
                        response.headers.get('Location', ''), current
                    )
                    if not next_url or self.normalized_host(next_url) != original_host:
                        return ''
                    current = next_url
                    continue
                response.raise_for_status()
                ctype = (response.headers.get('Content-Type') or '').lower()
                if ctype and 'text/html' not in ctype and 'application/xhtml' not in ctype:
                    return ''
                if len(response.content) > self.MAX_HTML_BYTES:
                    return ''
                return response.text
        except requests.RequestException as exc:
            self.logger.warning('Falha ao consultar pagina de descoberta %s: %s', url, exc)
        return ''

    @staticmethod
    def source_id(url: str) -> str:
        return 'EXP' + hashlib.sha256(url.encode('utf-8')).hexdigest()[:10].upper()

    def make_candidate(self, source: dict[str, Any], url: str) -> dict[str, Any]:
        return {
            'segmento': 'descoberta',
            'sigla': self.source_id(url),
            'nome': f"{source.get('nome') or source.get('sigla')} - pagina adicional",
            'uf': source.get('uf') or 'BR',
            'site_oficial': source.get('site_oficial'),
            'pagina_editais_hint': url,
            'candidate_paths': [],
            'anchor_keywords': ['edital', 'chamada', 'bolsa', 'pesquisa'],
            'tipo_coleta': 'html',
            'parser': 'generic_discovery',
            'selectors': {'item': self.ITEM_SELECTORS},
            'prioridade': 'diaria',
            'estrategia': 'expansao_continua',
            'activation_mode': 'review_when_viable',
            'origem_sigla': source.get('sigla'),
        }

    def make_active_source(self, source: dict[str, Any], url: str) -> dict[str, Any]:
        return asdict(SourceConfig(
            nome=str(source.get('nome') or source.get('sigla')),
            sigla=self.source_id(url),
            sigla_publicacao=str(source.get('sigla_publicacao') or source.get('sigla')),
            uf=str(source.get('uf') or 'BR'),
            site_oficial=str(source.get('site_oficial') or ''),
            pagina_editais=url,
            tipo_coleta='html',
            ativo=True,
            parser='generic_discovery',
            selectors={'item': self.ITEM_SELECTORS},
        ))

    def scan(
        self,
        active_sources: list[dict[str, Any]],
        candidate_sources: list[dict[str, Any]],
        old_state: dict[str, Any],
        now_iso: str,
    ) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, Any]]:
        active = [dict(x) for x in active_sources]
        candidates = [dict(x) for x in candidate_sources]
        pages = {k: dict(v) for k, v in old_state.get('paginas', {}).items()}
        date = now_iso[:10]
        original_sources = [
            src for src in active if src.get('ativo', True)
            and str(src.get('pagina_editais') or '').startswith(('http://', 'https://'))
        ]
        total = len(original_sources)
        cursor = int(old_state.get('cursor', 0) or 0) % total if total else 0
        selected = (original_sources[cursor:] + original_sources[:cursor])[
            :self.MAX_SEEDS
        ]
        next_cursor = (cursor + len(selected)) % total if total else 0

        active_urls = {
            self.clean_url(str(src.get('pagina_editais') or ''), str(src.get('pagina_editais') or ''))
            for src in active
        }
        candidate_urls = {
            self.clean_url(str(src.get('pagina_editais_hint') or ''), str(src.get('pagina_editais_hint') or ''))
            for src in candidates
        }
        new_count = 0
        validated_count = 0
        activated_count = 0
        checked_count = 0
        candidates_added = 0

        for source in selected:
            seed = str(source.get('pagina_editais') or '')
            html = self.fetch_html(seed)
            checked_count += 1
            if not html:
                continue

            for url, label in self.links_from_page(html, seed)[:self.MAX_PAGES_PER_SEED]:
                if url in active_urls:
                    continue
                if url not in pages and new_count >= self.MAX_NEW_PAGES:
                    continue

                record = pages.get(url)
                if record is None:
                    new_count += 1
                    record = {
                        'url': url, 'titulo_detectado': label,
                        'origem_sigla': source.get('sigla'), 'origem_pagina': seed,
                        'primeira_deteccao': now_iso,
                        'observacoes': 0, 'validacoes': 0,
                        'exemplos': [],
                    }
                    pages[url] = record

                if record.get('ultima_data_observada') != date:
                    record['observacoes'] = int(record.get('observacoes', 0)) + 1
                    record['ultima_data_observada'] = date
                record['ultima_deteccao'] = now_iso
                trusted = self.same_scope(source, url)
                record['mesma_instituicao'] = trusted

                if not trusted:
                    record['status'] = 'externa_pendente_revisao'
                    continue

                if record.get('ultima_data_validada') != date and validated_count < self.MAX_VALIDATIONS:
                    validated_count += 1
                    candidate_html = self.fetch_html(url)
                    examples = self.preview_individual_calls(candidate_html, url) if candidate_html else []
                    if len(examples) >= 2:
                        record['validacoes'] = int(record.get('validacoes', 0)) + 1
                        record['exemplos'] = examples
                    record['ultima_data_validada'] = date

                if int(record.get('validacoes', 0)) >= 1 and url not in candidate_urls:
                    if candidates_added < self.MAX_NEW_PAGES:
                        candidates.append(self.make_candidate(source, url))
                        candidate_urls.add(url)
                        candidates_added += 1

                if (
                    int(record.get('observacoes', 0)) >= 2
                    and int(record.get('validacoes', 0)) >= 2
                    and activated_count < self.MAX_PROMOTIONS
                    and url not in active_urls
                ):
                    new_source = self.make_active_source(source, url)
                    if new_source['sigla'] not in {x.get('sigla') for x in active}:
                        active.append(new_source)
                        active_urls.add(url)
                        activated_count += 1
                        record['status'] = 'integrada_auto'
                        self.logger.info('Nova pagina de pesquisa integrada: %s', url)
                elif url in active_urls:
                    record['status'] = 'integrada_auto'
                elif int(record.get('validacoes', 0)) >= 1:
                    record['status'] = 'verificada_em_observacao'
                else:
                    record['status'] = 'aguardando_evidencias'

        state = {
            'generated_at': now_iso,
            'cursor': next_cursor,
            'paginas': pages,
            'sumario': {
                'fontes_visitadas': checked_count,
                'paginas_novas': new_count,
                'paginas_verificadas': validated_count,
                'candidatas_adicionadas': candidates_added,
                'fontes_auto_integradas': activated_count,
                'paginas_catalogadas': len(pages),
                'externas_pendentes_revisao': sum(
                    p.get('status') == 'externa_pendente_revisao'
                    for p in pages.values()
                ),
                'fontes_ativas_total': len(active),
            },
        }
        return active, candidates, state
