from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPITECSource(BaseSource):
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    EXCLUDE_HINTS = (
        'resultado',
        'retifica',
        'retificação',
        'errata',
        'homologa',
        'lista final',
        'encerrad',
    )

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for article in soup.select('article, .post, .jeg_post'):
            heading = article.select_one('h2 a[href], h3 a[href], h4 a[href]')
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
            if detail_url in seen:
                continue

            seen.add(detail_url)
            item = self._build_item(title, detail_url, article)
            if item:
                items.append(item)

        return items

    def _build_item(self, fallback_title: str, detail_url: str, article: BeautifulSoup) -> dict[str, Any] | None:
        soup = self._fetch_soup(detail_url)
        title = self._extract_title(soup) if soup is not None else fallback_title
        summary = self._extract_summary(soup) if soup is not None else ''
        if not summary:
            summary = self._extract_listing_summary(article) or fallback_title

        if not self._looks_open_or_upcoming(title, summary):
            return None

        notice_link = self._extract_notice_link(soup) if soup is not None else None
        opening_date = self._extract_opening_date(soup) if soup is not None else None

        return {
            'titulo': title or fallback_title,
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': self._infer_categoria(title or fallback_title, summary),
            'link': notice_link or detail_url,
            'resumo': summary,
            'publico_alvo': self._infer_publico_alvo(title or fallback_title, summary),
            'data_abertura': opening_date,
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

    def _extract_title(self, soup: BeautifulSoup) -> str | None:
        node = soup.select_one('h1')
        if node:
            return self._clean_text(node.get_text(' ', strip=True))
        return None

    def _extract_summary(self, soup: BeautifulSoup) -> str:
        for paragraph in soup.select('article p, .entry-content p, main p'):
            text = self._clean_text(paragraph.get_text(' ', strip=True))
            if text and len(text) >= 80:
                return text
        return ''

    def _extract_listing_summary(self, article: BeautifulSoup) -> str:
        for paragraph in article.select('p'):
            text = self._clean_text(paragraph.get_text(' ', strip=True))
            if text and len(text) >= 50:
                return text
        return ''

    def _extract_notice_link(self, soup: BeautifulSoup) -> str | None:
        for anchor in soup.select('a[href]'):
            href = self._clean_text(anchor.get('href'))
            label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
            if not href:
                continue
            full_href = urljoin(self.config.site_oficial, href)
            lower_href = full_href.lower()
            if lower_href.endswith('.pdf') or '.pdf?' in lower_href:
                return full_href
            if any(token in label for token in ('edital', 'chamada', 'inscri')):
                return full_href
        return None

    def _extract_opening_date(self, soup: BeautifulSoup) -> str | None:
        for node in soup.select('time, .entry-date, .published'):
            text = self._clean_text(node.get_text(' ', strip=True))
            if text:
                return text
        return None

    def _looks_open_or_upcoming(self, title: str, summary: str) -> bool:
        combined = f'{title} {summary}'.lower()
        if any(hint in combined for hint in self.EXCLUDE_HINTS):
            return False
        return any(token in combined for token in ('edital', 'chamada', 'inscri', 'submiss', 'pesquisa', 'empreendedor'))

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('bolsa', 'residencia', 'residência')):
            return 'bolsa'
        if any(token in combined for token in ('inov', 'empreendedor', 'startup', 'empresa', 'centelha')):
            return 'inovacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('mulher', 'feminino', 'empreendedor', 'startup', 'empresa')):
            return 'Empreendedoras, empresas, startups, pesquisadores e ICTs de Sergipe'
        if 'bolsa' in combined:
            return 'Estudantes, bolsistas e pesquisadores vinculados a instituicoes de Sergipe'
        return 'Pesquisadores, grupos de pesquisa e instituicoes cientificas de Sergipe'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())
