from __future__ import annotations

from src.config import settings
from src.services.source_discovery_service import SourceDiscoveryService
from src.services.storage_service import StorageService
from src.utils.dates import now_in_timezone
from src.utils.logger import configure_logger


def main() -> None:
    logger = configure_logger(settings.log_file_path)
    storage = StorageService()
    discovery_service = SourceDiscoveryService(logger)

    now = now_in_timezone(settings.timezone)
    now_iso = now.isoformat()

    active_sources = storage.read_json(settings.fontes_path, default=[])
    planned_sources = storage.read_json(settings.fontes_planejadas_path, default={})
    candidate_sources = storage.read_json(settings.fontes_candidatas_path, default=[])

    updated_active_sources, updated_planned_sources, discovery_payload = discovery_service.run(
        active_sources,
        planned_sources,
        candidate_sources,
        now_iso,
    )

    storage.write_json(settings.fontes_path, updated_active_sources)
    storage.write_json(settings.fontes_planejadas_path, updated_planned_sources)
    storage.write_json(settings.fontes_descobertas_path, discovery_payload)

    summary = discovery_payload.get('sumario', {})
    logger.info('Descoberta mensal concluida.')
    logger.info('Fontes ativas auditadas: %s', summary.get('fontes_ativas_auditadas', 0))
    logger.info('Candidatas avaliadas: %s', summary.get('candidatas_avaliadas', 0))
    logger.info('Fontes ativas atualizadas: %s', summary.get('fontes_ativas_atualizadas', 0))
    logger.info('Candidatas viaveis: %s', summary.get('candidatas_viaveis', 0))
    logger.info('Candidatas auto ativadas: %s', summary.get('candidatas_auto_ativadas', 0))


if __name__ == '__main__':
    main()
