from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from src.sources.base_source import BaseSource


class FAPESBSource(BaseSource):
    EXCLUDE_HINTS = (
        'errata',
        'resultado',
        'prorroga',
        'enquadramento',
        'retifica',
    )

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for article in soup.select('article.category-aberto.category-edital'):
            title_node = article.select_one('h2.entry-title a[href]')
            if not title_node:
                continue

            title = title_node.get_text(' ', strip=True)
            href = (title_node.get('href') or '').strip()
            if not title or not href:
                continue

            lower_title = title.lower()
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
                continue

            full_href = urljoin(self.config.site_oficial, href)
            if full_href in seen:
                continue

            summary_node = article.select_one('.entry-content p')
            published_node = article.select_one('time.entry-date.published')

            seen.add(full_href)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._infer_categoria(title),
                    'link': full_href,
                    'resumo': summary_node.get_text(' ', strip=True) if summary_node else title,
                    'publico_alvo': self._infer_publico_alvo(title),
                    'data_abertura': published_node.get_text(' ', strip=True) if published_node else None,
                    'data_expiracao': None,
                }
            )

        return items

    def _infer_categoria(self, title: str) -> str:
        lower_title = title.lower()
        if 'bolsa' in lower_title:
            return 'bolsa'
        if 'inova' in lower_title or 'empresa' in lower_title or 'centelha' in lower_title:
            return 'inovacao'
        if 'chamada' in lower_title:
            return 'pesquisa'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str) -> str:
        lower_title = title.lower()
        if 'pesquisador' in lower_title or 'pós-graduação' in lower_title or 'pos-graduacao' in lower_title:
            return 'Pesquisadores e programas de pos-graduacao da Bahia'
        if 'empresa' in lower_title or 'inov' in lower_title or 'centelha' in lower_title:
            return 'Empresas, empreendedores e pesquisadores da Bahia'
        return 'Pesquisadores, grupos de pesquisa e instituicoes da Bahia'
