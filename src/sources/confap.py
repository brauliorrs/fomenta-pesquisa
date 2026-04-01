from __future__ import annotations

from src.sources.base_source import BaseSource


class CONFAPSource(BaseSource):
    INCLUDE_KEYWORDS = (
        'edital', 'chamada', 'inscri', 'prêmio', 'premio', 'centelha', 'bolsa', 'compet'
    )
    EXCLUDE_KEYWORDS = (
        'resultado', 'fórum', 'forum', 'publicada na', 'investiga', 'usa novas tecnologias', 'projeto apoiado'
    )

    def parse(self, raw_content: str) -> list[dict]:
        soup = self.soup(raw_content)
        items: list[dict] = []
        seen: set[str] = set()

        for link in soup.select('a[href^="https://news.confap.org.br/"]'):
            href = (link.get('href') or '').strip()
            if '/tag/' in href or href.rstrip('/') == 'https://news.confap.org.br':
                continue
            if href in seen:
                continue

            title_node = link.select_one('h2, h3')
            title = title_node.get_text(' ', strip=True) if title_node else link.get_text(' ', strip=True)
            if not title or len(title) < 20:
                continue

            lower_title = title.lower()
            if not any(keyword in lower_title for keyword in self.INCLUDE_KEYWORDS):
                continue
            if any(keyword in lower_title for keyword in self.EXCLUDE_KEYWORDS):
                continue

            seen.add(href)
            items.append(
                {
                    'titulo': title,
                    'orgao': self.config.nome,
                    'fonte': self.config.sigla,
                    'uf': self.config.uf,
                    'categoria': 'pesquisa',
                    'link': href,
                    'resumo': title,
                    'publico_alvo': 'Pesquisadores e instituicoes de pesquisa',
                    'data_abertura': None,
                    'data_expiracao': None,
                }
            )

            if len(items) >= 20:
                break

        return items
