from __future__ import annotations

from urllib.parse import urljoin

from bs4 import BeautifulSoup

from src.sources.base_source import BaseSource


class GenericDiscoverySource(BaseSource):
    def parse(self, raw_content: str) -> list[dict]:
        soup = self.soup(raw_content)
        selectors = self.config.selectors or {}
        item_selector = selectors.get('item') or 'a'
        title_selector = selectors.get('title') or ''
        link_selector = selectors.get('link') or ''
        summary_selector = selectors.get('summary') or ''
        status_selector = selectors.get('status') or ''
        category = selectors.get('categoria') or 'geral'

        items: list[dict] = []
        for node in soup.select(item_selector):
            title = self._extract_title(node, title_selector)
            href = self._extract_href(node, link_selector)
            if not title or not href:
                continue

            full_href = urljoin(self.config.pagina_editais, href)
            summary = self._extract_summary(node, summary_selector, title)
            status = self._extract_status(node, status_selector)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': category,
                    'link': full_href,
                    'resumo': summary,
                    'publico_alvo': '',
                    'status': status,
                }
            )

        return self._deduplicate(items)

    def _extract_title(self, node, title_selector: str) -> str:
        if title_selector:
            title_node = node.select_one(title_selector)
            if title_node:
                return title_node.get_text(' ', strip=True)

        for selector in ('h1', 'h2', 'h3', 'h4', 'strong', 'b', 'a'):
            title_node = node.select_one(selector)
            if title_node:
                title = title_node.get_text(' ', strip=True)
                if title:
                    return title

        return node.get_text(' ', strip=True)

    def _extract_href(self, node, link_selector: str) -> str:
        if link_selector:
            link_node = node.select_one(link_selector)
            if link_node and link_node.get('href'):
                return str(link_node.get('href')).strip()

        if node.get('href'):
            return str(node.get('href')).strip()

        link_node = node.select_one('a[href]')
        if link_node and link_node.get('href'):
            return str(link_node.get('href')).strip()
        return ''

    def _extract_summary(self, node, summary_selector: str, title: str) -> str:
        if summary_selector:
            summary_node = node.select_one(summary_selector)
            if summary_node:
                summary = summary_node.get_text(' ', strip=True)
                if summary:
                    return summary

        summary = node.get_text(' ', strip=True)
        if summary == title:
            return ''
        return summary

    def _extract_status(self, node, status_selector: str) -> str:
        if status_selector:
            status_node = node.select_one(status_selector)
            if status_node:
                return status_node.get_text(' ', strip=True)
        return node.get_text(' ', strip=True)

    def _deduplicate(self, items: list[dict]) -> list[dict]:
        seen: set[tuple[str, str]] = set()
        deduplicated: list[dict] = []
        for item in items:
            key = (item.get('titulo', '').strip(), item.get('link', '').strip())
            if not all(key) or key in seen:
                continue
            seen.add(key)
            deduplicated.append(item)
        return deduplicated
