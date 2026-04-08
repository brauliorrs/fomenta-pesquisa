from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPESCSource(BaseSource):
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    DEADLINE_HINTS = (
        'prazo para submiss',
        'periodo de submiss',
        'período de submiss',
        'submissao',
        'submissão',
        'inscri',
        'manifestacao de interesse',
        'manifestação de interesse',
    )
    OPENING_HINTS = ('publicado em', 'lancamento', 'lançamento')
    COMPLETE_NOTICE_HINTS = ('acesse o edital completo', 'edital completo')

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        candidates = self._extract_candidate_links(soup)
        items: list[dict[str, Any]] = []

        for title, link in candidates:
            item = self._build_item(title, link)
            if item:
                items.append(item)

        return items

    def _extract_candidate_links(self, soup: BeautifulSoup) -> list[tuple[str, str]]:
        candidates: list[tuple[str, str]] = []
        seen: set[str] = set()

        for anchor in soup.select('h3.upk-title a[href]'):
            title = self._clean_text(anchor.get_text(' ', strip=True))
            href = self._clean_text(anchor.get('href'))
            if not title or not href:
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
        opening_date = self._extract_opening_date(soup)
        expiration_date = self._extract_expiration_date(soup)
        edital_link = self._extract_notice_link(soup) or link

        return {
            'titulo': title,
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': self._infer_categoria(title, summary),
            'link': edital_link,
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
            return self._clean_text(title_node.get_text(' ', strip=True))
        meta_title = soup.select_one('meta[property="og:title"]')
        if meta_title and meta_title.get('content'):
            return self._clean_text(meta_title.get('content'))
        return None

    def _extract_summary(self, soup: BeautifulSoup) -> str | None:
        for paragraph in soup.select('div.elementor-widget-theme-post-content p'):
            text = self._clean_text(paragraph.get_text(' ', strip=True))
            if not text:
                continue
            lower_text = text.lower()
            if lower_text.startswith('prazo para submiss') or lower_text.startswith('contato para'):
                continue
            if len(text) >= 80:
                return text

        meta_description = soup.select_one('meta[property="og:description"]')
        if meta_description and meta_description.get('content'):
            return self._clean_text(meta_description.get('content'))
        return None

    def _extract_opening_date(self, soup: BeautifulSoup) -> str | None:
        for time_node in soup.select('time'):
            text = self._clean_text(time_node.get_text(' ', strip=True))
            match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
            if match:
                return match.group(1)

        full_text = self._clean_text(soup.get_text('\n', strip=True))
        match = re.search(r'publicado em[:\s]+(\d{1,2}/\d{1,2}/\d{4})', full_text, flags=re.I)
        if match:
            return match.group(1)
        return None

    def _extract_expiration_date(self, soup: BeautifulSoup) -> str | None:
        full_text = self._clean_text(soup.get_text('\n', strip=True))
        lower_text = full_text.lower()
        if 'fluxo contínuo' in lower_text or 'fluxo continuo' in lower_text:
            return None

        for hint in self.DEADLINE_HINTS:
            pattern = rf'{hint}[^0-9]{{0,20}}(\d{{1,2}}/\d{{1,2}}/\d{{4}})(?:[^0-9]{{1,10}}a[^0-9]{{0,10}}(\d{{1,2}}/\d{{1,2}}/\d{{4}}))?'
            match = re.search(pattern, lower_text, flags=re.I)
            if match:
                return match.group(2) or match.group(1)

        matches = re.findall(r'prazo para submiss[aã]o:\s*(\d{1,2}/\d{1,2}/\d{4})\s*a\s*(\d{1,2}/\d{1,2}/\d{4})', lower_text, flags=re.I)
        if matches:
            return matches[0][1]
        return None

    def _extract_notice_link(self, soup: BeautifulSoup) -> str | None:
        for anchor in soup.select('a[href]'):
            label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
            href = self._clean_text(anchor.get('href'))
            if not href:
                continue
            if any(hint in label for hint in self.COMPLETE_NOTICE_HINTS):
                return urljoin(self.config.site_oficial, href)
        return None

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'bolsa' in combined or 'pesquisa' in combined and 'mulheres' in combined:
            return 'bolsa'
        if 'centelha' in combined or 'empreendimento' in combined or 'inov' in combined or 'propriedade intelectual' in combined:
            return 'inovacao'
        if 'clim' in combined or 'pesquisa' in combined:
            return 'pesquisa'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'mulheres+tec' in combined or 'mulheres+pesquisa' in combined:
            return 'Pesquisadoras, estudantes e empreendedoras de Santa Catarina'
        if 'centelha' in combined or 'empreendimento' in combined or 'inovacao' in combined or 'inovação' in combined:
            return 'Empresas, startups, pesquisadores e ambientes de inovacao de Santa Catarina'
        if 'propriedade intelectual' in combined or 'nucleo de inovacao tecnologica' in combined:
            return 'Nucleos de inovacao tecnologica, ICTs e pesquisadores de Santa Catarina'
        return 'Pesquisadores, grupos de pesquisa e instituicoes de Santa Catarina'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())
