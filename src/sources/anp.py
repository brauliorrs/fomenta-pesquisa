from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class ANPSource(BaseSource):
    PRH_URL = (
        'https://www.gov.br/anp/pt-br/assuntos/tecnologia-meio-ambiente/'
        'prh-anp-programa-de-formacao-de-recursos-humanos/eixo-academico/edital-de-chamada-publica'
    )
    AWARD_URL = (
        'https://www.gov.br/anp/pt-br/assuntos/tecnologia-meio-ambiente/'
        'premio-anp-inovacao-tecnologica/premio-anp-de-inovacao-tecnologica-2025'
    )
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for builder in (self._build_prh_item, self._build_award_item):
            item = builder()
            if not item:
                continue

            link = (item.get('link') or '').strip()
            if not link or link in seen:
                continue

            seen.add(link)
            items.append(item)

        return items

    def _build_prh_item(self) -> dict[str, Any] | None:
        soup = self._fetch_soup(self.PRH_URL)
        if soup is None:
            return None

        text = soup.get_text('\n', strip=True)
        title = self._find_text(
            soup,
            (
                re.compile(r'Edital de Chamada P[úu]blica n.? ?\d+/PRH-ANP/\d{4}', re.I),
                re.compile(r'Edital de Chamada P[úu]blica', re.I),
            ),
        )
        edital_link = self._find_link(
            soup,
            include=('edital',),
            exclude=('retifica', 'resultado', 'manual', 'tutorial', 'youtube', 'recurso', 'errata'),
        )
        opening_date = self._first_group(
            text,
            (
                r'Em\s+(\d{1,2}/\d{1,2}/\d{4}),\s+a ANP publicou o Edital',
                r'Publicado em\s+(\d{1,2}/\d{1,2}/\d{4})',
            ),
        )

        return {
            'titulo': title or 'Edital de Chamada Publica PRH-ANP',
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': 'formacao',
            'link': edital_link or self.PRH_URL,
            'resumo': 'Chamada da ANP para classificacao de programas de formacao de recursos humanos no eixo academico.',
            'publico_alvo': 'Instituicoes de ensino superior, pesquisadores e bolsistas',
            'data_abertura': opening_date,
            'data_expiracao': None,
        }

    def _build_award_item(self) -> dict[str, Any] | None:
        soup = self._fetch_soup(self.AWARD_URL)
        if soup is None:
            return None

        text = soup.get_text('\n', strip=True)
        title = self._find_text(
            soup,
            (
                re.compile(r'Pr[êe]mio ANP de Inova[cç][aã]o Tecnol[óo]gica \d{4}', re.I),
                re.compile(r'Pr[êe]mio ANP de Inova[cç][aã]o Tecnol[óo]gica', re.I),
            ),
        )
        edital_link = self._find_link(
            soup,
            include=('download do edital', 'fazer o download do edital'),
            exclude=('termo aditivo',),
        )
        opening_date = self._first_group(text, (r'Prazo para inscri[cç][oõ]es:\s*(\d{1,2}/\d{1,2}/\d{4})',))
        expiration_date = self._second_group(
            text,
            (r'Prazo para inscri[cç][oõ]es:\s*(\d{1,2}/\d{1,2}/\d{4})\s*a\s*(\d{1,2}/\d{1,2}/\d{4})',),
        )

        return {
            'titulo': title or 'Premio ANP de Inovacao Tecnologica',
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': 'inovacao',
            'link': edital_link or self.AWARD_URL,
            'resumo': 'Premio da ANP para reconhecer projetos de pesquisa, desenvolvimento e inovacao ligados ao setor de energia.',
            'publico_alvo': 'Empresas, instituicoes de pesquisa e pesquisadores do setor energetico',
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

    def _find_text(self, soup: BeautifulSoup, patterns: tuple[re.Pattern[str], ...]) -> str | None:
        for pattern in patterns:
            match = soup.find(string=pattern)
            if match:
                return str(match).strip()
        return None

    def _find_link(self, soup: BeautifulSoup, include: tuple[str, ...], exclude: tuple[str, ...]) -> str | None:
        for anchor in soup.select('a[href]'):
            label = anchor.get_text(' ', strip=True).lower()
            href = (anchor.get('href') or '').strip()
            if not href:
                continue
            if not any(token in label for token in include):
                continue
            if any(token in label for token in exclude):
                continue
            return urljoin(self.config.site_oficial, href)
        return None

    def _first_group(self, text: str, patterns: tuple[str, ...]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match:
                return match.group(1)
        return None

    def _second_group(self, text: str, patterns: tuple[str, ...]) -> str | None:
        for pattern in patterns:
            match = re.search(pattern, text, flags=re.I)
            if match and match.lastindex and match.lastindex >= 2:
                return match.group(2)
        return None
