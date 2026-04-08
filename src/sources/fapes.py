from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from src.sources.base_source import BaseSource


class FAPESSource(BaseSource):
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    CATEGORY_URLS = (
        'https://fapes.es.gov.br/edital-aberto-formacao-cientifica',
        'https://fapes.es.gov.br/editais-abertos-pesquisa-4',
        'https://fapes.es.gov.br/difusao-do-conhecimento',
        'https://fapes.es.gov.br/editais-abertos-extensao-2',
        'https://fapes.es.gov.br/inovacao',
        'https://fapes.es.gov.br/chamadas-internacionais',
    )
    EXCLUDE_HINTS = (
        'webinário',
        'webinario',
        'manual',
        'formulário',
        'formulario',
        'tabela',
        'planilha',
        'faq',
        'pergunta',
        'tutorial',
        'cadastro',
        'sigfapes',
    )

    def collect(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for page_url in self.CATEGORY_URLS:
            soup = self._fetch_soup(page_url)
            if soup is None:
                continue

            for item in self._parse_page(soup):
                link = (item.get('link') or '').strip()
                if not link or link in seen:
                    continue
                seen.add(link)
                items.append(item)

        return items

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        return []

    def _parse_page(self, soup: BeautifulSoup) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []

        for panel in soup.select('div.panel.panel-box'):
            title_node = panel.select_one('.paneltitle-value')
            if not title_node:
                continue

            title = self._clean_text(title_node.get_text(' ', strip=True))
            if not title or 'edital fapes' not in title.lower():
                continue

            summary = self._extract_summary(panel) or title
            link = self._extract_notice_link(panel, title)
            if not link:
                continue

            update_node = panel.select_one('.dataatualizacao-value')
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._infer_categoria(title, summary),
                    'link': link,
                    'resumo': summary,
                    'publico_alvo': self._infer_publico_alvo(title, summary),
                    'data_abertura': self._clean_text(update_node.get_text(' ', strip=True)) if update_node else None,
                    'data_expiracao': None,
                }
            )

        return items

    def _fetch_soup(self, url: str) -> BeautifulSoup | None:
        try:
            response = requests.get(url, timeout=self.timeout, headers=self.USER_AGENT)
            response.raise_for_status()
        except Exception:
            return None
        return BeautifulSoup(response.text, 'html.parser')

    def _extract_summary(self, panel: Tag) -> str:
        summary_node = panel.select_one('.description-table-content .description-value')
        if summary_node:
            text = self._clean_text(summary_node.get_text(' ', strip=True))
            if text:
                return text

        caption_node = panel.select_one('.caption-value')
        if caption_node:
            return self._clean_text(caption_node.get_text(' ', strip=True))
        return ''

    def _extract_notice_link(self, panel: Tag, title: str) -> str:
        title_lower = title.lower()

        for anchor in panel.select('table.table-downloads a[href]'):
            label = self._clean_text(anchor.get_text(' ', strip=True))
            lower_label = label.lower()
            href = self._clean_text(anchor.get('href'))
            if not href:
                continue
            if any(hint in lower_label for hint in self.EXCLUDE_HINTS):
                continue
            if 'edital fapes' not in lower_label and title_lower not in lower_label:
                continue
            return urljoin(self.config.site_oficial, href)

        for anchor in panel.select('table.table-downloads a[href]'):
            label = self._clean_text(anchor.get_text(' ', strip=True))
            lower_label = label.lower()
            href = self._clean_text(anchor.get('href'))
            if not href:
                continue
            if any(hint in lower_label for hint in self.EXCLUDE_HINTS):
                continue
            if lower_label.startswith('edital fapes'):
                return urljoin(self.config.site_oficial, href)

        return ''

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'inov' in combined or 'empresa' in combined or 'propriedade intelectual' in combined:
            return 'inovacao'
        if 'evento' in combined or 'difusão' in combined or 'difusao' in combined:
            return 'divulgacao'
        if 'bolsa' in combined or 'formação' in combined or 'formacao' in combined or 'estágio' in combined or 'estagio' in combined:
            return 'bolsa'
        if 'extensão' in combined or 'extensao' in combined:
            return 'extensao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'evento' in combined:
            return 'Pesquisadores, estudantes e instituicoes de ensino do Espirito Santo'
        if 'inov' in combined or 'empresa' in combined:
            return 'Empresas, startups, pesquisadores e ICTs do Espirito Santo'
        if 'formação' in combined or 'formacao' in combined or 'bolsa' in combined or 'estágio' in combined or 'estagio' in combined:
            return 'Pesquisadores, bolsistas, estudantes e instituicoes de ensino do Espirito Santo'
        return 'Pesquisadores, grupos de pesquisa e instituicoes do Espirito Santo'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())
