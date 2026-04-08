from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPEAPSource(BaseSource):
    EXCLUDE_HINTS = ('resultado', 'retifica', 'portaria', 'homologa', 'errata')

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for row in soup.select('tr.clickable-row[data-href]'):
            href = self._clean_text(row.get('data-href'))
            cells = row.select('td')
            if len(cells) < 2 or not href:
                continue

            opening_date = self._clean_text(cells[0].get_text(' ', strip=True))
            meta_cell = cells[1]
            badge = meta_cell.select_one('div span')
            title_node = meta_cell.select_one('span.tw-text-black')
            category = self._clean_text(badge.get_text(' ', strip=True) if badge is not None else '')
            title = self._clean_text(title_node.get_text(' ', strip=True) if title_node is not None else meta_cell.get_text(' ', strip=True))
            if not title:
                continue

            lower_title = title.lower()
            if category.lower() != 'chamadas':
                continue
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
                continue

            link = urljoin(self.config.site_oficial, href)
            if link in seen:
                continue

            seen.add(link)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._infer_categoria(title),
                    'link': link,
                    'resumo': f'{title}. Chamada aberta publicada pela FAPEAP.',
                    'publico_alvo': self._infer_publico_alvo(title),
                    'data_abertura': opening_date,
                    'data_expiracao': None,
                    'status': 'aberto',
                }
            )

        return items

    def _infer_categoria(self, title: str) -> str:
        lower = title.lower()
        if any(token in lower for token in ('bolsa', 'mestrado', 'doutorado', 'pos-graduacao')):
            return 'bolsa'
        if any(token in lower for token in ('centelha', 'startup', 'inovacao')):
            return 'inovacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str) -> str:
        lower = title.lower()
        if any(token in lower for token in ('mestrado', 'doutorado', 'bolsa')):
            return 'Pesquisadores, bolsistas e programas de pos-graduacao do Amapa'
        if any(token in lower for token in ('centelha', 'startup', 'inovacao')):
            return 'Empreendedores, startups, pesquisadores e ICTs do Amapa'
        return 'Pesquisadores, grupos de pesquisa e instituicoes cientificas do Amapa'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        text = BeautifulSoup(str(value), 'html.parser').get_text(' ', strip=True)
        return ' '.join(text.replace('\xa0', ' ').split())
