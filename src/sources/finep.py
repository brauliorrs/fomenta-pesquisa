from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from src.sources.base_source import BaseSource


class FINEPSource(BaseSource):
    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for card in soup.select('.item'):
            title_node = card.select_one('h3 a[href]')
            if not title_node:
                continue

            title = title_node.get_text(' ', strip=True)
            href = (title_node.get('href') or '').strip()
            if not title or not href:
                continue

            full_href = urljoin(self.config.site_oficial, href)
            if full_href in seen:
                continue

            public_node = card.select_one('.publico .tag')
            prazo_node = card.select_one('.prazo span')
            publication_node = card.select_one('.data_pub span')
            theme_node = card.select_one('.tema span')

            seen.add(full_href)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': 'inovacao',
                    'link': full_href,
                    'resumo': (theme_node.get_text(' ', strip=True) if theme_node else title),
                    'publico_alvo': (public_node.get_text(' ', strip=True) if public_node else 'Empresas e instituicoes de pesquisa'),
                    'data_abertura': publication_node.get_text(' ', strip=True) if publication_node else None,
                    'data_expiracao': prazo_node.get_text(' ', strip=True) if prazo_node else None,
                }
            )

        return items
