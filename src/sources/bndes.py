from __future__ import annotations

from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from src.sources.base_source import BaseSource


class BNDESSource(BaseSource):
    USER_AGENT = {"User-Agent": "editais-bot/1.0"}
    TITLE_HINTS = ("bndes fep", "estudo")

    def fetch(self) -> str:
        response = requests.get(
            self.config.pagina_editais,
            timeout=max(self.timeout, 60),
            headers=self.USER_AGENT,
        )
        response.raise_for_status()
        response.encoding = response.apparent_encoding or response.encoding
        return response.text

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        calls_container = self._find_calls_container(soup)
        if calls_container is None:
            return items

        for anchor in calls_container.select("a[href]"):
            title = self._clean_text(anchor.get_text(" ", strip=True))
            href = self._clean_text(anchor.get("href"))
            if not title or not href:
                continue

            lower_title = title.lower()
            if not any(hint in lower_title for hint in self.TITLE_HINTS):
                continue

            full_href = urljoin(self.config.site_oficial, href)
            if full_href in seen:
                continue

            seen.add(full_href)
            items.append(
                {
                    "titulo": title,
                    "orgao": self.config.nome,
                    "fonte": self.config.sigla,
                    "uf": self.config.uf,
                    "categoria": "pesquisa",
                    "link": full_href,
                    "resumo": "Chamada do BNDES FEP para estudos, pesquisas e estruturação de projetos com impacto econômico e social.",
                    "publico_alvo": "Empresas, consultorias, pesquisadores e parceiros estrategicos ligados a estudos e projetos apoiados pelo BNDES",
                    "data_abertura": None,
                    "data_expiracao": None,
                    "status": "aberto",
                }
            )

        return items

    def _find_calls_container(self, soup: BeautifulSoup) -> Tag | None:
        heading = soup.find(
            lambda node: getattr(node, "name", None) in {"h2", "h3", "h4"}
            and "chamadas em andamento" in self._clean_text(node.get_text(" ", strip=True)).lower()
        )
        if heading is None:
            return None

        for sibling in heading.find_all_next():
            if getattr(sibling, "name", None) in {"h2", "h3", "h4"}:
                break
            if getattr(sibling, "name", None) in {"ul", "ol", "div"} and sibling.select("a[href]"):
                return sibling
        return None

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).replace("\xa0", " ").split())
