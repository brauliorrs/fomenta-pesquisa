from __future__ import annotations

import warnings
from typing import Any
from urllib.parse import urljoin

import requests
from requests.exceptions import SSLError

from src.sources.base_source import BaseSource


class EMBRAPASource(BaseSource):
    OPENING_HINTS = ('chamada abertura', 'chamada nº', 'chamada no', 'chamada n')
    EXCLUDE_HINTS = ('resultado', 'retificada', 'anexo', 'orientação', 'orientacao')

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for card in soup.select('.card-frame'):
            title_node = card.select_one('h3')
            title = title_node.get_text(' ', strip=True) if title_node else ''
            if not title:
                continue

            resumo = ''
            first_paragraph = card.select_one('.card-frame-texto p')
            if first_paragraph:
                resumo = first_paragraph.get_text(' ', strip=True)

            edital_link = self._extract_opening_link(card)
            if not edital_link or edital_link in seen:
                continue

            seen.add(edital_link)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': 'pesquisa',
                    'link': edital_link,
                    'resumo': resumo or title,
                    'publico_alvo': 'Instituicoes e pesquisadores',
                    'data_abertura': None,
                    'data_expiracao': None,
                }
            )

        return items

    def fetch(self) -> str:
        try:
            return super().fetch()
        except SSLError:
            warnings.filterwarnings('ignore', message='Unverified HTTPS request')
            response = requests.get(
                self.config.pagina_editais,
                timeout=self.timeout,
                headers={"User-Agent": "editais-bot/1.0"},
                verify=False,
            )
            response.raise_for_status()
            return response.text

    def _extract_opening_link(self, card: Any) -> str | None:
        candidates: list[tuple[int, str]] = []

        for anchor in card.select('a[href]'):
            text = anchor.get_text(' ', strip=True).lower()
            href = (anchor.get('href') or '').strip()
            if not href:
                continue

            full_href = urljoin(self.config.site_oficial, href)
            if any(hint in text for hint in self.EXCLUDE_HINTS):
                continue
            if any(hint in text for hint in self.OPENING_HINTS):
                score = 0
                if 'abertura' in text:
                    score += 5
                if 'chamada nº' in text or 'chamada no' in text or 'chamada n' in text:
                    score += 2
                if full_href.lower().endswith('.pdf'):
                    score += 1
                candidates.append((score, full_href))

        if not candidates:
            return None

        candidates.sort(key=lambda item: (-item[0], len(item[1])))
        return candidates[0][1]
