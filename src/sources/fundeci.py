from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup, Tag

from src.sources.base_source import BaseSource


class FUNDECISource(BaseSource):
    USER_AGENT = {"User-Agent": "editais-bot/1.0"}
    CLOSED_HINTS = ("encerrad", "conclu", "resultado", "revogad", "cancelad")

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for entry in soup.select("ul.list-group li.list-group-item"):
            item = self._parse_entry(entry)
            if item is None:
                continue

            link = item.get("link") or ""
            if not link or link in seen:
                continue

            seen.add(link)
            items.append(item)

        return items

    def _parse_entry(self, entry: Tag) -> dict[str, Any] | None:
        anchor = entry.select_one("a[href]")
        if anchor is None:
            return None

        title = self._clean_text(anchor.get_text(" ", strip=True))
        href = self._clean_text(anchor.get("href"))
        if not title or not href:
            return None

        status = " ".join(
            self._clean_text(node.get_text(" ", strip=True))
            for node in entry.select(".label-item-expand")
            if self._clean_text(node.get_text(" ", strip=True))
        )
        if self._is_closed_status(status):
            return None

        detail_url = urljoin(self.config.site_oficial, href)
        soup = self._fetch_soup(detail_url)
        if soup is None:
            return None

        text = self._clean_text(soup.get_text("\n", strip=True))
        item_title = self._extract_title(soup) or title
        summary = self._extract_summary(soup) or title
        notice_link = self._extract_notice_link(soup) or detail_url
        opening_date, expiration_date = self._extract_submission_window(text)
        if expiration_date is None and self._is_closed_status(text):
            return None

        return {
            "titulo": item_title,
            "orgao": self.config.nome,
            "fonte": self.config.sigla,
            "uf": self.config.uf,
            "categoria": self._infer_categoria(item_title, summary),
            "link": notice_link,
            "resumo": summary,
            "publico_alvo": self._infer_publico_alvo(item_title, summary, text),
            "data_abertura": opening_date,
            "data_expiracao": expiration_date,
            "status": "aberto",
        }

    def _fetch_soup(self, url: str) -> BeautifulSoup | None:
        try:
            response = requests.get(url, timeout=self.timeout, headers=self.USER_AGENT)
            response.raise_for_status()
        except Exception:
            return None

        response.encoding = response.apparent_encoding or response.encoding
        return BeautifulSoup(response.text, "html.parser")

    def _extract_title(self, soup: BeautifulSoup) -> str | None:
        for selector in ("h1.hide-accessible", "main h1", ".portlet-body h1"):
            node = soup.select_one(selector)
            if node is None:
                continue
            text = self._clean_text(node.get_text(" ", strip=True))
            if text and text.lower() != "editais":
                return text
        return None

    def _extract_summary(self, soup: BeautifulSoup) -> str | None:
        skip_prefixes = (
            "conheca os editais",
            "voltar edital",
            "vigencia:",
            "inscricoes",
            "divulgacao",
            "recomendamos a atenta leitura",
            "assista a live",
            "publicacao",
        )
        for paragraph in soup.select("main p, .portlet-body p, article p"):
            text = self._clean_text(paragraph.get_text(" ", strip=True))
            lower = text.lower()
            if not text or len(text) < 80:
                continue
            if any(lower.startswith(prefix) for prefix in skip_prefixes):
                continue
            return text
        return None

    def _extract_notice_link(self, soup: BeautifulSoup) -> str | None:
        candidates: list[str] = []
        for anchor in soup.select("a[href]"):
            label = self._clean_text(anchor.get_text(" ", strip=True)).lower()
            href = self._clean_text(anchor.get("href"))
            if not href:
                continue
            full_href = urljoin(self.config.site_oficial, href)
            lower_href = full_href.lower()
            if not lower_href.endswith(".pdf"):
                continue
            if "edital" not in label and "edital" not in lower_href:
                continue
            if any(token in f"{label} {lower_href}" for token in ("errata", "resultado", "comunicado", "prorrog")):
                continue
            candidates.append(full_href)
        return candidates[0] if candidates else None

    def _extract_submission_window(self, text: str) -> tuple[str | None, str | None]:
        patterns = (
            r"cadastramento e envio de propostas devem ser realizados [^0-9]{0,30}(\d{1,2}/\d{1,2}/\d{4})\s*a\s*(\d{1,2}/\d{1,2}/\d{4})",
            r"cadastro e envio dos projetos\s*(\d{1,2}/\d{1,2}/\d{4})\s*a\s*(\d{1,2}/\d{1,2}/\d{4})",
            r"periodo de divulgacao e inscricao das propostas\s*(\d{1,2}/\d{1,2}/\d{4})\s*(\d{1,2}/\d{1,2}/\d{4})",
            r"inscricoes abertas(?: ate)?[^0-9]{0,20}(\d{1,2}/\d{1,2}/\d{4})\s*a\s*(\d{1,2}/\d{1,2}/\d{4})",
        )
        lower_text = text.lower()
        for pattern in patterns:
            match = re.search(pattern, lower_text, flags=re.I)
            if match:
                return match.group(1), match.group(2)
        return None, None

    def _infer_categoria(self, title: str, summary: str) -> str:
        combined = f"{title} {summary}".lower()
        if any(token in combined for token in ("subvencao", "startup", "empresa", "inovacao")):
            return "inovacao"
        if any(token in combined for token in ("sustent", "caatinga", "residuos")):
            return "sustentabilidade"
        if any(token in combined for token in ("territorial", "transferencia de tecnologia", "difusao")):
            return "desenvolvimento"
        return "pesquisa"

    def _infer_publico_alvo(self, title: str, summary: str, text: str) -> str:
        combined = f"{title} {summary} {text}".lower()
        if "instituicoes publicas e privadas sem fins lucrativos" in combined:
            return "Instituicoes publicas e privadas sem fins lucrativos da area de atuacao do Banco do Nordeste"
        if any(token in combined for token in ("subvencao", "startup", "empresa")):
            return "Empresas, startups e atores do ecossistema de inovacao da area de atuacao do Banco do Nordeste"
        if "agricultura familiar" in combined:
            return "Pesquisadores, instituicoes parceiras e agentes ligados a agricultura familiar do Nordeste"
        return "Pesquisadores, instituicoes de ciencia e tecnologia e entidades da area de atuacao do Banco do Nordeste"

    def _is_closed_status(self, value: str) -> bool:
        normalized = self._normalize_text(value)
        return any(hint in normalized for hint in self.CLOSED_HINTS)

    def _normalize_text(self, value: Any) -> str:
        text = self._clean_text(value).lower()
        replacements = str.maketrans(
            {
                "á": "a",
                "à": "a",
                "â": "a",
                "ã": "a",
                "é": "e",
                "ê": "e",
                "í": "i",
                "ó": "o",
                "ô": "o",
                "õ": "o",
                "ú": "u",
                "ç": "c",
            }
        )
        return text.translate(replacements)

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).replace("\xa0", " ").split())
