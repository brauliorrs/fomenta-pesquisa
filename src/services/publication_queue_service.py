from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import settings
from src.services.opportunity_guard import opportunity_gate
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
        candidates = [
            item for item in editais
            if item.get('pronto_para_postagem')
            and item.get('status') != 'encerrado'
            and opportunity_gate(item, timezone_name=settings.timezone)[0]
        ]
        ineditos = sorted(
            (item for item in candidates if not already_published(item, published_ids)),
            key=self._sort_key,
        )
        publicados = sorted(
            (item for item in candidates if already_published(item, published_ids)),
            key=self._sort_key,
        )
        original_count = len(candidates)
        assert len(ineditos) + len(publicados) == original_count

        common = {
            'generated_at': generated_at,
            'criterio': 'triagem_automatica_nao_equivale_a_inscricoes_confirmadas',
            'total_elegiveis_automaticamente': original_count,
        }
        pending_payload = {
            **common,
            'tipo_fila': 'fila_1_ineditos',
            'total_prontos': len(ineditos),
            'total_ineditos': len(ineditos),
            'total_ja_publicados': len(publicados),
            'itens': [
                self._to_queue_item(item, i + 1, False)
                for i, item in enumerate(ineditos)
            ],
        }
        monitoring_payload = {
            **common,
            'tipo_fila': 'fila_2_ja_publicados',
            'total_ja_publicados': len(publicados),
            'total_ineditos': len(ineditos),
            'itens': [
                self._to_queue_item(item, i + 1, True)
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
            'validacao_inscricoes': 'triagem_automatica_sem_homologacao_do_prazo_oficial',
            'urgencia_dias': self._days_left(item.get('data_expiracao')),
            'link': item.get('link'),
            'caption': item.get('instagram_caption'),
            'card_header': item.get('card_header'),
            'card_title': item.get('card_title'),
            'card_deadline': item.get('card_deadline'),
            'card_summary': item.get('card_summary'),
            'card_handle': item.get('card_handle'),
            'card_footer_note': item.get('card_footer_note'),
        }

    def _sort_key(self, item: dict[str, Any]) -> tuple[int, int, str]:
        days_left = self._days_left(item.get('data_expiracao'))
        days_rank = days_left if days_left is not None else 9999
        score = int(item.get('score_editorial', 0) or 0)
        return (days_rank, -score, str(item.get('titulo') or ''))

    def _days_left(self, expiration_date: str | None) -> int | None:
        parsed = parse_date(expiration_date)
        if not parsed:
            return None
        return (parsed.date() - now_in_timezone(settings.timezone).date()).days
