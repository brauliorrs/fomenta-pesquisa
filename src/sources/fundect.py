from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FUNDECTSource(BaseSource):
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    MAX_PAGES = 5
    EXCLUDE_HINTS = ('encerrad', 'resultado', 'revogad', 'retifica', 'rerratifica')

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

        for article in soup.select('article'):
            heading = article.select_one('h3 a[href], h2 a[href]')
            if heading is None:
                continue

            title = self._clean_text(heading.get_text(' ', strip=True))
            href = self._clean_text(heading.get('href'))
            if not title or not href:
                continue

            lower_title = title.lower()
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
                continue

            detail_url = urljoin(self.config.site_oficial, href)
            excerpt = ''
            for paragraph in article.select('p'):
                text = self._clean_text(paragraph.get_text(' ', strip=True))
                if text and len(text) >= 40:
                    excerpt = text
                    break

            opening_date = None
            article_text = self._clean_text(article.get_text(' ', strip=True))
            date_match = re.search(r'(\d{1,2}\s+[A-Za-zÀ-ÿ]{3,}\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})', article_text, flags=re.I)
            if date_match:
                opening_date = self._normalize_date_token(date_match.group(1))

            items.append((title, detail_url, excerpt, opening_date))

        if items:
            return items

        for anchor in soup.select('a[href]'):
            title = self._clean_text(anchor.get_text(' ', strip=True))
            href = self._clean_text(anchor.get('href'))
            if not title or not href:
                continue
            lower_title = title.lower()
            if 'programa' not in lower_title and 'chamada' not in lower_title and 'edital' not in lower_title:
                continue
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
                continue
            items.append((title, urljoin(self.config.site_oficial, href), '', None))

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
        notice_link = self._extract_notice_link(soup) or detail_url
        opening = self._extract_opening_date(soup) or opening_date

        return {
            'titulo': title,
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': self._infer_categoria(title, summary),
            'link': notice_link,
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
        next_link = soup.select_one('a.next.page-numbers[href], nav.pagination a.next[href]')
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
            if lower.startswith('categorias:'):
                continue
            if 'inscrições devem ser feitas' in lower or 'inscricoes devem ser feitas' in lower:
                continue
            if len(text) >= 70:
                return text
        return None

    def _extract_opening_date(self, soup: BeautifulSoup) -> str | None:
        text = self._clean_text(soup.get_text('\n', strip=True))
        match = re.search(r'(\d{1,2}\s+[A-Za-zÀ-ÿ]{3,}\s+\d{4}|\d{1,2}/\d{1,2}/\d{4})', text, flags=re.I)
        if not match:
            return None
        return self._normalize_date_token(match.group(1))

    def _extract_notice_link(self, soup: BeautifulSoup) -> str | None:
        for anchor in soup.select('a[href]'):
            label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
            href = self._clean_text(anchor.get('href'))
            if not href:
                continue
            if 'acesse o edital' in label or 'edital' == label:
                return urljoin(self.config.site_oficial, href)
            if href.lower().endswith('.pdf') or '.pdf?' in href.lower():
                return urljoin(self.config.site_oficial, href)
        return None

    def _normalize_date_token(self, value: str) -> str | None:
        cleaned = self._clean_text(value)
        numeric = re.search(r'(\d{1,2})/(\d{1,2})/(\d{4})', cleaned)
        if numeric:
            return f'{int(numeric.group(1)):02d}/{int(numeric.group(2)):02d}/{numeric.group(3)}'

        extenso = re.search(r'(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})', cleaned, flags=re.I)
        if not extenso:
            return None
        month = self._month_number(extenso.group(2))
        if month is None:
            return None
        return f'{int(extenso.group(1)):02d}/{month:02d}/{extenso.group(3)}'

    def _month_number(self, value: str) -> int | None:
        normalized = self._normalize_text(value)
        months = {
            'janeiro': 1,
            'fevereiro': 2,
            'marco': 3,
            'abril': 4,
            'maio': 5,
            'junho': 6,
            'julho': 7,
            'agosto': 8,
            'setembro': 9,
            'outubro': 10,
            'novembro': 11,
            'dezembro': 12,
        }
        return months.get(normalized)

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'centelha' in combined or 'startup' in combined or 'subvenção' in combined or 'subvencao' in combined:
            return 'inovacao'
        if 'evento' in combined or 'premio' in combined or 'prêmio' in combined:
            return 'divulgacao'
        if 'bolsa' in combined or 'pesquisador' in combined or 'doutor' in combined:
            return 'bolsa'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'centelha' in combined or 'startup' in combined or 'empresa' in combined:
            return 'Empreendedores, startups, pesquisadores e ambientes de inovacao de Mato Grosso do Sul'
        if 'premio' in combined or 'prêmio' in combined or 'evento' in combined:
            return 'Pesquisadores, estudantes, docentes e atores do ecossistema de ciencia e tecnologia de Mato Grosso do Sul'
        if 'bolsa' in combined or 'doutor' in combined or 'pesquisador' in combined:
            return 'Pesquisadores, bolsistas e instituicoes de ensino e pesquisa de Mato Grosso do Sul'
        return 'Pesquisadores, grupos de pesquisa e instituicoes de Mato Grosso do Sul'

    def _normalize_text(self, value: Any) -> str:
        text = self._clean_text(value).lower()
        replacements = str.maketrans({
            'á': 'a',
            'à': 'a',
            'â': 'a',
            'ã': 'a',
            'é': 'e',
            'ê': 'e',
            'í': 'i',
            'ó': 'o',
            'ô': 'o',
            'õ': 'o',
            'ú': 'u',
            'ç': 'c',
        })
        return text.translate(replacements)

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())
