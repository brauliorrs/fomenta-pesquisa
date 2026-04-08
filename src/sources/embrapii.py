from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class EMBRAPIISource(BaseSource):
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    INCLUDE_HINTS = ('chamada', 'financiamento')
    EXCLUDE_HINTS = ('resultado final', 'resultado preliminar', 'selecionam pesquisa para financiamento')
    DEADLINE_HINTS = ('submiss', 'inscri', 'prazo', 'proposta', 'consulta de elegibilidade')
    OPENING_HINTS = ('abertura', 'lançamento', 'lancamento')

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        links = self._extract_candidate_links(soup)
        items: list[dict[str, Any]] = []

        for title, link in links:
            item = self._build_item(title, link)
            if item:
                items.append(item)

        return items

    def _extract_candidate_links(self, soup: BeautifulSoup) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()
        current_year = datetime.now().year

        for anchor in soup.select('a.blue-left-block-list-link[href]'):
            title = anchor.get_text(' ', strip=True)
            href = (anchor.get('href') or '').strip()
            if not title or not href:
                continue

            lower_title = title.lower()
            if not any(hint in lower_title for hint in self.INCLUDE_HINTS):
                continue
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
                continue

            year_match = re.search(r'(20\d{2})', title)
            if year_match and int(year_match.group(1)) < current_year - 1:
                continue

            full_href = urljoin(self.config.site_oficial, href)
            if full_href in seen:
                continue

            seen.add(full_href)
            candidates.append((title, full_href))

        return candidates

    def _build_item(self, fallback_title: str, link: str) -> dict[str, Any] | None:
        soup = self._fetch_soup(link)
        if soup is None:
            return None

        title = self._extract_title(soup) or fallback_title
        summary = self._extract_summary(soup) or fallback_title
        opening_date, expiration_date = self._extract_schedule_dates(soup)

        return {
            'titulo': title,
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': 'inovacao',
            'link': link,
            'resumo': summary,
            'publico_alvo': self._infer_publico_alvo(title, summary),
            'data_abertura': opening_date,
            'data_expiracao': expiration_date,
        }

    def _fetch_soup(self, url: str) -> BeautifulSoup | None:
        try:
            response = requests.get(url, timeout=self.timeout, headers=self.USER_AGENT)
            response.raise_for_status()
        except Exception:
            return None
        return BeautifulSoup(response.text, 'html.parser')

    def _extract_title(self, soup: BeautifulSoup) -> str | None:
        title_node = soup.select_one('h1')
        if title_node:
            return title_node.get_text(' ', strip=True)
        meta_title = soup.select_one('meta[property="og:title"]')
        if meta_title and meta_title.get('content'):
            return str(meta_title.get('content')).strip()
        return None

    def _extract_summary(self, soup: BeautifulSoup) -> str | None:
        meta_description = soup.select_one('meta[property="og:description"]')
        if meta_description and meta_description.get('content'):
            return str(meta_description.get('content')).strip()

        for paragraph in soup.select('.chamadas-publicas-content p'):
            text = paragraph.get_text(' ', strip=True)
            if len(text) >= 80:
                return text
        return None

    def _extract_schedule_dates(self, soup: BeautifulSoup) -> tuple[str | None, str | None]:
        opening_date: str | None = None
        expiration_date: str | None = None

        for row in soup.select('.chamadas-publicas-content table tr'):
            cells = row.select('td, th')
            if len(cells) < 2:
                continue

            label = cells[0].get_text(' ', strip=True).lower()
            value = cells[-1].get_text(' ', strip=True)
            date_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', value)
            if not date_match:
                continue

            date_value = date_match.group(1)
            if opening_date is None and any(hint in label for hint in self.OPENING_HINTS):
                opening_date = date_value
            if expiration_date is None and any(hint in label for hint in self.DEADLINE_HINTS):
                expiration_date = date_value

        return opening_date, expiration_date

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'empresa' in combined and 'pesquisa' in combined:
            return 'Empresas, ICTs e grupos de pesquisa'
        if 'unidade' in combined or 'ict' in combined or 'competência' in combined or 'competencia' in combined:
            return 'ICTs, grupos de pesquisa e unidades de inovacao'
        return 'Instituicoes de pesquisa, empresas e pesquisadores'
