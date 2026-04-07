from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from src.sources.base_source import BaseSource


class FIOCRUZSource(BaseSource):
    TITLE_HINTS = ('pibic', 'pibiti', 'ic ', 'ic-', 'iniciacao', 'edital', 'bolsa')

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in soup.select('.edital-corrente .editalItem'):
            title_node = item.select_one('.box-simple-title')
            title = title_node.get_text(' ', strip=True) if title_node else ''
            if not title:
                continue

            lower_title = title.lower()
            if not any(hint in lower_title for hint in self.TITLE_HINTS):
                continue

            edital_link = self._extract_edital_link(item)
            if not edital_link or edital_link in seen:
                continue

            seen.add(edital_link)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': 'bolsa',
                    'link': edital_link,
                    'resumo': title,
                    'publico_alvo': 'Estudantes e pesquisadores',
                    'data_abertura': None,
                    'data_expiracao': None,
                }
            )

        return items

    def _extract_edital_link(self, item: Any) -> str | None:
        for button in item.select('button[onclick], a[href]'):
            label = button.get_text(' ', strip=True).lower()
            if 'errata' in label:
                continue
            if 'edital' not in label:
                continue

            href = (button.get('href') or '').strip()
            if href:
                return urljoin(self.config.site_oficial, href)

            onclick = (button.get('onclick') or '').strip()
            match = re.search(r"window\.open\('([^']+)'", onclick)
            if match:
                return urljoin(self.config.site_oficial, match.group(1))

        return None
