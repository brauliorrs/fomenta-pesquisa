from __future__ import annotations

import re
from typing import Any
from urllib.parse import urljoin

import requests
from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class DECITSource(BaseSource):
    USER_AGENT = {"User-Agent": "editais-bot/1.0"}
    INCLUDE_KEYWORDS = ("chamada", "pesquisa", "sus")
    EXCLUDE_KEYWORDS = ("seminario", "seminário", "evento", "agenda", "vacinacao", "vacinação")

    def collect(self) -> list[dict[str, Any]]:
        listing_soup = self._fetch_soup(self.config.pagina_editais)
        if listing_soup is None:
            return []

        items: list[dict[str, Any]] = []
        seen: set[str] = set()

        for article_url, fallback_title in self._extract_candidate_articles(listing_soup):
            article_soup = self._fetch_soup(article_url)
            if article_soup is None:
                continue

            for item in self._parse_article(article_soup, article_url, fallback_title):
                link = item.get("link") or ""
                if not link or link in seen:
                    continue
                seen.add(link)
                items.append(item)

        return items

    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        soup = self.soup(raw_content)
        return self._parse_article(soup, self.config.pagina_editais, None)

    def _extract_candidate_articles(self, soup: BeautifulSoup) -> list[tuple[str, str]]:
        articles: list[tuple[str, str]] = []
        seen: set[str] = set()

        for anchor in soup.select("a.summary.url[href], a[href]"):
            title = self._clean_text(anchor.get_text(" ", strip=True))
            href = self._clean_text(anchor.get("href"))
            if not title or not href:
                continue
            if "/assuntos/noticias/" not in href:
                continue

            normalized = self._normalize_text(title)
            if not all(keyword in normalized for keyword in self.INCLUDE_KEYWORDS):
                continue
            if any(keyword in normalized for keyword in self.EXCLUDE_KEYWORDS):
                continue

            full_href = urljoin(self.config.site_oficial, href)
            if full_href in seen:
                continue

            seen.add(full_href)
            articles.append((full_href, title))

            if len(articles) >= 5:
                break

        return articles

    def _parse_article(self, soup: BeautifulSoup, article_url: str, fallback_title: str | None) -> list[dict[str, Any]]:
        article_title = self._extract_article_title(soup) or fallback_title or "Chamadas Publicas do DECIT"
        description = self._extract_article_description(soup) or article_title
        opening_date = self._extract_article_date(soup)
        expiration_date = self._extract_deadline(soup.get_text("\n", strip=True))

        items: list[dict[str, Any]] = []
        for anchor in soup.select("a[href]"):
            title = self._clean_text(anchor.get_text(" ", strip=True))
            href = self._clean_text(anchor.get("href"))
            if not title or not href:
                continue

            full_href = urljoin(article_url, href)
            lower_href = full_href.lower()
            lower_title = self._normalize_text(title)
            if "chamadas-publicas" not in lower_href and "iddivulgacao=" not in lower_href:
                continue
            if "chamada" not in lower_title:
                continue

            items.append(
                {
                    "titulo": title,
                    "orgao": self.config.nome,
                    "fonte": self.config.sigla,
                    "uf": self.config.uf,
                    "categoria": "saude",
                    "link": full_href,
                    "resumo": description,
                    "publico_alvo": "Pesquisadores com titulo de doutor vinculados a instituicoes cientificas, tecnologicas e de inovacao",
                    "data_abertura": opening_date,
                    "data_expiracao": expiration_date,
                    "status": "aberto",
                }
            )

        return items

    def _fetch_soup(self, url: str) -> BeautifulSoup | None:
        try:
            response = requests.get(url, timeout=self.timeout, headers=self.USER_AGENT)
            response.raise_for_status()
        except Exception:
            return None

        response.encoding = response.apparent_encoding or response.encoding
        return BeautifulSoup(response.text, "html.parser")

    def _extract_article_title(self, soup: BeautifulSoup) -> str | None:
        node = soup.select_one("h1.documentFirstHeading, h1")
        if node:
            return self._clean_text(node.get_text(" ", strip=True))
        return None

    def _extract_article_description(self, soup: BeautifulSoup) -> str | None:
        for selector in ("div.documentDescription", "meta[name='description']", "meta[property='og:description']"):
            node = soup.select_one(selector)
            if node is None:
                continue
            if node.name == "meta":
                text = self._clean_text(node.get("content"))
            else:
                text = self._clean_text(node.get_text(" ", strip=True))
            if text:
                return text
        return None

    def _extract_article_date(self, soup: BeautifulSoup) -> str | None:
        for selector in ("span.documentPublished time", "time"):
            node = soup.select_one(selector)
            if node is None:
                continue
            token = self._clean_text(node.get("datetime") or node.get_text(" ", strip=True))
            normalized = self._normalize_date_token(token)
            if normalized:
                return normalized
        return None

    def _extract_deadline(self, text: str) -> str | None:
        clean = self._clean_text(text)
        extenso = re.search(r"ate o dia (\d{1,2}) de ([A-Za-zçãéíóúâêôà]+)", clean, flags=re.I)
        if not extenso:
            return None
        day, month_name = extenso.groups()
        month = self._month_number(month_name)
        if month is None:
            return None
        year = 2026
        return f"{int(day):02d}/{month:02d}/{year}"

    def _normalize_date_token(self, value: str) -> str | None:
        numeric = re.search(r"(\d{4})-(\d{2})-(\d{2})", value)
        if numeric:
            return f"{numeric.group(3)}/{numeric.group(2)}/{numeric.group(1)}"
        return None

    def _month_number(self, value: str) -> int | None:
        months = {
            "janeiro": 1,
            "fevereiro": 2,
            "marco": 3,
            "março": 3,
            "abril": 4,
            "maio": 5,
            "junho": 6,
            "julho": 7,
            "agosto": 8,
            "setembro": 9,
            "outubro": 10,
            "novembro": 11,
            "dezembro": 12,
        }
        return months.get(self._normalize_text(value))

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
