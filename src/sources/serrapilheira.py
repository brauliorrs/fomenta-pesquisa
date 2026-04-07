from __future__ import annotations

from typing import Any

from src.sources.base_source import BaseSource


class SERRAPILHEIRASource(BaseSource):
    INCLUDE_HINTS = ('chamada pública', 'chamada publica', 'chamada para')
    EXCLUDE_HINTS = ('camp serrapilheira',)

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for anchor in soup.select('a.vc_gitem-link[href], a[href]'):
            title = anchor.get_text(' ', strip=True)
            href = (anchor.get('href') or '').strip()
            if not title or not href:
                continue

            lower_title = title.lower()
            if not any(hint in lower_title for hint in self.INCLUDE_HINTS):
                continue
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
                continue
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
                    'publico_alvo': 'Pesquisadores e pos-doutorandos',
                    'data_abertura': None,
                    'data_expiracao': None,
                }
            )

        return items
