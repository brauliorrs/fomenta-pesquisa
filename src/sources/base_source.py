from __future__ import annotations

from abc import ABC, abstractmethod
from time import sleep
from typing import Any
import warnings

from bs4 import BeautifulSoup
import requests

from src.models import SourceConfig


class BaseSource(ABC):
    DEFAULT_HEADERS = {"User-Agent": "editais-bot/1.0"}

    def __init__(self, config: SourceConfig, timeout: int = 30) -> None:
        self.config = config
        self.timeout = timeout

    @property
    def name(self) -> str:
        return self.config.sigla

    def request(self, method: str, url: str, **kwargs: Any) -> requests.Response:
        headers = kwargs.pop('headers', getattr(self, 'USER_AGENT', self.DEFAULT_HEADERS))
        timeout = kwargs.pop('timeout', self.timeout)
        allow_insecure = kwargs.pop('allow_insecure', True)
        last_exc: Exception | None = None

        for attempt in range(3):
            try:
                response = requests.request(
                    method,
                    url,
                    headers=headers,
                    timeout=timeout,
                    **kwargs,
                )
                response.raise_for_status()
                return response
            except requests.exceptions.SSLError as exc:
                last_exc = exc
                if allow_insecure:
                    try:
                        warnings.filterwarnings('ignore', message='Unverified HTTPS request')
                        insecure_kwargs = {**kwargs, 'verify': False}
                        response = requests.request(
                            method,
                            url,
                            headers=headers,
                            timeout=timeout,
                            **insecure_kwargs,
                        )
                        response.raise_for_status()
                        return response
                    except requests.RequestException as insecure_exc:
                        last_exc = insecure_exc
                if attempt == 2:
                    break
            except requests.HTTPError as exc:
                last_exc = exc
                status_code = exc.response.status_code if exc.response is not None else None
                if status_code is not None and 400 <= status_code < 500 and status_code != 429:
                    break
            except requests.RequestException as exc:
                last_exc = exc
                if attempt == 2:
                    break
            if attempt < 2:
                sleep(attempt + 1)

        if last_exc is not None:
            raise last_exc
        raise RuntimeError(f'Falha ao buscar fonte {self.config.sigla}.')

    def fetch(self) -> str:
        response = self.request('GET', self.config.pagina_editais)
        return response.text

    def soup(self, raw_content: str) -> BeautifulSoup:
        return BeautifulSoup(raw_content, "html.parser")

    @abstractmethod
    def parse(self, raw_content: str) -> list[dict[str, Any]]:
        raise NotImplementedError

    def collect(self) -> list[dict[str, Any]]:
        try:
            raw_content = self.fetch()
        except requests.RequestException:
            return []
        return self.parse(raw_content)
