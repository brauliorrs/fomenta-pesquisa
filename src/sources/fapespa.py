from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPESPASource(BaseSource):
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    MAX_PAGES = 4
    INCLUDE_HINTS = (
        'edital',
        'chamada',
        'inscri',
        'propostas',
        'submiss',
        'lança',
        'lanca',
        'abre',
        'recebe',
        'programa centelha',
        'apoiar',
    )
    EXCLUDE_HINTS = (
        'resultado',
        'workshop',
        'divulga resultado',
        'retifica',
        'rerratifica',
        'homologa',
        'lista final',
    )

    def collect(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        next_url = self.config.pagina_editais

        for _ in range(self.MAX_PAGES):
            soup = self._fetch_soup(next_url)
            if soup is None:
                break

            page_items = self._parse_listing_page(soup)
            if not page_items:
                break

            for fallback_title, detail_url, excerpt, opening_date in page_items:
                if detail_url in seen:
                    continue

                seen.add(detail_url)
                item = self._build_item(fallback_title, detail_url, excerpt, opening_date)
                if item:
                    items.append(item)

            discovered_next = self._extract_next_page(soup, next_url)
            if not discovered_next or discovered_next == next_url:
                break
            next_url = discovered_next

        return items

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []

        for fallback_title, detail_url, excerpt, opening_date in self._parse_listing_page(soup):
            item = self._build_item(fallback_title, detail_url, excerpt, opening_date)
            if item:
                items.append(item)

        return items

    def _parse_listing_page(self, soup: BeautifulSoup) -> list[tuple[str, str, str, str | None]]:
        items: list[tuple[str, str, str, str | None]] = []

        for title_node in soup.select('h2 a[href], h3 a[href]'):
            title = self._clean_text(title_node.get_text(' ', strip=True))
            href = self._clean_text(title_node.get('href'))
            if not title or not href:
                continue

            article = title_node.find_parent('article') or title_node.parent
            if article is None:
                continue

            text_blob = self._clean_text(article.get_text(' ', strip=True))
            lower_blob = text_blob.lower()
            if any(hint in lower_blob for hint in self.EXCLUDE_HINTS):
                continue
            if not any(hint in lower_blob for hint in self.INCLUDE_HINTS):
                continue

            excerpt = ''
            for paragraph in article.select('p'):
                text = self._clean_text(paragraph.get_text(' ', strip=True))
                if text and len(text) >= 50:
                    excerpt = text
                    break

            opening_date = None
            match = re.search(r'(\d{2}/\d{2}/\d{4})', text_blob)
            if match:
                opening_date = match.group(1)

            items.append((title, urljoin(self.config.site_oficial, href), excerpt, opening_date))

        return items

    def _build_item(
        self,
        fallback_title: str,
        detail_url: str,
        fallback_summary: str,
        opening_date: str | None,
    ) -> dict[str, Any] | None:
        soup = self._fetch_soup(detail_url)
        if soup is None:
            return None

        title = self._extract_title(soup) or fallback_title
        summary = self._extract_summary(soup) or fallback_summary or fallback_title
        if not self._looks_open_or_upcoming(title, summary):
            return None

        link = self._extract_notice_link(soup) or detail_url
        opening = self._extract_opening_date(soup) or opening_date

        return {
            'titulo': title,
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': self._infer_categoria(title, summary),
            'link': link,
            'resumo': summary,
            'publico_alvo': self._infer_publico_alvo(title, summary),
            'data_abertura': opening,
            'data_expiracao': None,
            'status': 'aberto',
        }

    def _fetch_soup(self, url: str) -> BeautifulSoup | None:
        try:
            response = requests.get(url, timeout=self.timeout, headers=self.USER_AGENT)
            response.raise_for_status()
        except Exception:
            return None
        return BeautifulSoup(response.text, 'html.parser')

    def _extract_next_page(self, soup: BeautifulSoup, current_url: str) -> str | None:
        next_link = soup.select_one('a.next.page-numbers[href]')
        if next_link and next_link.get('href'):
            return urljoin(current_url, next_link['href'])
        return None

    def _extract_title(self, soup: BeautifulSoup) -> str | None:
        node = soup.select_one('h1')
        if node:
            return self._clean_text(node.get_text(' ', strip=True))
        return None

    def _extract_summary(self, soup: BeautifulSoup) -> str | None:
        for paragraph in soup.select('article p, .entry-content p, main p'):
            text = self._clean_text(paragraph.get_text(' ', strip=True))
            if not text:
                continue
            lower = text.lower()
            if lower.startswith('texto:') or lower.startswith('serviço:') or lower.startswith('servico:'):
                continue
            if len(text) >= 80:
                return text
        return None

    def _extract_opening_date(self, soup: BeautifulSoup) -> str | None:
        text = self._clean_text(soup.get_text(' ', strip=True))
        match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
        if match:
            return match.group(1)
        return None

    def _extract_notice_link(self, soup: BeautifulSoup) -> str | None:
        for anchor in soup.select('a[href]'):
            href = self._clean_text(anchor.get('href'))
            label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
            if not href:
                continue
            href_lower = href.lower()
            if href_lower.endswith('.pdf') or '.pdf?' in href_lower:
                return urljoin(self.config.site_oficial, href)
            if 'edital' in label or 'chamada' in label:
                return urljoin(self.config.site_oficial, href)
            if 'programacentelha' in href_lower or 'portal.fapespa.pa.gov.br' in href_lower:
                return href
        return None

    def _looks_open_or_upcoming(self, title: str, summary: str) -> bool:
        combined = f'{title} {summary}'.lower()
        if any(hint in combined for hint in self.EXCLUDE_HINTS):
            return False
        return any(hint in combined for hint in self.INCLUDE_HINTS)

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'centelha' in combined or 'startup' in combined or 'empresa' in combined or 'bioeconom' in combined:
            return 'inovacao'
        if 'bolsa' in combined or 'cientista' in combined or 'pesquisadora' in combined or 'pesquisador' in combined:
            return 'bolsa'
        if 'evento' in combined:
            return 'divulgacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'centelha' in combined or 'startup' in combined or 'empresa' in combined:
            return 'Empreendedores, startups, pesquisadores e ambientes de inovacao do Para'
        if 'mulheres cientistas' in combined or 'pesquisadora' in combined:
            return 'Pesquisadoras vinculadas a ICTs sediadas no Para'
        if 'evento' in combined:
            return 'Pesquisadores, docentes e instituicoes cientificas do Para'
        return 'Pesquisadores, grupos de pesquisa e instituicoes do Para'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())
