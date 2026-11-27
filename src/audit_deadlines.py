"""Auditar documentos oficiais cadastrados sem mudar a lista de publicacao."""
from __future__ import annotations

from src.config import settings
from src.services.deadline_audit_service import DeadlineAuditService
from src.services.stage2_inventory import build_stage2_inventory
from src.services.storage_service import StorageService
from src.utils.dates import now_in_timezone
from src.utils.logger import configure_logger


def main() -> None:
    logger = configure_logger(settings.discover_log_file_path)
    storage = StorageService()
    now_iso = now_in_timezone(settings.timezone).isoformat()
    editais = storage.read_json(settings.editais_path, default=[])
    previous = storage.read_json(settings.deadline_audit_path, default={})
    report = DeadlineAuditService(logger).run(editais, previous, now_iso)
    storage.write_json(settings.deadline_audit_path, report)
    confrontos = storage.read_json(settings.stage2_official_checks_path, default={})
    inventory = build_stage2_inventory(editais, report, confrontos, now_iso)
    storage.write_json(settings.stage2_inventory_path, inventory)
    logger.info('Inventario etapa 2: %s', inventory['sumario'])
    logger.info('Auditoria de prazos: %s', report['sumario'])


if __name__ == '__main__':
    main()
