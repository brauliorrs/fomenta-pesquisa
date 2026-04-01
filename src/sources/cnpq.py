from __future__ import annotations

from typing import Any

from src.sources.base_source import BaseSource


class CNPQSource(BaseSource):
    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []

        for container in soup.select('li'):
            title_tag = container.select_one('h4')
            link_input = container.select_one('input[value*=idDivulgacao]')
            if title_tag is None or link_input is None:
                continue

            title = title_tag.get_text(' ', strip=True)
            href = link_input.get('value', '').strip()
            if not title or not href:
                continue

            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': 'pesquisa',
                    'link': href,
                    'resumo': title,
                    'publico_alvo': 'Pesquisadores',
                    'data_abertura': None,
                    'data_expiracao': None,
                }
            )

            if len(items) >= 20:
                break

        return items
