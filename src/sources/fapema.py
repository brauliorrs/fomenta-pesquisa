from __future__ import annotations

import re
from typing import Any
from urllib.parse import parse_qs, urljoin, urlparse

import requests
from bs4 import BeautifulSoup, Tag

from src.sources.base_source import BaseSource


class FAPEMASource(BaseSource):
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    MAX_PAGES = 5
    DEADLINE_HINTS = (
        'periodo de submiss',
        'período de submiss',
        'prazo de inscri',
        'prazo para inscri',
        'data limite para submiss',
        'submissão on-line',
        'submissao on-line',
        'submissao online',
        'submissão online',
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

            for fallback_title, detail_url, excerpt in page_items:
                if detail_url in seen:
                    continue

                seen.add(detail_url)
                item = self._build_item(fallback_title, detail_url, excerpt)
                if item:
                    items.append(item)

            discovered_next = self._extract_next_page(soup, next_url)
            if not discovered_next or discovered_next == next_url:
                break
            next_url = discovered_next

        return items

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        page_items = self._parse_listing_page(soup)
        items: list[dict[str, Any]] = []

        for fallback_title, detail_url, excerpt in page_items:
            item = self._build_item(fallback_title, detail_url, excerpt)
            if item:
                items.append(item)

        return items

    def _parse_listing_page(self, soup: BeautifulSoup) -> list[tuple[str, str, str]]:
        items: list[tuple[str, str, str]] = []

        for article in soup.select('article'):
            heading = article.select_one('h3 a[href], h2 a[href]')
            if heading is None:
                continue

            title = self._clean_text(heading.get_text(' ', strip=True))
            href = self._clean_text(heading.get('href'))
            if not title or not href:
                continue

            excerpt = ''
            for candidate in article.select('p'):
                text = self._clean_text(candidate.get_text(' ', strip=True))
                if text and len(text) > 40:
                    excerpt = text
                    break

            items.append((title, urljoin(self.config.site_oficial, href), excerpt))

        return items

    def _build_item(self, fallback_title: str, detail_url: str, fallback_summary: str) -> dict[str, Any] | None:
        soup = self._fetch_soup(detail_url)
        if soup is None:
            return None

        title = self._extract_title(soup) or fallback_title
        summary = self._extract_summary(soup) or fallback_summary or fallback_title
        public_target = self._extract_public_target(soup) or self._infer_publico_alvo(title, summary)
        opening_date = self._extract_opening_date(soup)
        expiration_date = self._extract_expiration_date(soup)
        notice_link = self._extract_notice_link(soup) or detail_url

        return {
            'titulo': title,
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': self._infer_categoria(title, summary),
            'link': notice_link,
            'resumo': summary,
            'publico_alvo': public_target,
            'data_abertura': opening_date,
            'data_expiracao': expiration_date,
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
        title_node = soup.select_one('h1')
        if title_node:
            return self._clean_text(title_node.get_text(' ', strip=True))
        meta_title = soup.select_one('meta[property="og:title"]')
        if meta_title and meta_title.get('content'):
            return self._clean_text(meta_title.get('content'))
        return None

    def _extract_summary(self, soup: BeautifulSoup) -> str | None:
        content = soup.select_one('article, main, .entry-content, .post-content')
        if content is None:
            return None

        for paragraph in content.select('p'):
            text = self._clean_text(paragraph.get_text(' ', strip=True))
            if not text:
                continue
            lower = text.lower()
            if lower.startswith('público-alvo') or lower.startswith('publico-alvo'):
                continue
            if any(hint in lower for hint in self.DEADLINE_HINTS):
                continue
            if len(text) >= 60:
                return text
        return None

    def _extract_public_target(self, soup: BeautifulSoup) -> str | None:
        text = self._clean_text(soup.get_text('\n', strip=True))
        match = re.search(
            r'(?:PÚBLICO-ALVO|PUBLICO-ALVO)\s*(.+?)(?:ATIVIDADES|CRONOGRAMA|OBJETIVO|DISPOSIÇÕES|DISPOSICOES|$)',
            text,
            flags=re.I,
        )
        if match:
            return self._clean_text(match.group(1))
        return None

    def _extract_opening_date(self, soup: BeautifulSoup) -> str | None:
        text = self._clean_text(soup.get_text('\n', strip=True))

        numeric = re.search(r'Por\s+.+?\s+(\d{1,2}/\d{1,2}/\d{4})', text, flags=re.I)
        if numeric:
            return numeric.group(1)

        extenso = re.search(
            r'Por\s+.+?\s+(\d{1,2})\s+de\s+([A-Za-zÀ-ÿ]+)\s+de\s+(\d{4})',
            text,
            flags=re.I,
        )
        if not extenso:
            return None

        month = self._month_number(extenso.group(2))
        if month is None:
            return None
        return f'{int(extenso.group(1)):02d}/{month:02d}/{extenso.group(3)}'

    def _extract_expiration_date(self, soup: BeautifulSoup) -> str | None:
        text = self._clean_text(soup.get_text('\n', strip=True))
        lower = text.lower()
        if 'fluxo contínuo' in lower or 'fluxo continuo' in lower:
            return None

        patterns = (
            r'(?:per[ií]odo de submiss[aã]o(?: on-line| online)?|prazo de inscri[cç][aã]o)[^0-9]{0,40}(\d{1,2}/\d{1,2}/\d{4})\s*a\s*(\d{1,2}/\d{1,2}/\d{4})',
            r'(?:data limite para submiss[aã]o(?: on-line| online)?|prazo para inscri[cç][aã]o)[^0-9]{0,40}(\d{1,2}/\d{1,2}/\d{4})',
            r'at[ée]\s+o\s+dia\s+(\d{1,2}/\d{1,2}/\d{4})',
        )

        for pattern in patterns:
            match = re.search(pattern, lower, flags=re.I)
            if not match:
                continue
            if match.lastindex and match.lastindex >= 2 and match.group(2):
                return match.group(2)
            return match.group(1)

        return None

    def _extract_notice_link(self, soup: BeautifulSoup) -> str | None:
        iframe = soup.select_one('iframe[src*="file="]')
        if iframe and iframe.get('src'):
            parsed = urlparse(iframe['src'])
            file_param = parse_qs(parsed.query).get('file')
            if file_param:
                return file_param[0]

        for anchor in soup.select('a[href]'):
            href = self._clean_text(anchor.get('href'))
            label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
            if not href:
                continue
            if href.lower().endswith('.pdf') or '.pdf?' in href.lower():
                return urljoin(self.config.site_oficial, href)
            if 'edital' in label and 'fullscreen' not in label:
                return urljoin(self.config.site_oficial, href)

        return None

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'bolsa' in combined or 'residência' in combined or 'residencia' in combined or 'monitor' in combined:
            return 'bolsa'
        if 'inova' in combined or 'deep tech' in combined or 'centelha' in combined or 'startup' in combined:
            return 'inovacao'
        if 'prêmio' in combined or 'premio' in combined or 'música' in combined or 'musica' in combined:
            return 'divulgacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'startup' in combined or 'empresa' in combined or 'centelha' in combined or 'deep tech' in combined:
            return 'Empresas, startups, pesquisadores e ambientes de inovacao do Maranhao'
        if 'monitor' in combined or 'residência' in combined or 'residencia' in combined or 'bolsa' in combined:
            return 'Estudantes, bolsistas e profissionais vinculados a instituicoes do Maranhao'
        if 'prêmio' in combined or 'premio' in combined:
            return 'Pesquisadores, estudantes, docentes e profissionais de ciencia e inovacao do Maranhao'
        return 'Pesquisadores, grupos de pesquisa e instituicoes de ensino e pesquisa do Maranhao'

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
