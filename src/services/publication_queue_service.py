from __future__ import annotations

from datetime import date
from pathlib import Path
from typing import Any

from src.services.storage_service import StorageService
from src.utils.dates import parse_date


class PublicationQueueService:
    def __init__(self, storage: StorageService, queue_path: Path) -> None:
        self.storage = storage
        self.queue_path = queue_path

    def export(self, editais: list[dict[str, Any]], generated_at: str) -> None:
        ready_items = [item for item in editais if item.get('pronto_para_postagem') and item.get('status') != 'encerrado']
        ready_items.sort(key=self._sort_key)

        payload = {
            'generated_at': generated_at,
            'total_prontos': len(ready_items),
            'itens': [self._to_queue_item(item, index + 1) for index, item in enumerate(ready_items)],
        }
        self.storage.write_json(self.queue_path, payload)

    def _to_queue_item(self, item: dict[str, Any], position: int) -> dict[str, Any]:
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
            'instagram_feed_publicado': bool(item.get('instagram_feed_publicado')),
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
        return (parsed.date() - date.today()).days
