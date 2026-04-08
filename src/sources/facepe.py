from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import NavigableString, Tag

from src.sources.base_source import BaseSource


class FACEPESource(BaseSource):
    EXCLUDE_HINTS = (
        'errata',
        'resultado',
        'retificação',
        'retificacao',
        'prorrogação',
        'prorrogacao',
        'enquadramento',
        'lista de espera',
        'homologadas',
        'fluxo contínuo',
        'fluxo continuo',
        'rodada 1',
    )

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for heading in soup.select('h5 a[href]'):
            title = heading.get_text(' ', strip=True)
            href = (heading.get('href') or '').strip()
            if not title or not href:
                continue

            lower_title = title.lower()
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
                continue

            full_href = urljoin(self.config.site_oficial, href)
            if full_href in seen:
                continue

            block_lines = self._collect_block_lines(heading.parent)
            publication = self._extract_publication_date(block_lines)

            seen.add(full_href)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._infer_categoria(title),
                    'link': full_href,
                    'resumo': title,
                    'publico_alvo': self._infer_publico_alvo(title),
                    'data_abertura': publication,
                    'data_expiracao': None,
                }
            )

        return items

    def _collect_block_lines(self, start_node: Tag) -> list[str]:
        lines: list[str] = []
        for sibling in start_node.next_siblings:
            if isinstance(sibling, NavigableString):
                text = str(sibling).strip()
                if text:
                    lines.append(text)
                continue

            if not isinstance(sibling, Tag):
                continue
            if sibling.name == 'h5':
                break

            text = sibling.get_text(' ', strip=True)
            if text:
                lines.append(text)
            if sibling.name == 'hr':
                break

        return lines

    def _extract_publication_date(self, block_lines: list[str]) -> str | None:
        joined = ' '.join(block_lines)
        match = re.search(r'Publica[cç][aã]o:\s*(\d{1,2} de [A-Za-zçãéíóúâêôà]+ de \d{4})', joined, flags=re.I)
        if match:
            return match.group(1)
        return None

    def _infer_categoria(self, title: str) -> str:
        lower_title = title.lower()
        if 'bolsa' in lower_title:
            return 'bolsa'
        if 'inova' in lower_title or 'startup' in lower_title or 'compet' in lower_title:
            return 'inovacao'
        if 'prêmio' in lower_title or 'premio' in lower_title:
            return 'premio'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str) -> str:
        lower_title = title.lower()
        if 'startup' in lower_title or 'inovam' in lower_title:
            return 'Startups, empreendedoras e inovadores'
        if 'bolsa' in lower_title or 'iniciação científica' in lower_title or 'iniciacao cientifica' in lower_title:
            return 'Estudantes, bolsistas e pesquisadores'
        return 'Pesquisadores, grupos de pesquisa e instituicoes de Pernambuco'
