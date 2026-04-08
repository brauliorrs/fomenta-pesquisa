from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class FAPACSource(BaseSource):
    INCLUDE_HINTS = ('edital', 'chamada', 'chamamento', 'processo seletivo', 'inscri')
    EXCLUDE_HINTS = (
        'resultado',
        'errata',
        'retifica',
        'retificação',
        'homologa',
        'encerrado',
        'encerrada',
        'comunicado',
        'anexo',
        'formulario',
        'formulário',
    )

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for anchor in soup.select('a[href], h2 a[href], h3 a[href], h4 a[href]'):
            title = self._clean_text(anchor.get_text(' ', strip=True))
            href = self._clean_text(anchor.get('href'))
            if not title:
                continue

            lower_title = title.lower()
            if any(hint in lower_title for hint in self.EXCLUDE_HINTS):
                continue
            if not any(hint in lower_title for hint in self.INCLUDE_HINTS):
                continue

            full_href = urljoin(self.config.site_oficial, href) if href else self.config.pagina_editais
            if full_href in seen:
                continue
            seen.add(full_href)

            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': self._infer_categoria(title),
                    'link': full_href,
                    'resumo': self._infer_summary(anchor) or title,
                    'publico_alvo': self._infer_publico_alvo(title),
                    'data_abertura': None,
                    'data_expiracao': None,
                    'status': 'aberto',
                }
            )

        return items

    def _infer_summary(self, anchor: BeautifulSoup) -> str:
        container = anchor.find_parent(['li', 'article', 'div', 'section']) or anchor.parent
        if container is None:
            return ''
        text = self._clean_text(container.get_text(' ', strip=True))
        if text and len(text) >= 50:
            return text
        return ''

    def _infer_categoria(self, title: str) -> str:
        lower_title = title.lower()
        if any(token in lower_title for token in ('bolsa', 'mentoria')):
            return 'bolsa'
        if any(token in lower_title for token in ('inov', 'cadeia produtiva', 'tecnolog')):
            return 'inovacao'
        return 'pesquisa'

    def _infer_publico_alvo(self, title: str) -> str:
        lower_title = title.lower()
        if any(token in lower_title for token in ('sociedade civil', 'organizacoes', 'organizações')):
            return 'Organizacoes da sociedade civil e parceiros institucionais do Acre'
        if any(token in lower_title for token in ('bolsa', 'mentoria', 'inov')):
            return 'Pesquisadores, bolsistas, mentores e empreendedores do Acre'
        return 'Pesquisadores, grupos de pesquisa e instituicoes cientificas do Acre'

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ''
        return ' '.join(str(value).replace('\xa0', ' ').split())
