from __future__ import annotations

from typing import Any

from src.sources.base_source import BaseSource


class IPEASource(BaseSource):
    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for link in soup.select('a'):
            title = link.get_text(' ', strip=True)
            href = (link.get('href') or '').strip()
            if not title or not href:
                continue
            if '/portal/bolsas-de-pesquisa-lista/' not in href:
                continue
            if href.startswith('/'):
                href = f'https://www.ipea.gov.br{href}'
            if href in seen:
                continue

            seen.add(href)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': 'pesquisa',
                    'link': href,
                    'resumo': title,
                    'publico_alvo': 'Pesquisadores e bolsistas',
                    'data_abertura': None,
                    'data_expiracao': None,
                }
            )

            if len(items) >= 20:
                break

        return items
