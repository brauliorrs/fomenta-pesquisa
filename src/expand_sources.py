"""Entrada diaria da expansao controlada de fontes."""
from __future__ import annotations

from src.config import settings
from src.services.source_expansion_service import SourceExpansionService
from src.services.storage_service import StorageService
from src.utils.dates import now_in_timezone
from src.utils.logger import configure_logger


def main() -> None:
    logger = configure_logger(settings.discover_log_file_path)
    storage = StorageService()
    service = SourceExpansionService(logger)
    now_iso = now_in_timezone(settings.timezone).isoformat()

    active = storage.read_json(settings.fontes_path, default=[])
    candidates = storage.read_json(settings.fontes_candidatas_path, default=[])
    history = storage.read_json(settings.fontes_expansao_path, default={})
    active, candidates, payload = service.scan(active, candidates, history, now_iso)

    storage.write_json(settings.fontes_path, active)
    storage.write_json(settings.fontes_candidatas_path, candidates)
    storage.write_json(settings.fontes_expansao_path, payload)
    summary = payload['sumario']
    logger.info('Expansao diaria: %s', summary)


if __name__ == '__main__':
    main()
