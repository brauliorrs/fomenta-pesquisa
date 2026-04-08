from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import Tag

from src.sources.base_source import BaseSource


class FAPERJSource(BaseSource):
    TITLE_PATTERN = re.compile(r'Edital FAPERJ N[º°]\s*\d+/\d{4}', re.I)

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for paragraph in soup.select('p'):
            text = paragraph.get_text(' ', strip=True)
            if not text or not self.TITLE_PATTERN.search(text):
                continue

            link_node = paragraph.select_one('a[href]')
            if not link_node:
                continue

            title = link_node.get_text(' ', strip=True)
            href = (link_node.get('href') or '').strip()
            if not title or not href:
                continue

            full_href = urljoin(self.config.site_oficial, href)
            if full_href in seen:
                continue

            expiration = self._extract_submission_deadline(text)
            if not expiration:
                continue

            seen.add(full_href)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._infer_categoria(title, text),
                    'link': full_href,
                    'resumo': self._build_summary(text, title),
                    'publico_alvo': self._infer_publico_alvo(title, text),
                    'data_abertura': self._extract_opening_date(text),
                    'data_expiracao': expiration,
                }
            )

        return items

    def _extract_submission_deadline(self, text: str) -> str | None:
        match = re.search(
            r'Submiss[aã]o de propostas(?: on-line| online)?\s*:\s*(.+?)(?:Divulga[cç][aã]o do resultado|Interposi[cç][aã]o de recursos|Prazo para interposi[cç][aã]o|Resultado Final|$)',
            text,
            flags=re.I,
        )
        if not match:
            return None

        dates = re.findall(r'\d{1,2}/\d{1,2}/\d{4}', match.group(1))
        if dates:
            return dates[-1]

        extenso = re.findall(
            r'\d{1,2} de [A-Za-zçãéíóúâêôà]+ de \d{4}',
            match.group(1),
            flags=re.I,
        )
        if extenso:
            return extenso[-1]
        return None

    def _extract_opening_date(self, text: str) -> str | None:
        match = re.search(r'Lan[cç]amento do edital:\s*(\d{1,2}/\d{1,2}/\d{4})', text, flags=re.I)
        if match:
            return match.group(1)
        return None

    def _infer_categoria(self, title: str, text: str) -> str:
        combined = f'{title} {text}'.lower()
        if 'bolsa' in combined or 'pesquisador visitante' in combined or 'pós-doutorado' in combined or 'pos-doutorado' in combined:
            return 'bolsa'
        if 'inova' in combined or 'startup' in combined or 'empresa' in combined:
            return 'inovacao'
        return 'pesquisa'

    def _build_summary(self, text: str, fallback_title: str) -> str:
        opening = self._extract_opening_date(text)
        expiration = self._extract_submission_deadline(text)
        if opening and expiration:
            return f'Lançamento em {opening} e submissão aberta até {expiration}.'
        return fallback_title

    def _infer_publico_alvo(self, title: str, text: str) -> str:
        combined = f'{title} {text}'.lower()
        if 'empresa' in combined or 'startup' in combined:
            return 'Empresas, startups e pesquisadores'
        if 'bolsa' in combined or 'pesquisador visitante' in combined:
            return 'Pesquisadores, bolsistas e programas de pos-graduacao'
        return 'Pesquisadores, grupos de pesquisa e instituicoes do Rio de Janeiro'
