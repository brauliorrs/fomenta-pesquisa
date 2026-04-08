from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup, NavigableString, Tag

from src.sources.base_source import BaseSource


class FAPESPSource(BaseSource):
    DEADLINE_HINTS = (
        'data limite',
        'data-limite',
        'prazo',
        'submiss',
        'apresentação de pré-propostas',
        'apresentacao de pre-propostas',
        'prazos',
    )
    EXCLUDE_HINTS = (
        'english',
        'acordos',
        'ano todo',
        'fluxo contínuo',
        'fluxo continuo',
    )

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for heading in soup.select('h3 a[href]'):
            title = heading.get_text(' ', strip=True)
            href = (heading.get('href') or '').strip()
            if not title or not href:
                continue

            block_lines = self._collect_block_lines(heading.parent)
            lower_block = ' '.join(block_lines).lower()
            if not any(hint in lower_block for hint in self.DEADLINE_HINTS):
                continue
            if any(hint in lower_block for hint in self.EXCLUDE_HINTS):
                continue

            expiration = self._extract_deadline(block_lines)
            if not expiration:
                continue

            full_href = urljoin(self.config.site_oficial, href)
            if full_href in seen:
                continue

            seen.add(full_href)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._extract_categoria(block_lines),
                    'link': full_href,
                    'resumo': self._build_summary(block_lines, title),
                    'publico_alvo': self._infer_publico_alvo(title, block_lines),
                    'data_abertura': None,
                    'data_expiracao': expiration,
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
            if sibling.name == 'h3':
                break

            text = sibling.get_text(' ', strip=True)
            if text:
                lines.append(text)

            if sibling.name == 'hr':
                break

        return lines

    def _extract_deadline(self, block_lines: list[str]) -> str | None:
        joined = ' '.join(block_lines)
        dates = re.findall(r'\d{1,2}/\d{1,2}/\d{4}', joined)
        if dates:
            return dates[0]

        extenso = re.search(
            r'(\d{1,2}) de ([A-Za-zçãéíóúâêôà]+) de (\d{4})',
            joined,
            flags=re.I,
        )
        if extenso:
            return extenso.group(0)
        return None

    def _extract_categoria(self, block_lines: list[str]) -> str:
        joined = ' '.join(block_lines).lower()
        if 'inovação' in joined or 'inovacao' in joined or 'pipe' in joined:
            return 'inovacao'
        if 'bolsa' in joined:
            return 'bolsa'
        return 'pesquisa'

    def _build_summary(self, block_lines: list[str], fallback_title: str) -> str:
        for line in block_lines:
            lower = line.lower()
            if lower.startswith('área') or lower.startswith('areas') or lower.startswith('áreas'):
                return line
            if lower.startswith('modalidade'):
                return line
        return fallback_title

    def _infer_publico_alvo(self, title: str, block_lines: list[str]) -> str:
        combined = f"{title} {' '.join(block_lines)}".lower()
        if 'pipe' in combined or 'startup' in combined or 'empresa' in combined:
            return 'Empresas inovadoras, startups e pesquisadores'
        if 'escola' in combined or 'reunião científica' in combined or 'reuniao cientifica' in combined:
            return 'Pesquisadores, docentes e organizadores de atividades cientificas'
        return 'Pesquisadores, grupos de pesquisa e instituicoes cientificas'
