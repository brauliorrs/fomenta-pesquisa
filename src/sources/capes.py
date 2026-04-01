from __future__ import annotations

from typing import Any

from src.sources.base_source import BaseSource


class CAPESSource(BaseSource):
    INCLUDE_KEYWORDS = ('edital', 'chamamento', 'inscri', 'prorroga prazo', 'prorroga o prazo', 'seleção', 'selecao')
    EXCLUDE_KEYWORDS = (
        'seminário',
        'seminario',
        'debate',
        'homenageada',
        'prestigia',
        'reúne',
        'reune',
        'apresenta',
        'explica',
        'ofertará',
        'ofertara',
        'concedem',
        'lista tríplice',
        'lista triplice',
        'cadastramento de bolsas',
        'cadastramento',
        'registro de informações',
        'registro de informacoes',
        'instabilidade no sistema',
        'instabilidade constatada no sistema',
    )
    CATEGORY_HINTS = {
        'edital': 'edital',
        'chamamento': 'chamamento',
        'bolsa': 'bolsa',
        'inscri': 'selecao',
    }

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for link in soup.select('a'):
            title = link.get_text(' ', strip=True)
            href = (link.get('href') or '').strip()
            if not title or not href:
                continue
            if '/assuntos/noticias/' not in href:
                continue
            if href in seen:
                continue

            lower_title = title.lower()
            if not any(keyword in lower_title for keyword in self.INCLUDE_KEYWORDS):
                continue
            if any(keyword in lower_title for keyword in self.EXCLUDE_KEYWORDS):
                continue

            categoria = 'bolsa'
            for hint, value in self.CATEGORY_HINTS.items():
                if hint in lower_title:
                    categoria = value
                    break

            seen.add(href)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': categoria,
                    'link': href,
                    'resumo': title,
                    'publico_alvo': 'Comunidade academica',
                    'data_abertura': None,
                    'data_expiracao': None,
                }
            )

            if len(items) >= 20:
                break

        return items
