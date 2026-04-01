from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any

from bs4 import BeautifulSoup
import requests

from src.models import SourceConfig


class BaseSource(ABC):
    def __init__(self, config: SourceConfig, timeout: int = 30) -> None:
        self.config = config
        self.timeout = timeout

    @property
    def name(self) -> str:
        return self.config.sigla

    def fetch(self) -> str:
        response = requests.get(
            self.config.pagina_editais,
            timeout=self.timeout,
            headers={"User-Agent": "editais-bot/1.0"},
        )
        response.raise_for_status()
        return response.text

    def soup(self, raw_content: str) -> BeautifulSoup:
        return BeautifulSoup(raw_content, "html.parser")

    @abstractmethod
    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def collect(self) -> list[dict[str, Any]]:
        raw_content = self.fetch()
        return self.parse(raw_content)
