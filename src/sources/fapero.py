from __future__ import annotations

from datetime import datetime
import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, Tag

from src.sources.base_source import BaseSource


class FAPEROSource(BaseSource):
    PUBLICACOES_PATTERN = re.compile(r'/publicacoes/\d{4}-\d+/?$', re.I)
    EXCLUDE_HINTS = (
        'resultado',
        'retifica',
        'retificação',
        'errata',
        'homologa',
        'encerrad',
        'demonstrativo',
    )

    def fetch(self) -> str:
        for candidate in self._candidate_urls():
            try:
                response = self.request('GET', candidate)
            except Exception:
                continue
            return response.text
        return ''

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []

        for heading in soup.select('main h2, article h2, .entry-content h2, main h3, article h3'):
            title = self._clean_text(heading.get_text(' ', strip=True))
            if not title:
                continue

            lower_title = title.lower()
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
                continue

            content_nodes = self._collect_block_nodes(heading)
            summary = self._extract_summary(content_nodes) or title
            link = self._extract_notice_link(content_nodes) or self.config.pagina_editais
            if not self._looks_open_or_upcoming(title, summary, link):
                continue

            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._infer_categoria(title, summary),
                    'link': link,
                    'resumo': summary,
                    'publico_alvo': self._infer_publico_alvo(title, summary),
                    'data_abertura': None,
                    'data_expiracao': None,
                    'status': 'aberto',
                }
            )

        return items

    def _collect_block_nodes(self, heading: Tag) -> list[Tag]:
        nodes: list[Tag] = []
        sibling = heading.find_next_sibling()
        while sibling is not None:
            if sibling.name in {'h2', 'h3'}:
                break
            if isinstance(sibling, Tag):
                nodes.append(sibling)
            sibling = sibling.find_next_sibling()
        return nodes

    def _extract_summary(self, nodes: list[Tag]) -> str:
        for node in nodes:
            text = self._clean_text(node.get_text(' ', strip=True))
            if text and len(text) >= 60:
                return text
        return ''

    def _extract_notice_link(self, nodes: list[Tag]) -> str | None:
        for node in nodes:
            for anchor in node.select('a[href]'):
                href = self._clean_text(anchor.get('href'))
                label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
                if not href:
                    continue
                full_href = urljoin(self.config.site_oficial, href)
                lower_href = full_href.lower()
                if lower_href.endswith('.pdf') or '.pdf?' in lower_href:
                    return full_href
                if any(token in label for token in ('edital', 'chamada', 'visualizar', 'abrir')):
                    return full_href
        return None

    def _looks_open_or_upcoming(self, title: str, summary: str, link: str) -> bool:
        combined = f'{title} {summary} {link}'.lower()
        if any(hint in combined for hint in self.EXCLUDE_HINTS):
            return False
        return any(token in combined for token in ('edital', 'chamada', '.pdf', 'inscri', 'pesquisa', 'programa'))

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('bolsa', 'mestrado', 'doutorado', 'pos-doutorado')):
            return 'bolsa'
        if any(token in combined for token in ('inov', 'centelha', 'empresa', 'startup')):
            return 'inovacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('empresa', 'startup', 'inov', 'centelha')):
            return 'Empresas, empreendedores, pesquisadores e ICTs de Rondonia'
        if any(token in combined for token in ('mestrado', 'doutorado', 'bolsa', 'pos-doutorado')):
            return 'Estudantes, bolsistas e pesquisadores vinculados a instituicoes de Rondonia'
        return 'Pesquisadores, grupos de pesquisa e instituicoes cientificas de Rondonia'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())

    def _candidate_urls(self) -> list[str]:
        base_url = self.config.site_oficial.rstrip('/')
        configured = self.config.pagina_editais.rstrip('/')
        current_year = datetime.now().year

        candidates = [
            configured,
            re.sub(r'/editais$', '', configured, flags=re.I),
            f'{base_url}/publicacoes/{current_year}-2',
            f'{base_url}/publicacoes/{current_year - 1}-2',
            base_url,
        ]

        seen: set[str] = set()
        normalized: list[str] = []
        for candidate in candidates:
            candidate = candidate.rstrip('/') + '/'
            if not candidate or candidate in seen:
                continue
            seen.add(candidate)
            normalized.append(candidate)
        return normalized
