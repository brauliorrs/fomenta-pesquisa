"""Auditar documentos oficiais cadastrados sem mudar a lista de publicacao."""
from __future__ import annotations

from src.config import settings
from src.services.deadline_audit_service import DeadlineAuditService
from src.services.deadline_candidates import build_deadline_candidates
from src.services.p1_operational_report import build_p1_operational_report
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
    candidates = build_deadline_candidates(
        editais, report, now_in_timezone(settings.timezone).date()
    )
    storage.write_json(
        settings.deadline_audit_path.parent / 'candidatos_recuperacao_prazos.json',
        candidates,
    )
    logger.info('Candidatos de prazo para revisao, em HOLD: %s',
                candidates['sumario']['candidatos_para_validacao'])
    confrontos = storage.read_json(settings.stage2_official_checks_path, default={})
    inventory = build_stage2_inventory(editais, report, confrontos, now_iso)
    storage.write_json(settings.stage2_inventory_path, inventory)
    # Métricas de cobertura por fonte. Este relatório é somente diagnóstico.
    p1_report = build_p1_operational_report(editais, previous, report, inventory)
    storage.write_json(settings.deadline_audit_path.parent / 'relatorio_p1_operacional.json', p1_report)
    logger.info('P1 auditoria operacional: %s elegiveis visitados; %s pendentes; %s recuperacoes de acesso',
                p1_report['visitados_elegiveis'],
                p1_report['pendentes_de_visita_elegiveis'],
                p1_report['falhas_de_acesso_recuperadas_nesta_execucao'])
    logger.info('Inventario etapa 2: %s', inventory['sumario'])
    logger.info('Auditoria de prazos: %s', report['sumario'])


if __name__ == '__main__':
    main()
