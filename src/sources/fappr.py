from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

from bs4 import Tag

from src.sources.base_source import BaseSource


class FAPPRSource(BaseSource):
    TITLE_CODE_PATTERN = re.compile(r'^(CP|PI)\s+(\d{2})/(\d{2,4})', re.I)
    DEADLINE_PATTERN = re.compile(r'(\d{1,2}/\d{1,2}/\d{4})')
    INCLUDE_LINK_HINTS = ('edital', 'diretrizes para a chamada')
    EXCLUDE_LINK_HINTS = ('anexos', 'resultado', 'ato defa', 'adequação', 'adequacao', 'formulário', 'formulario')
    PARCERIA_EXCLUDE_HINTS = ('artigos na revista',)

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for block in soup.select('div.row.two-col-right'):
            title = self._extract_title(block)
            if not title:
                continue

            section = self._extract_section(block)
            if not self._is_relevant_block(title, section):
                continue

            summary = self._extract_summary(block) or title
            link = self._select_main_link(block, title, section)
            if not link or link in seen:
                continue

            opening_date, expiration_date = self._extract_dates(block)
            if not expiration_date and not self._is_fluxo_continuo(block):
                continue

            seen.add(link)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._infer_categoria(title, summary),
                    'link': link,
                    'resumo': summary,
                    'publico_alvo': self._infer_publico_alvo(title, summary),
                    'data_abertura': opening_date,
                    'data_expiracao': expiration_date,
                }
            )

        return items

    def _extract_title(self, block: Tag) -> str:
        for heading in block.select('h3'):
            text = self._clean_text(heading.get_text(' ', strip=True))
            if text:
                return text
        return ''

    def _extract_section(self, block: Tag) -> str:
        section_heading = block.find_previous(
            lambda tag: isinstance(tag, Tag)
            and tag.name == 'h3'
            and 'text-align-center' in (tag.get('class') or [])
            and self._clean_text(tag.get_text(' ', strip=True))
        )
        if not section_heading:
            return ''
        return self._clean_text(section_heading.get_text(' ', strip=True))

    def _is_relevant_block(self, title: str, section: str) -> bool:
        lower_title = title.lower()
        if section == 'Parcerias da Araucária':
            return not any(hint in lower_title for hint in self.PARCERIA_EXCLUDE_HINTS)
        return bool(self.TITLE_CODE_PATTERN.match(title))

    def _extract_summary(self, block: Tag) -> str:
        paragraph = block.find('p')
        if not paragraph:
            return ''
        return self._clean_text(paragraph.get_text(' ', strip=True))

    def _select_main_link(self, block: Tag, title: str, section: str) -> str:
        code_prefix, code_number = self._extract_code(title)

        for anchor in block.select('a[href]'):
            href = self._clean_text(anchor.get('href'))
            label = self._clean_text(anchor.get_text(' ', strip=True))
            lower_label = label.lower()
            if not href:
                continue
            if not any(hint in lower_label for hint in self.INCLUDE_LINK_HINTS):
                continue
            if any(hint in lower_label for hint in self.EXCLUDE_LINK_HINTS):
                continue
            if section != 'Parcerias da Araucária' and code_prefix and code_number:
                if code_prefix not in label.upper() or f'{code_number}/' not in label:
                    continue
            return urljoin(self.config.site_oficial, href)

        return ''

    def _extract_code(self, title: str) -> tuple[str, str]:
        match = self.TITLE_CODE_PATTERN.match(title)
        if not match:
            return '', ''
        return match.group(1).upper(), match.group(2)

    def _extract_dates(self, block: Tag) -> tuple[str | None, str | None]:
        opening_date: str | None = None
        expiration_date: str | None = None

        for item in block.select('li'):
            text = self._clean_text(item.get_text(' ', strip=True))
            if not text:
                continue

            lower_text = text.lower()
            dates = self.DEADLINE_PATTERN.findall(text)
            if not dates:
                continue

            if opening_date is None and 'manifestação de interesse' in lower_text:
                opening_date = dates[0]
            if any(hint in lower_text for hint in ('inscrição', 'inscrições', 'indicação/inscrição', 'indicacao/inscricao', 'manifestação de interesse', 'manifestacao de interesse')):
                expiration_date = dates[-1]

        return opening_date, expiration_date

    def _is_fluxo_continuo(self, block: Tag) -> bool:
        text = self._clean_text(block.get_text(' ', strip=True)).lower()
        return 'fluxo contínuo' in text or 'fluxo continuo' in text

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'bolsa' in combined or 'pibic' in combined or 'pibit' in combined or 'pibex' in combined or 'pibis' in combined:
            return 'bolsa'
        if 'evento' in combined or 'prêmio' in combined or 'premio' in combined:
            return 'divulgacao'
        if 'inovação' in combined or 'inovacao' in combined:
            return 'inovacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str, summary: str) -> str:
        combined = f'{title} {summary}'.lower()
        if 'ucran' in combined:
            return 'Pesquisadores ucranianos, universidades e ICTs do Paraná'
        if 'mitacs' in combined or 'brasillinois' in combined or 'horizon' in combined or 'marie' in combined or 'la trobe' in combined:
            return 'Pesquisadores, ICTs e redes de cooperação internacional do Paraná'
        if 'pibic' in combined or 'pibit' in combined or 'pibex' in combined or 'pibis' in combined or 'graduação' in combined or 'graduacao' in combined:
            return 'Estudantes de graduação, pesquisadores e instituições do Paraná'
        if 'evento' in combined:
            return 'Associações científicas, institutos de pesquisa e organizadores de eventos do Paraná'
        if 'inct' in combined:
            return 'Institutos Nacionais de Ciência e Tecnologia e instituições de pesquisa do Paraná'
        return 'Pesquisadores, ICTs e instituições do Paraná'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())
