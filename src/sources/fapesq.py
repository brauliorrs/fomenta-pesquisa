from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPESQSource(BaseSource):
    INCLUDE_HINTS = ('edital', 'chamada', 'submiss', 'inscri', 'propostas', 'aberto')
    EXCLUDE_HINTS = ('resultado', 'retifica', 'retificação', 'errata', 'homologa', 'encerrad', 'lista final')

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        containers = soup.select('article, .entry-content, main')
        for container in containers:
            for anchor in container.select('a[href]'):
                title = self._clean_text(anchor.get_text(' ', strip=True))
                href = self._clean_text(anchor.get('href'))
                context = self._clean_text(anchor.parent.get_text(' ', strip=True)) if anchor.parent else title
                if not title or not href:
                    continue

                combined = f'{title} {context}'.lower()
                if any(hint in combined for hint in self.EXCLUDE_HINTS):
                    continue
                if not any(hint in combined for hint in self.INCLUDE_HINTS):
                    continue

                full_href = urljoin(self.config.site_oficial, href)
                dedupe_key = f'{title}|{full_href}'
                if dedupe_key in seen:
                    continue

                seen.add(dedupe_key)
                expiration = self._extract_deadline(context)
                items.append(
                    {
                        'titulo': title,
                        'orgao': self.config.nome,
                        'fonte': self.config.sigla,
                        'uf': self.config.uf,
                        'categoria': self._infer_categoria(title, context),
                        'link': full_href,
                        'resumo': context if len(context) >= 40 else title,
                        'publico_alvo': self._infer_publico_alvo(title, context),
                        'data_abertura': None,
                        'data_expiracao': expiration,
                        'status': 'aberto',
                    }
                )

        return items

    def _extract_deadline(self, text: str) -> str | None:
        match = re.search(r'(\d{2}/\d{2}/\d{4})', text)
        if match:
            return match.group(1)
        return None

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'bolsa' in combined:
            return 'bolsa'
        if any(token in combined for token in ('inov', 'empresa', 'startup')):
            return 'inovacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('empresa', 'startup', 'inov')):
            return 'Empresas, empreendedores, pesquisadores e ICTs da Paraiba'
        if 'bolsa' in combined:
            return 'Estudantes, bolsistas e pesquisadores vinculados a instituicoes da Paraiba'
        return 'Pesquisadores, grupos de pesquisa e instituicoes cientificas da Paraiba'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())
