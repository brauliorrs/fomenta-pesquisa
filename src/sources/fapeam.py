from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPEAMSource(BaseSource):
    AJAX_URL = 'https://www.fapeam.am.gov.br/wp-admin/admin-ajax.php?action=get-editais'
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    MAX_PAGES = 6
    EXCLUDE_HINTS = ('resultado', 'retifica', 'errata', 'homologa', 'encerrad')

    def collect(self) -> list[dict[str, Any]]:
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for page in range(1, self.MAX_PAGES + 1):
            payload = self._fetch_page(page)
            page_items = self._decode_payload(payload)
            if not page_items:
                break

            for entry in page_items:
                detail_url = self._clean_text(entry.get('permalink'))
                if not detail_url or detail_url in seen:
                    continue

                seen.add(detail_url)
                item = self._build_item(entry, detail_url)
                if item:
                    items.append(item)

            if not self._has_next_page(payload):
                break

        return items

    def fetch(self) -> str:
        payload = self._fetch_page(1)
        return json.dumps(payload, ensure_ascii=False)

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        payload = json.loads(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for entry in self._decode_payload(payload):
            detail_url = self._clean_text(entry.get('permalink'))
            if not detail_url or detail_url in seen:
                continue

            seen.add(detail_url)
            item = self._build_item(entry, detail_url)
            if item:
                items.append(item)

        return items

    def _fetch_page(self, page: int) -> dict[str, Any]:
        response = requests.post(
            self.AJAX_URL,
            data={'tipo': 'editais-abertos', 'p': str(page), 'paginacao': '1'},
            headers={**self.USER_AGENT, 'Content-Type': 'application/x-www-form-urlencoded; charset=utf-8'},
            timeout=self.timeout,
        )
        response.raise_for_status()
        payload = response.json()
        return payload if isinstance(payload, dict) else {}

    def _decode_payload(self, payload: dict[str, Any] | list[Any] | Any) -> list[dict[str, Any]]:
        if isinstance(payload, dict):
            items = payload.get('editais_formatted') or []
        elif isinstance(payload, list):
            items = payload
        else:
            items = []
        return [item for item in items if isinstance(item, dict)]

    def _has_next_page(self, payload: dict[str, Any]) -> bool:
        pagination = self._clean_text(payload.get('paginacao'))
        return bool(pagination)

    def _build_item(self, entry: dict[str, Any], detail_url: str) -> dict[str, Any] | None:
        title = self._clean_text(entry.get('post_title'))
        if not title:
            return None

        lower_title = title.lower()
        if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
            return None

        opening_date, expiration_date = self._extract_vigencia(entry.get('vigencia'))
        soup = self._fetch_soup(detail_url)
        summary = self._extract_summary(soup) if soup is not None else ''
        if not summary:
            summary = f'{title}.'

        notice_link = self._extract_notice_link(soup, detail_url) if soup is not None else detail_url

        return {
            'titulo': title,
            'orgao': self.config.nome,
            'fonte': self.config.sigla,
            'uf': self.config.uf,
            'categoria': self._infer_categoria(title, summary),
            'link': notice_link or detail_url,
            'resumo': summary,
            'publico_alvo': self._infer_publico_alvo(title, summary),
            'data_abertura': opening_date,
            'data_expiracao': expiration_date,
            'status': 'aberto',
        }

    def _fetch_soup(self, url: str) -> BeautifulSoup | None:
        try:
            response = requests.get(url, timeout=self.timeout, headers=self.USER_AGENT)
            response.raise_for_status()
        except Exception:
            return None
        return BeautifulSoup(response.text, 'html.parser')

    def _extract_vigencia(self, value: Any) -> tuple[str | None, str | None]:
        text = self._clean_text(value)
        match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})\s+at[eé]\s+(\d{1,2}/\d{1,2}/\d{4})', text, flags=re.I)
        if not match:
            return None, None
        return match.group(1), match.group(2)

    def _extract_summary(self, soup: BeautifulSoup) -> str:
        for paragraph in soup.select('article p, .entry-content p, main p'):
            text = self._clean_text(paragraph.get_text(' ', strip=True))
            if len(text) >= 80:
                return text
        return ''

    def _extract_notice_link(self, soup: BeautifulSoup, detail_url: str) -> str:
        best_score = -1
        best_href = detail_url

        for anchor in soup.select('a[href]'):
            href = self._clean_text(anchor.get('href'))
            label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
            if not href:
                continue

            full_href = urljoin(detail_url, href)
            lower_href = full_href.lower()
            score = 0
            if lower_href.endswith('.pdf') or '.pdf?' in lower_href:
                score += 3
            if any(token in label for token in ('edital', 'chamada')):
                score += 4
            if any(token in label for token in ('retifica', 'extrato', 'resultado', 'errata')):
                score -= 5

            if score > best_score:
                best_score = score
                best_href = full_href

        return best_href

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('lidera', 'inov', 'tecnolog', 'socio tech', 'empresa')):
            return 'inovacao'
        if any(token in combined for token in ('bolsa', 'mestre', 'doutor')):
            return 'bolsa'
        if any(token in combined for token in ('popularizacao', 'museu', 'colecoes biologicas')):
            return 'divulgacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('mulheres', 'feminina', 'cientista')):
            return 'Pesquisadoras, liderancas femininas e instituicoes cientificas do Amazonas'
        if any(token in combined for token in ('empresa', 'inovacao', 'tecnologia social', 'ecoturismo')):
            return 'Empresas, empreendedores, pesquisadores e ICTs do Amazonas'
        if any(token in combined for token in ('mestre', 'doutor', 'bolsa')):
            return 'Pesquisadores, mestres, doutores e instituicoes de pesquisa do Amazonas'
        return 'Pesquisadores, grupos de pesquisa e instituicoes cientificas do Amazonas'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        text = BeautifulSoup(str(value), 'html.parser').get_text(' ', strip=True)
        return ' '.join(text.replace('\xa0', ' ').split())
