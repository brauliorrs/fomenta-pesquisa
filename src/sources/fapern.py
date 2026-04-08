from __future__ import annotations

import json
import re
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPERNSource(BaseSource):
    API_URL = 'https://www.fapern.rn.gov.br/wp-json/wp/v2/materia'
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    INCLUDE_HINTS = ('edital', 'chamada', 'inscri', 'submiss', 'selec', 'bolsa')
    TITLE_EXCLUDE_HINTS = ('seminario', 'evento', 'reuniao', 'parceria', 'palestra', 'resultado', 'homologa')
    MONTHS = {
        'janeiro': 1,
        'fevereiro': 2,
        'marco': 3,
        'março': 3,
        'abril': 4,
        'maio': 5,
        'junho': 6,
        'julho': 7,
        'agosto': 8,
        'setembro': 9,
        'outubro': 10,
        'novembro': 11,
        'dezembro': 12,
    }

    def collect(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        page = 1
        total_pages = 1

        while page <= total_pages:
            response = requests.get(
                self.API_URL,
                params={'categories': 4, 'per_page': 50, 'page': page},
                headers=self.USER_AGENT,
                timeout=self.timeout,
            )
            if response.status_code == 400 and page > 1:
                break
            response.raise_for_status()
            total_pages = int(response.headers.get('X-WP-TotalPages', '1') or '1')
            payload = response.json()
            if not isinstance(payload, list):
                break

            for entry in payload:
                item = self._build_item(entry)
                if not item or item['link'] in seen:
                    continue
                seen.add(item['link'])
                items.append(item)

            page += 1

        return items

    def fetch(self) -> str:
        response = requests.get(
            self.API_URL,
            params={'categories': 4, 'per_page': 50, 'page': 1},
            headers=self.USER_AGENT,
            timeout=self.timeout,
        )
        response.raise_for_status()
        return response.text

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        payload = json.loads(raw_content)
        if not isinstance(payload, list):
            return []

        items: list[dict[str, Any]] = []
        seen: set[str] = set()
        for entry in payload:
            item = self._build_item(entry)
            if not item or item['link'] in seen:
                continue
            seen.add(item['link'])
            items.append(item)
        return items

    def _build_item(self, entry: dict[str, Any]) -> dict[str, Any] | None:
        title = self._html_to_text(entry.get('title', {}).get('rendered'))
        link = self._clean_text(entry.get('link'))
        if not title or not link:
            return None

        lower_title = title.lower()
        if any(hint in lower_title for hint in self.TITLE_EXCLUDE_HINTS):
            return None

        acf = entry.get('acf') if isinstance(entry.get('acf'), dict) else {}
        summary = self._clean_text(acf.get('resumo'))
        content_html = self._clean_text(acf.get('materia'))
        content_text = self._html_to_text(content_html)
        combined = f'{title} {summary} {content_text}'.lower()
        if not any(hint in combined for hint in self.INCLUDE_HINTS):
            return None

        official_link = self._extract_notice_link(content_html) or link
        opening_date = self._clean_text(entry.get('date')).split('T', 1)[0] or None
        expiration_date = self._extract_deadline(summary, content_text, opening_date)
        final_summary = summary or self._first_sentence(content_text) or f'{title}.'

        return {
            'titulo': title,
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': self._infer_categoria(title, final_summary),
            'link': official_link,
            'resumo': final_summary,
            'publico_alvo': self._infer_publico_alvo(title, final_summary),
            'data_abertura': opening_date,
            'data_expiracao': expiration_date,
            'status': 'aberto',
        }

    def _extract_notice_link(self, html_content: str) -> str | None:
        if not html_content:
            return None

        soup = BeautifulSoup(html_content, 'html.parser')
        best_href: str | None = None
        best_score = -1

        for anchor in soup.select('a[href]'):
            href = self._clean_text(anchor.get('href'))
            label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
            if not href:
                continue

            score = 0
            if href.lower().endswith('.pdf') or '.pdf?' in href.lower():
                score += 3
            if any(token in label for token in ('edital', 'chamada')):
                score += 4
            if 'fapern.rn.gov.br' in href:
                score += 1

            if score > best_score:
                best_score = score
                best_href = href

        return best_href

    def _extract_deadline(self, summary: str, content: str, opening_date: str | None) -> str | None:
        combined = f'{summary} {content}'

        numeric_matches = re.findall(r'(\d{1,2}/\d{1,2}/\d{4})', combined)
        if numeric_matches:
            return numeric_matches[-1]

        base_year = int(opening_date[:4]) if opening_date else None

        range_match = re.search(
            r'(\d{1,2})[ºo]?\s+a\s+(\d{1,2})\s+de\s+([A-Za-zçãéíóúâêôà]+)(?:\s+de\s+(\d{4}))?',
            combined,
            flags=re.I,
        )
        if range_match:
            _, end_day, month_name, explicit_year = range_match.groups()
            return self._format_date(end_day, month_name, explicit_year or base_year)

        until_match = re.search(
            r'at[eé]\s+(?:as\s+\d{1,2}h\d{0,2}\s+)?(\d{1,2})\s+de\s+([A-Za-zçãéíóúâêôà]+)(?:\s+de\s+(\d{4}))?',
            combined,
            flags=re.I,
        )
        if until_match:
            day, month_name, explicit_year = until_match.groups()
            return self._format_date(day, month_name, explicit_year or base_year)

        return None

    def _format_date(self, day: str, month_name: str, year: str | int | None) -> str | None:
        if year is None:
            return None
        month = self.MONTHS.get(month_name.lower())
        if month is None:
            return None
        return f'{int(day):02d}/{month:02d}/{int(year):04d}'

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('bolsa', 'doutor', 'pos-graduacao')):
            return 'bolsa'
        if any(token in combined for token in ('inovacao', 'tecnologia', 'propin')):
            return 'inovacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('doutor', 'doutorado', 'bolsa', 'pesquisador-bolsista')):
            return 'Pesquisadores, bolsistas e instituicoes cientificas do Rio Grande do Norte'
        if any(token in combined for token in ('ti', 'direito', 'assistente administrativo')):
            return 'Profissionais, pesquisadores e equipes tecnicas vinculadas a projetos da FAPERN'
        return 'Pesquisadores, grupos de pesquisa e instituicoes cientificas do Rio Grande do Norte'

    def _first_sentence(self, text: str) -> str:
        parts = [part.strip() for part in text.replace('\n', ' ').split('. ') if part.strip()]
        if not parts:
            return ''
        sentence = parts[0]
        if not sentence.endswith('.'):
            sentence += '.'
        return sentence

    def _html_to_text(self, value: Any) -> str:
        if value is None:
            return ''
        return self._clean_text(BeautifulSoup(str(value), 'html.parser').get_text(' ', strip=True))

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())
