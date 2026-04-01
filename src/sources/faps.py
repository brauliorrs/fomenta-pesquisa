from __future__ import annotations

from src.sources.base_source import BaseSource


class FAPSource(BaseSource):
    def parse(self, raw_content: str) -> list[dict]:
        return []
