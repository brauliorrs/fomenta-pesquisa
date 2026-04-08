from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from src.sources.base_source import BaseSource


class FAPEMATSource(BaseSource):
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    MONTHS = {
        'january': 1,
        'february': 2,
        'march': 3,
        'april': 4,
        'may': 5,
        'june': 6,
        'july': 7,
        'august': 8,
        'september': 9,
        'october': 10,
        'november': 11,
        'december': 12,
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
    DETAIL_TITLE_HINTS = ('edital', 'chamada', 'programa')
    EXCLUDE_HINTS = ('encerrad', 'resultado', 'retifica', 'rerratifica', 'oculto')

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for anchor in soup.select('h3 a[href], h2 a[href], h4 a[href]'):
            title = self._clean_text(anchor.get_text(' ', strip=True))
            href = self._clean_text(anchor.get('href'))
            if not title or not href:
                continue

            lower_title = title.lower()
            if not any(hint in lower_title for hint in self.DETAIL_TITLE_HINTS):
                continue
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
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
        if soup is None:
            return None

        title = self._extract_title(soup) or fallback_title
        summary = self._extract_summary(soup) or fallback_title
        opening_date = self._extract_opening_date(soup)
        notice_link = self._extract_notice_link(soup) or detail_url

        return {
            'titulo': title,
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': self._infer_categoria(title, summary),
            'link': notice_link,
            'resumo': summary,
            'publico_alvo': self._infer_publico_alvo(title, summary),
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
        for selector in ('h1', 'h2', 'h3'):
            node = soup.select_one(selector)
            if not node:
                continue
            text = self._clean_text(node.get_text(' ', strip=True))
            if text and any(hint in text.lower() for hint in self.DETAIL_TITLE_HINTS):
                return text
        return None

    def _extract_summary(self, soup: BeautifulSoup) -> str | None:
        main_text = self._clean_text(soup.get_text('\n', strip=True))
        match = re.search(
            r'Segue em\s+ANEXO\s+o\s+(.+?)(?:Arquivo\(s\) anexado\(s\)|Serviços|Contatos|$)',
            main_text,
            flags=re.I,
        )
        if match:
            return self._clean_text(match.group(1))

        for paragraph in soup.select('p'):
            text = self._clean_text(paragraph.get_text(' ', strip=True))
            if text and len(text) >= 60:
                return text
        return None

    def _extract_opening_date(self, soup: BeautifulSoup) -> str | None:
        text = self._clean_text(soup.get_text('\n', strip=True))
        numeric = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
        if numeric:
            return numeric.group(1)

        extenso = re.search(r'(\d{1,2}) de ([A-Za-zÀ-ÿ]+) de (\d{4})', text, flags=re.I)
        if not extenso:
            return None
        month = self.MONTHS.get(self._normalize_text(extenso.group(2)))
        if month is None:
            return None
        return f'{int(extenso.group(1)):02d}/{month:02d}/{extenso.group(3)}'

    def _extract_notice_link(self, soup: BeautifulSoup) -> str | None:
        attached_section = None
        for heading in soup.select('h4, h5, strong, b'):
            text = self._clean_text(heading.get_text(' ', strip=True)).lower()
            if 'arquivo' in text and 'anexado' in text:
                attached_section = heading.parent if isinstance(heading.parent, Tag) else heading
                break

        search_root = attached_section or soup
        for anchor in search_root.select('a[href]'):
            href = self._clean_text(anchor.get('href'))
            label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
            if not href:
                continue
            if any(hint in label for hint in ('edital', 'anexo', 'chamada')):
                return urljoin(self.config.site_oficial, href)
            if href.lower().endswith('.pdf') or '.pdf?' in href.lower():
                return urljoin(self.config.site_oficial, href)
        return None

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'sus' in combined or 'saude' in combined or 'saúde' in combined:
            return 'pesquisa'
        if 'inova' in combined or 'tecnolog' in combined:
            return 'inovacao'
        if 'bolsa' in combined or 'pesquisador' in combined:
            return 'bolsa'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'sus' in combined or 'saude' in combined or 'saúde' in combined:
            return 'Pesquisadores, gestores e instituicoes de saude de Mato Grosso'
        if 'inova' in combined or 'tecnolog' in combined:
            return 'Pesquisadores, ICTs, empresas e ambientes de inovacao de Mato Grosso'
        if 'bolsa' in combined:
            return 'Pesquisadores, bolsistas e instituicoes de ensino e pesquisa de Mato Grosso'
        return 'Pesquisadores, grupos de pesquisa e instituicoes de Mato Grosso'

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
