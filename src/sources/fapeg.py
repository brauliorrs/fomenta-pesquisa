from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPEGSource(BaseSource):
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    MONTHS = {
        'janeiro': 1,
        'fevereiro': 2,
        'marco': 3,
        'março': 3,
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
    EXCLUDE_NOTICE_HINTS = (
        'retifica',
        'resultado',
        'errata',
        'formulario',
        'anexo',
        'tutorial',
        'manual',
        'faq',
    )

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for row in soup.select('table tr'):
            cells = row.find_all('td')
            if len(cells) < 5:
                continue

            code = self._clean_text(cells[0].get_text(' ', strip=True))
            modalidade = self._clean_text(cells[1].get_text(' ', strip=True))
            origem = self._clean_text(cells[2].get_text(' ', strip=True))
            description = self._clean_text(cells[3].get_text(' ', strip=True))
            detail_anchor = cells[4].select_one('a[href]')
            if not code or not modalidade or not description or detail_anchor is None:
                continue

            detail_href = self._clean_text(detail_anchor.get('href'))
            if not detail_href:
                continue

            detail_url = urljoin(self.config.site_oficial, detail_href)
            item = self._build_item(code, modalidade, origem, description, detail_url)
            if not item:
                continue

            notice_url = self._clean_text(item.get('link'))
            dedupe_key = notice_url or detail_url
            if dedupe_key in seen:
                continue

            seen.add(dedupe_key)
            items.append(item)

        return items

    def _build_item(
        self,
        code: str,
        modalidade: str,
        origem: str,
        description: str,
        detail_url: str,
    ) -> dict[str, Any] | None:
        soup = self._fetch_soup(detail_url)
        title = self._build_title(code, modalidade, origem, description)
        opening_date = None
        notice_url = detail_url

        if soup is not None:
            extracted_title = self._extract_title(soup)
            if extracted_title:
                title = extracted_title
            opening_date = self._extract_opening_date(soup)
            notice_url = self._extract_notice_link(soup) or detail_url

        return {
            'titulo': title,
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': self._infer_categoria(title, description, origem),
            'link': notice_url,
            'resumo': description,
            'publico_alvo': self._infer_publico_alvo(title, description, origem),
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
        title_node = soup.select_one('h1')
        if title_node:
            return self._clean_text(title_node.get_text(' ', strip=True))
        meta_title = soup.select_one('meta[property="og:title"]')
        if meta_title and meta_title.get('content'):
            return self._clean_text(meta_title.get('content'))
        return None

    def _extract_opening_date(self, soup: BeautifulSoup) -> str | None:
        text = self._clean_text(soup.get_text('\n', strip=True))
        match = re.search(
            r'Publicado em\s+(\d{1,2})\s+([A-Za-zÀ-ÿ]+)\s+(\d{4})',
            text,
            flags=re.I,
        )
        if not match:
            return None

        month = self.MONTHS.get(match.group(2).lower())
        if month is None:
            return None
        return f'{int(match.group(1)):02d}/{month:02d}/{match.group(3)}'

    def _extract_notice_link(self, soup: BeautifulSoup) -> str | None:
        candidates: list[tuple[int, str]] = []

        for anchor in soup.select('a[href]'):
            label = self._clean_text(anchor.get_text(' ', strip=True))
            href = self._clean_text(anchor.get('href'))
            if not label or not href:
                continue

            lower_label = label.lower()
            if any(hint in lower_label for hint in self.EXCLUDE_NOTICE_HINTS):
                continue
            if 'edital' not in lower_label:
                continue

            score = 0
            if lower_label == 'edital':
                score += 5
            if lower_label.startswith('edital'):
                score += 3
            if href.lower().endswith('.pdf'):
                score += 2
            candidates.append((score, urljoin(self.config.site_oficial, href)))

        if not candidates:
            return None

        candidates.sort(key=lambda item: item[0], reverse=True)
        return candidates[0][1]

    def _build_title(self, code: str, modalidade: str, origem: str, description: str) -> str:
        origin_suffix = f' {origem}' if origem and origem.lower() not in modalidade.lower() else ''
        return self._clean_text(f'{modalidade}{origin_suffix} nº {code} - {description}')

    def _infer_categoria(self, title: str, description: str, origem: str) -> str:
        combined = f'{title} {description} {origem}'.lower()
        if 'prêmio' in combined or 'premio' in combined or 'evento' in combined:
            return 'divulgacao'
        if 'inova' in combined or 'laborat' in combined or 'tecnolog' in combined:
            return 'inovacao'
        if 'formaç' in combined or 'formac' in combined or 'mestrado' in combined or 'doutorado' in combined or 'bolsa' in combined:
            return 'bolsa'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, description: str, origem: str) -> str:
        combined = f'{title} {description} {origem}'.lower()
        if 'evento' in combined:
            return 'Pesquisadores, docentes, estudantes e instituicoes cientificas de Goias'
        if 'gestao publica' in combined or 'servidor' in combined:
            return 'Servidores publicos, pesquisadores e instituicoes do Estado de Goias'
        if 'inova' in combined or 'laborat' in combined or 'tecnolog' in combined:
            return 'Pesquisadores, ICTs, ambientes de inovacao e parceiros do ecossistema goiano'
        if 'prêmio' in combined or 'premio' in combined:
            return 'Pesquisadores, estudantes, docentes, startups e atores de ciencia e inovacao de Goias'
        return 'Pesquisadores, grupos de pesquisa e instituicoes de ciencia e tecnologia de Goias'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())
