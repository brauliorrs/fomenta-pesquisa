from __future__ import annotations

import time
from pathlib import Path

import requests

from src.config import settings
from src.services.storage_service import StorageService


def is_public_image(url: str) -> bool:
    response = requests.get(url, stream=True, timeout=30)
    try:
        return response.status_code == 200 and response.headers.get('content-type', '').startswith('image/')
    finally:
        response.close()


def main() -> None:
    storage = StorageService()
    editais = storage.read_json(settings.editais_path, default=[])
    ready_assets = [
        Path(item['instagram_asset']).name
        for item in editais
        if item.get('pronto_para_postagem') and item.get('instagram_asset')
    ]
    if not ready_assets:
        print('Nenhum asset pronto para validar no ambiente publico.')
        return

    sample_asset = ready_assets[0]
    sample_url = settings.public_asset_base_url.rstrip('/') + '/' + sample_asset
    timeout_seconds = 300
    interval_seconds = 15
    start = time.time()

    while True:
        if is_public_image(sample_url):
            print(f'Asset publico disponivel: {sample_url}')
            return
        elapsed = int(time.time() - start)
        if elapsed >= timeout_seconds:
            raise TimeoutError(f'Asset ainda nao esta publico apos {timeout_seconds}s: {sample_url}')
        print(f'Aguardando asset publico ({elapsed}s): {sample_url}')
        time.sleep(interval_seconds)


if __name__ == '__main__':
    main()
