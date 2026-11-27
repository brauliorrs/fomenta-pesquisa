from __future__ import annotations

from pathlib import Path
from datetime import datetime, timedelta, timezone
from zoneinfo import ZoneInfo
from typing import Any

from src.config import settings
from src.services.opportunity_guard import opportunity_gate, _parse
from src.services.published_editorial_guard import published_repost_block_reason
from src.services.storage_service import StorageService
from src.utils.dates import now_in_timezone, parse_date


def published_feed_ids(history_rows: list[dict[str, Any]]) -> set[str]:
    """Recuperar publicacoes reais do feed, sem confundir com stories."""
    return {
        str(row.get('edital_id') or '').strip()
        for row in history_rows
        if str(row.get('status') or '').lower() == 'success'
        and str(row.get('feed_media_id') or '').strip()
        and str(row.get('edital_id') or '').strip()
    }


def already_published(item: dict[str, Any], published_ids: set[str]) -> bool:
    return bool(
        item.get('instagram_feed_publicado')
        or str(item.get('instagram_feed_media_id') or '').strip()
        or str(item.get('id') or '') in published_ids
    )


class PublicationQueueService:
    """Fila 1: ineditos para feed; fila 2: ja publicados para monitoramento.

    Um registro apto pela triagem automatica NAO implica prazo confirmado
    independentemente no edital oficial.
    """

    def __init__(
        self, storage: StorageService, queue_path: Path,
        monitoring_path: Path | None = None,
    ) -> None:
        self.storage = storage
        self.queue_path = queue_path
        self.monitoring_path = monitoring_path or settings.fila_ja_publicados_path

    def export(
        self, editais: list[dict[str, Any]], generated_at: str,
        history_rows: list[dict[str, Any]] | None = None,
    ) -> None:
        published_ids = published_feed_ids(history_rows or [])
        # A fila de monitoramento preserva o feed historico mesmo apos o vencimento.
        by_id: dict[str, dict[str, Any]] = {}
        for item in editais:
            key = str(item.get('id') or '').strip()
            if not key:
                continue
            previous = by_id.get(key)
            if previous is None or (
                already_published(item, published_ids)
                and not already_published(previous, published_ids)
            ):
                by_id[key] = item
        distinct = list(by_id.values())
        ordering_now = now_in_timezone(settings.timezone)
        publicados = sorted(
            (item for item in distinct if already_published(item, published_ids)),
            key=lambda item: self._sort_key(item, ordering_now),
        )
        unpublished = [
            item for item in distinct if not already_published(item, published_ids)
        ]
        ineditos = sorted(
            (item for item in unpublished
             if item.get('pronto_para_postagem')
             and item.get('status') != 'encerrado'
             and opportunity_gate(item, timezone_name=settings.timezone)[0]),
            key=lambda item: self._sort_key(item, ordering_now),
        )
        assert not ({item['id'] for item in ineditos} & {item['id'] for item in publicados})

        common = {
            'generated_at': generated_at,
            'criterio': 'triagem_automatica_nao_equivale_a_inscricoes_confirmadas',
            'total_elegiveis_automaticamente': len(ineditos),
            'total_registros_catalogo_distintos': len(distinct),
            'total_bloqueados_ou_sem_prazo': len(unpublished) - len(ineditos),
            'total_encerrados_monitorados': sum(
                not opportunity_gate(item, timezone_name=settings.timezone)[0]
                for item in publicados
            ),
        }
        pending_payload = {
            **common,
            'tipo_fila': 'fila_1_ineditos',
            'total_prontos': len(ineditos),
            'total_ineditos': len(ineditos),
            'total_ja_publicados': len(publicados),
            'itens': [
                self._to_queue_item(item, i + 1, False, ordering_now)
                for i, item in enumerate(ineditos)
            ],
        }
        monitoring_payload = {
            **common,
            'tipo_fila': 'fila_2_ja_publicados',
            'total_ja_publicados': len(publicados),
            'total_ineditos': len(ineditos),
            'itens': [
                self._to_queue_item(item, i + 1, True, ordering_now)
                for i, item in enumerate(publicados)
            ],
        }
        self.storage.write_json(self.queue_path, pending_payload)
        self.storage.write_json(self.monitoring_path, monitoring_payload)

    def _to_queue_item(
        self, item: dict[str, Any], position: int, published: bool,
    ) -> dict[str, Any]:
        return {
            'posicao_fila': position,
            'id': item.get('id'),
            'titulo': item.get('titulo'),
            'fonte': item.get('fonte'),
            'orgao': item.get('orgao'),
            'prazo': item.get('data_expiracao'),
            'status': item.get('status'),
            'score_editorial': item.get('score_editorial', 0),
            'ultima_postagem': item.get('ultima_postagem'),
            'quantidade_postagens': item.get('quantidade_postagens', 0),
            'instagram_feed_publicado': published,
            'validacao_inscricoes': (
                'HOLD_editorial_repostagem_suspensa'
                if published and published_repost_block_reason(item)
                else ('monitoramento_historico_nao_autoriza_repostagem'
                      if published else 'triagem_automatica_sem_homologacao_do_prazo_oficial')
            ),
            'repostagem_bloqueada': bool(
                published and published_repost_block_reason(item)
            ),
            'urgencia_dias': self._days_left(item.get('data_expiracao'), reference_now),
            'risco_vencimento': self._risk_label(item.get('data_expiracao'), reference_now),
            'prazo_com_horario': self._deadline(item.get('data_expiracao'))[1],
            'link': item.get('link'),
            'caption': item.get('instagram_caption'),
            'card_header': item.get('card_header'),
            'card_title': item.get('card_title'),
            'card_deadline': item.get('card_deadline'),
            'card_summary': item.get('card_summary'),
            'card_handle': item.get('card_handle'),
            'card_footer_note': item.get('card_footer_note'),
        }

    def _deadline(self, value: str | None) -> tuple[datetime | None, bool]:
        """Prazo com hora usa instante real; sem hora usa limite conservador
        APENAS PARA ORDENAÇÃO (não confirma horário de fechamento).
        """
        zone = ZoneInfo(settings.timezone)
        parsed = _parse(value, zone)
        if parsed is None:
            return None, False
        deadline, precise = parsed
        if not precise:
            deadline = datetime.combine(
                deadline.date() + timedelta(days=1), datetime.min.time(),
                tzinfo=zone,
            )
        return deadline.astimezone(timezone.utc), precise

    def _sort_key(
        self, item: dict[str, Any], reference_now: datetime | None = None,
    ) -> tuple[datetime, int, int, str]:
        deadline, precise = self._deadline(item.get('data_expiracao'))
        score = int(item.get('score_editorial', 0) or 0)
        # A data, incluindo hora/fuso quando conhecidos, precede o score.
        return (deadline or datetime.max.replace(tzinfo=timezone.utc),
                0 if precise else 1, -score, str(item.get('titulo') or ''))

    def _risk_label(
        self, value: str | None, reference_now: datetime | None = None,
    ) -> str:
        now = reference_now or now_in_timezone(settings.timezone)
        parsed = _parse(value, ZoneInfo(settings.timezone))
        if parsed is None:
            return 'prazo_desconhecido'
        deadline, precise = parsed
        if not precise:
            if now.date() >= deadline.date():
                return 'vence_hoje_horario_desconhecido' if now.date() == deadline.date() else 'vencido'
            return 'vence_amanha' if (deadline.date() - now.date()).days == 1 else 'prazo_futuro_sem_horario'
        if now >= deadline:
            return 'vencido'
        if (deadline - now).total_seconds() <= 24 * 3600:
            return 'iminente_24h'
        return 'prazo_futuro_confirmado_com_horario'

    def _days_left(
        self, expiration_date: str | None, reference_now: datetime | None = None,
    ) -> int | None:
        parsed = _parse(expiration_date, ZoneInfo(settings.timezone))
        if not parsed:
            return None
        now = reference_now or now_in_timezone(settings.timezone)
        return (parsed[0].date() - now.date()).days
