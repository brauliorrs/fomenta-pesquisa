from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPTSource(BaseSource):
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    EXCLUDE_HINTS = ('resultado', 'suspenso', 'encerrad', 'retifica', 'errata')
    INCLUDE_HINTS = ('edital', 'chamada', 'inscri', 'submiss')

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for anchor in soup.select('.page_extra_links a[href]'):
            title = self._clean_text(anchor.get_text(' ', strip=True))
            href = self._clean_text(anchor.get('href'))
            if not title or not href:
                continue

            lower_title = title.lower()
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
                continue
            if not any(hint in lower_title for hint in self.INCLUDE_HINTS):
                continue

            detail_url = urljoin(self.config.site_oficial, href)
            if detail_url in seen:
                continue

            seen.add(detail_url)
            item = self._build_item(title, detail_url)
            if item:
                items.append(item)

        return items

    def _build_item(self, fallback_title: str, detail_url: str) -> dict[str, Any] | None:
        soup = self._fetch_soup(detail_url)
        title = self._extract_title(soup) if soup is not None else fallback_title
        summary = self._extract_summary(soup) if soup is not None else ''
        if not summary:
            summary = f'{fallback_title}.'

        notice_link = self._extract_notice_link(soup, detail_url) if soup is not None else detail_url
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
        for paragraph in soup.select('.page_content p, article p, main p'):
            text = self._clean_text(paragraph.get_text(' ', strip=True))
            lower = text.lower()
            if not text or any(hint in lower for hint in ('publicado em', 'compartilhe', 'voltar')):
                continue
            if len(text) >= 80:
                return text
        return ''

    def _extract_notice_link(self, soup: BeautifulSoup, detail_url: str) -> str:
        best_score = -1
        best_href = detail_url

        for anchor in soup.select('a[href]'):
            href = self._clean_text(anchor.get('href'))
            label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
            if not href:
                continue

            full_href = urljoin(detail_url, href)
            lower_href = full_href.lower()
            score = 0
            if lower_href.endswith('.pdf') or '.pdf?' in lower_href:
                score += 3
            if any(token in label for token in ('edital', 'chamada')):
                score += 4
            if any(token in label for token in ('resultado', 'retifica', 'extrato')):
                score -= 5

            if score > best_score:
                best_score = score
                best_href = full_href

        return best_href

    def _extract_opening_date(self, soup: BeautifulSoup) -> str | None:
        text = self._clean_text(soup.get_text(' ', strip=True))
        match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
        if match:
            return match.group(1)
        return None

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('evento', 'tecnico cientifico')):
            return 'divulgacao'
        if any(token in combined for token in ('inovacao', 'empresa', 'startup')):
            return 'inovacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('evento', 'tecnico cientifico')):
            return 'Pesquisadores, docentes e instituicoes cientificas do Tocantins'
        if any(token in combined for token in ('empresa', 'startup', 'inovacao')):
            return 'Empresas, empreendedores, pesquisadores e ICTs do Tocantins'
        return 'Pesquisadores, grupos de pesquisa e instituicoes cientificas do Tocantins'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        text = BeautifulSoup(str(value), 'html.parser').get_text(' ', strip=True)
        return ' '.join(text.replace('\xa0', ' ').split())
