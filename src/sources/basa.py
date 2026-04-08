from __future__ import annotations

import re
from datetime import datetime
from typing import Any
from urllib.parse import urljoin

from src.sources.base_source import BaseSource


class BASASource(BaseSource):
    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        text = self._clean_text(soup.get_text("\n", strip=True))
        opening_date, expiration_date = self._extract_submission_window(text)

        if expiration_date and self._is_expired(expiration_date):
            return []

        title = self._extract_title(soup)
        summary = self._extract_summary(soup)
        edital_link = self._extract_notice_link(soup)
        if not title or not summary or not edital_link:
            return []

        return [
            {
                "titulo": title,
                "orgao": self.config.nome,
                "fonte": self.config.sigla,
                "uf": self.config.uf,
                "categoria": "pesquisa",
                "link": edital_link,
                "resumo": summary,
                "publico_alvo": "Pesquisadores e instituicoes de ensino, ciencia, tecnologia e inovacao da regiao amazonica",
                "data_abertura": opening_date,
                "data_expiracao": expiration_date,
                "status": "aberto",
            }
        ]

    def _extract_title(self, soup) -> str | None:
        for selector in ("h2", "h1", "h3"):
            for node in soup.select(selector):
                text = self._clean_text(node.get_text(" ", strip=True))
                if "pesquisa" in text.lower() and "edital" in text.lower():
                    return text
        return None

    def _extract_summary(self, soup) -> str | None:
        for paragraph in soup.select("p"):
            text = self._clean_text(paragraph.get_text(" ", strip=True))
            lower = text.lower()
            if not text or len(text) < 60:
                continue
            if "torna publico as inscricoes" in lower or "torna publico as inscricoes a selecao" in lower:
                return text
            if lower.startswith("o objetivo do certame"):
                return text
        return None

    def _extract_notice_link(self, soup) -> str | None:
        for anchor in soup.select("a[href]"):
            label = self._clean_text(anchor.get_text(" ", strip=True)).lower()
            href = self._clean_text(anchor.get("href"))
            if not href:
                continue
            if "edital de pesquisa" in label or ("edital" in label and "pesquisa" in label):
                return urljoin(self.config.site_oficial, href)
        return None

    def _extract_submission_window(self, text: str) -> tuple[str | None, str | None]:
        match = re.search(
            r"periodo de divulgacao e inscricao das propostas\s*(\d{1,2}/\d{1,2}/\d{4})\s*(\d{1,2}/\d{1,2}/\d{4})",
            text.lower(),
            flags=re.I,
        )
        if match:
            return match.group(1), match.group(2)
        return None, None

    def _is_expired(self, value: str) -> bool:
        try:
            expiration = datetime.strptime(value, "%d/%m/%Y").date()
        except ValueError:
            return False
        return expiration < datetime.now().date()

    def _clean_text(self, value: Any) -> str:
        if value is None:
            return ""
        return " ".join(str(value).replace("\xa0", " ").split())
