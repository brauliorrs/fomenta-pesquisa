from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPDFSource(BaseSource):
    EXCLUDE_HINTS = ('resultado', 'homologa', 'encerrad', 'revogad', 'cancelad')
    LINK_EXCLUDE_HINTS = ('retifica', 'extrato', 'contrapartidas', 'resultado', 'formulario', 'republicacao')

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for button in soup.select('button.panel-header'):
            title_node = button.select_one('.panel-title')
            title = self._clean_text(title_node.get_text(' ', strip=True) if title_node else button.get_text(' ', strip=True))
            if not title:
                continue

            lower_title = title.lower()
            if not any(token in lower_title for token in ('edital', 'chamada')):
                continue
            if any(token in lower_title for token in self.EXCLUDE_HINTS):
                continue

            collapse = button.find_next_sibling('div')
            if collapse is None:
                continue

            body = collapse.select_one('.panel-body') or collapse
            primary_link = self._extract_primary_link(body)
            if not primary_link or primary_link in seen:
                continue

            seen.add(primary_link)
            body_text = self._clean_text(body.get_text(' ', strip=True))
            opening_date, expiration_date = self._extract_submission_period(body_text)
            summary = self._build_summary(title, body)

            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._infer_categoria(title, summary),
                    'link': primary_link,
                    'resumo': summary,
                    'publico_alvo': self._infer_publico_alvo(title, summary),
                    'data_abertura': opening_date,
                    'data_expiracao': expiration_date,
                    'status': 'aberto',
                }
            )

        return items

    def _extract_primary_link(self, body: BeautifulSoup) -> str | None:
        best_score = -1
        best_href: str | None = None

        for anchor in body.select('a[href]'):
            href = self._clean_text(anchor.get('href'))
            label = self._clean_text(anchor.get_text(' ', strip=True)).lower()
            if not href:
                continue

            full_href = urljoin(self.config.site_oficial, href)
            lower_href = full_href.lower()
            score = 0
            if lower_href.endswith('.pdf') or '.pdf' in lower_href:
                score += 3
            if any(token in label for token in ('edital', 'chamada')):
                score += 4
            if any(token in label for token in self.LINK_EXCLUDE_HINTS):
                score -= 6
            if any(token in lower_href for token in ('retificacao', 'retifica', 'extrato', 'resultado')):
                score -= 5

            if score > best_score:
                best_score = score
                best_href = full_href

        return best_href

    def _extract_submission_period(self, text: str) -> tuple[str | None, str | None]:
        match = re.search(
            r'PER[ÍI]ODO DE SUBMISS[ÃA]O\s*:?\s*(\d{1,2}/\d{1,2}/\d{4})\s*[AaÀà]\s*(\d{1,2}/\d{1,2}/\d{4})',
            text,
            flags=re.I,
        )
        if match:
            return match.group(1), match.group(2)

        single_match = re.search(r'(\d{1,2}/\d{1,2}/\d{4})', text)
        if single_match:
            return single_match.group(1), None

        return None, None

    def _build_summary(self, title: str, body: BeautifulSoup) -> str:
        for paragraph in body.select('p'):
            text = self._clean_text(paragraph.get_text(' ', strip=True))
            lower = text.lower()
            if not text:
                continue
            if any(lower.startswith(prefix) for prefix in ('extrato', 'periodo de submissao', 'período de submissão', 'formularios', 'formulários', 'resultados')):
                continue
            if any(token in lower for token in ('retifica', 'contrapartidas de comunicacao')):
                continue
            if len(text) >= 70:
                return text

        return f'{title} com inscricoes abertas na FAPDF.'

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('learning', 'startup', 'inovadora', 'inovacao')):
            return 'inovacao'
        if any(token in combined for token in ('premio', 'pesquisador destaque')):
            return 'divulgacao'
        if any(token in combined for token in ('mestrado', 'doutorado', 'pdpg', 'bolsa')):
            return 'bolsa'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if any(token in combined for token in ('startup', 'inovadora', 'learning', 'empresa')):
            return 'Pesquisadores, empresas, startups e instituicoes do Distrito Federal'
        if any(token in combined for token in ('mestrado', 'doutorado', 'pdpg', 'pos-graduacao')):
            return 'Programas de pos-graduacao, pesquisadores e instituicoes do Distrito Federal'
        if 'extensao' in combined:
            return 'Instituicoes de ensino superior, pesquisadores e projetos de extensao do Distrito Federal'
        return 'Pesquisadores, grupos de pesquisa e instituicoes cientificas do Distrito Federal'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        text = BeautifulSoup(str(value), 'html.parser').get_text(' ', strip=True)
        return ' '.join(text.replace('\xa0', ' ').split())
