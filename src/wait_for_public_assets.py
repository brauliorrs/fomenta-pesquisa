from __future__ import annotations

import time
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import requests

from src.config import settings
from src.services.storage_service import StorageService


def is_public_image(url: str) -> bool:
    try:
        response = requests.get(url, stream=True, timeout=30)
    except requests.RequestException:
        return False
    try:
        return response.status_code == 200 and response.headers.get('content-type', '').startswith('image/')
    finally:
        response.close()


def main() -> None:
    base_url = settings.public_asset_base_url.rstrip('/')
    if not base_url:
        raise ValueError('PUBLIC_ASSET_BASE_URL nao configurada.')

    storage = StorageService()
    editais = storage.read_json(settings.editais_path, default=[])
    ready_assets = sorted(
        {
            Path(asset_path).name
            for item in editais
            if item.get('pronto_para_postagem')
            for asset_path in (item.get('instagram_asset'), item.get('instagram_story_asset'))
            if asset_path
        }
    )
    if not ready_assets:
        print('Nenhum asset pronto para validar no ambiente publico.')
        return

    pending_urls = [f'{base_url}/{asset_name}' for asset_name in ready_assets]
    timeout_seconds = max(60, settings.public_asset_wait_timeout_seconds)
    interval_seconds = 15
    start = time.time()

    while pending_urls:
        workers = min(8, len(pending_urls))
        with ThreadPoolExecutor(max_workers=workers) as executor:
            availability = executor.map(is_public_image, pending_urls)
            pending_urls = [
                url
                for url, is_available in zip(pending_urls, availability)
                if not is_available
            ]
        if not pending_urls:
            print(f'Assets publicos disponiveis: {len(ready_assets)}')
            return
        elapsed = int(time.time() - start)
        if elapsed >= timeout_seconds:
            raise TimeoutError(
                f'Assets ainda nao estao publicos apos {timeout_seconds}s: {", ".join(pending_urls[:3])}'
            )
        print(f'Aguardando {len(pending_urls)} asset(s) publico(s) ({elapsed}s): {pending_urls[0]}')
        time.sleep(interval_seconds)


if __name__ == '__main__':
    main()
