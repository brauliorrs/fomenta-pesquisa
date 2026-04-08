from __future__ import annotations

import json
from datetime import date
from typing import Any

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPEMIGSource(BaseSource):
    EXPORT_URL = 'https://api.site.fapemig.br/wp-json/fapemig-chamadas-novo/v1/chamadas/export?format=json'
    USER_AGENT = {'User-Agent': 'editais-bot/1.0'}
    CATEGORY_HINTS = {
        'inovacao': 'inovacao',
        'divulgacao': 'divulgacao',
        'bolsa': 'bolsa',
    }
    ATTACHMENT_INCLUDE_HINTS = ('chamada', 'edital', 'portaria', 'diretriz')
    ATTACHMENT_EXCLUDE_HINTS = (
        'anexo',
        'resultado',
        'ato de resultado',
        'ato preliminar',
        'termo',
        'declaracao',
        'declaração',
        'guia',
        'plano de trabalho',
        'pergunta',
        'faq',
    )

    def fetch(self) -> str:
        response = requests.get(
            self.EXPORT_URL,
            timeout=self.timeout,
            headers=self.USER_AGENT,
        )
        response.raise_for_status()
        return response.text

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        payload = self._decode_payload(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for item in payload:
            if not self._is_open_call(item):
                continue

            title = self._clean_text(item.get('titulo'))
            expiration = self._extract_expiration(item)
            if not title or not expiration or self._is_past(expiration):
                continue

            link = self._select_link(item)
            if not link or link in seen:
                continue

            seen.add(link)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._infer_category(item, title),
                    'link': link,
                    'resumo': self._build_summary(item, title),
                    'publico_alvo': self._build_publico_alvo(item, title),
                    'data_abertura': self._extract_opening(item),
                    'data_expiracao': expiration,
                }
            )

        return items

    def _decode_payload(self, raw_content: str) -> list[dict[str, Any]]:
        decoded = json.loads(raw_content)
        if isinstance(decoded, str):
            decoded = json.loads(decoded)
        if isinstance(decoded, list):
            return [item for item in decoded if isinstance(item, dict)]
        return []

    def _is_open_call(self, item: dict[str, Any]) -> bool:
        status = self._clean_text(item.get('status')).lower()
        post_status = self._clean_text(item.get('post_status')).lower()
        ativo = str(item.get('ativo', '')).strip().lower()
        return status == 'aberta' and post_status == 'publish' and ativo in {'1', 'true'}

    def _extract_opening(self, item: dict[str, Any]) -> str | None:
        schedule = item.get('cronograma_submissao') or []
        starts = [
            str(entry.get('inicio_date')).strip()
            for entry in schedule
            if isinstance(entry, dict) and str(entry.get('inicio_date') or '').strip()
        ]
        if starts:
            return min(starts)

        created_at = self._clean_text(item.get('created_at'))
        if created_at:
            return created_at.split(' ', 1)[0]
        return None

    def _extract_expiration(self, item: dict[str, Any]) -> str | None:
        schedule = item.get('cronograma_submissao') or []
        deadlines = [
            str(entry.get('fim_date')).strip()
            for entry in schedule
            if isinstance(entry, dict) and str(entry.get('fim_date') or '').strip()
        ]
        if deadlines:
            return max(deadlines)
        return None

    def _is_past(self, date_value: str) -> bool:
        try:
            parsed = date.fromisoformat(date_value)
        except ValueError:
            return False
        return parsed < date.today()

    def _infer_category(self, item: dict[str, Any], title: str) -> str:
        hints = [self._clean_text(value).lower() for value in item.get('linhas_fomento') or []]
        combined = f"{title} {' '.join(hints)}".lower()

        if 'credenciamento' in combined or 'capacita' in combined or 'recursos humanos' in combined:
            return 'formacao'

        for hint, category in self.CATEGORY_HINTS.items():
            if hint in combined:
                return category

        if 'evento' in combined or 'divulgacao' in combined:
            return 'divulgacao'
        if 'startup' in combined or 'empresa' in combined:
            return 'inovacao'
        if 'bolsa' in combined or 'pibic' in combined or 'pibiti' in combined:
            return 'bolsa'
        return 'pesquisa'

    def _build_summary(self, item: dict[str, Any], fallback_title: str) -> str:
        description = self._clean_text(item.get('descricao_chamada'))
        if description:
            return self._first_sentence(description)

        audience = self._clean_text(item.get('quem_pode_participar'))
        if audience:
            return self._first_sentence(audience)

        numero = self._clean_text(item.get('numero'))
        if numero:
            return f'Chamada FAPEMIG {numero} com inscricoes abertas.'
        return fallback_title

    def _build_publico_alvo(self, item: dict[str, Any], title: str) -> str:
        explicit = self._clean_text(item.get('quem_pode_participar'))
        if explicit:
            return explicit

        combined = title.lower()
        if 'empresa' in combined or 'startup' in combined:
            return 'Empresas, cooperativas e ICTs de Minas Gerais'
        if 'evento' in combined or 'divulgacao' in combined:
            return 'Pesquisadores, estudantes e instituicoes cientificas de Minas Gerais'
        if 'credenciamento' in combined or 'recursos humanos' in combined:
            return 'Instituicoes cientificas, programas de formacao e pesquisadores de Minas Gerais'
        return 'Pesquisadores, grupos de pesquisa e instituicoes de Minas Gerais'

    def _select_link(self, item: dict[str, Any]) -> str:
        numero = self._clean_text(item.get('numero')).lower()
        best_score = -1
        best_url = ''

        for attachment in item.get('anexos') or []:
            if not isinstance(attachment, dict):
                continue

            url = self._clean_text(attachment.get('anexo_url'))
            title = self._clean_text(attachment.get('titulo')).lower()
            if not url:
                continue

            score = 0
            if url.lower().endswith('.pdf'):
                score += 1
            if numero and numero in title:
                score += 4
            if any(hint in title for hint in self.ATTACHMENT_INCLUDE_HINTS):
                score += 3
            if any(hint in title for hint in self.ATTACHMENT_EXCLUDE_HINTS):
                score -= 4
            if title.startswith('retificacao') or title.startswith('retificação'):
                score -= 2

            if score > best_score:
                best_score = score
                best_url = url

        if best_score > 0 and best_url:
            return best_url

        slug = self._clean_text(item.get('slug'))
        if slug:
            return f"{self.config.site_oficial.rstrip('/')}/oportunidades/chamadas-e-editais/{slug}"
        return self.config.pagina_editais

    def _first_sentence(self, text: str) -> str:
        parts = [part.strip() for part in text.replace('\n', ' ').split('. ') if part.strip()]
        if not parts:
            return text
        sentence = parts[0]
        if not sentence.endswith('.'):
            sentence += '.'
        return sentence

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        text = BeautifulSoup(str(value), 'html.parser').get_text(' ', strip=True)
        return ' '.join(text.split())
