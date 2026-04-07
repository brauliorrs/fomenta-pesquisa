from __future__ import annotations

from pathlib import Path
from typing import Any

from src.config import settings
from src.models import Edital
from src.services.instagram_service import InstagramService
from src.services.publication_queue_service import PublicationQueueService
from src.services.storage_service import StorageService
from src.utils.dates import parse_date
from src.utils.dates import now_in_timezone
from src.utils.logger import configure_logger


def apply_publication_result(edital: dict, result, now_iso: str) -> None:
    if not result.success:
        return

    published_targets = result.payload.get('published_targets', [])
    if not published_targets:
        return

    edital['ultima_postagem'] = now_iso
    edital['quantidade_postagens'] = int(edital.get('quantidade_postagens', 0)) + 1
    edital['instagram_asset'] = result.payload.get('feed_image_path', edital.get('instagram_asset', ''))
    edital['instagram_story_asset'] = result.payload.get('story_image_path', edital.get('instagram_story_asset', ''))
    edital['instagram_mock_asset'] = result.payload.get('mock_path', edital.get('instagram_mock_asset', ''))

    if 'feed' in published_targets:
        edital['instagram_feed_publicado'] = True
        edital['instagram_feed_media_id'] = result.payload.get('feed_media_id', edital.get('instagram_feed_media_id', ''))
    if 'story' in published_targets:
        edital['instagram_story_media_id'] = result.payload.get('story_media_id', edital.get('instagram_story_media_id', ''))


def normalized_targets(value: str | None, include_story_default: bool) -> tuple[str, ...]:
    normalized = (value or '').strip().lower()
    if not normalized:
        return ('feed', 'story') if include_story_default else ('feed',)
    if normalized == 'both':
        return ('feed', 'story')

    targets: list[str] = []
    for item in normalized.replace(';', ',').split(','):
        candidate = item.strip()
        if candidate in {'feed', 'story'} and candidate not in targets:
            targets.append(candidate)

    if targets:
        return tuple(targets)

    return ('feed', 'story') if include_story_default else ('feed',)


def queue_positions(storage: StorageService) -> dict[str, int]:
    queue_payload = storage.read_json(settings.publication_queue_path, default={})
    queue_items = queue_payload.get('itens', []) if isinstance(queue_payload, dict) else []
    positions: dict[str, int] = {}
    for fallback_index, item in enumerate(queue_items, start=1):
        edital_id = str(item.get('id', '')).strip()
        if not edital_id:
            continue
        raw_position = item.get('posicao_fila')
        try:
            positions[edital_id] = int(raw_position)
        except (TypeError, ValueError):
            positions[edital_id] = fallback_index
    return positions


def ready_editais(editais: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        edital
        for edital in editais
        if edital.get('status') != 'encerrado' and edital.get('pronto_para_postagem')
    ]


def has_real_feed_publication(edital: dict[str, Any]) -> bool:
    return bool(str(edital.get('instagram_feed_media_id', '') or '').strip())


def candidate_priority(edital: dict[str, Any], story_enabled: bool) -> int:
    if not has_real_feed_publication(edital):
        return 0
    if story_enabled and not edital.get('instagram_story_media_id'):
        return 1
    return 2


def candidate_sort_key(edital: dict[str, Any], positions: dict[str, int], story_enabled: bool) -> tuple[int, int, str, str]:
    return (
        candidate_priority(edital, story_enabled),
        positions.get(edital.get('id', ''), 9999),
        edital.get('data_expiracao') or '9999-12-31',
        edital.get('titulo') or '',
    )


def row_mentions_story_success(row: dict[str, Any]) -> bool:
    if str(row.get('status', '')).lower() != 'success':
        return False
    message = str(row.get('mensagem', '')).lower()
    return 'story' in message


def story_posted_today(row: dict[str, Any], now) -> bool:
    if not row_mentions_story_success(row):
        return False
    published_at = parse_date(row.get('data_publicacao'))
    if published_at is None:
        return False
    return published_at.date() == now.date()


def ids_with_story_today(history_rows: list[dict[str, Any]], now) -> set[str]:
    ids: set[str] = set()
    for row in history_rows:
        edital_id = str(row.get('edital_id', '')).strip()
        if edital_id and story_posted_today(row, now):
            ids.add(edital_id)
    return ids


def select_new_publication_candidates(
    ordered_candidates: list[dict[str, Any]],
    story_enabled: bool,
) -> list[dict[str, Any]]:
    return [
        edital
        for edital in ordered_candidates
        if candidate_priority(edital, story_enabled) in {0, 1}
    ]


def select_story_repost_candidates(
    ordered_candidates: list[dict[str, Any]],
    story_reposts_enabled: bool,
    posted_story_today_ids: set[str],
    attempted_ids: set[str],
) -> list[dict[str, Any]]:
    if not story_reposts_enabled:
        return []

    return [
        edital
        for edital in ordered_candidates
        if has_real_feed_publication(edital)
        and edital.get('id') not in posted_story_today_ids
        and edital.get('id') not in attempted_ids
    ]


def select_bootstrap_candidates(
    ordered_candidates: list[dict[str, Any]],
    story_enabled: bool,
) -> list[dict[str, Any]]:
    return [
        edital
        for edital in ordered_candidates
        if candidate_priority(edital, story_enabled) in {0, 1}
    ]


def attempt_publication(
    edital: dict[str, Any],
    instagram_service: InstagramService,
    now_iso: str,
    history_rows: list[dict[str, Any]],
    logger,
    reason: str,
) -> bool:
    asset_path = edital.get('instagram_asset') or ''
    if not asset_path:
        logger.warning('Item %s sem asset preparado para publicacao.', edital.get('id'))
        return False

    asset_name = Path(asset_path).name
    logger.info('%s %s usando asset publico %s', reason, edital.get('id'), asset_name)
    result = instagram_service.publish_prepared_asset(
        Edital(**edital),
        image_path=asset_path,
        story_image_path=edital.get('instagram_story_asset', ''),
        mock_path=edital.get('instagram_mock_asset', ''),
    )

    if result.success:
        apply_publication_result(edital, result, now_iso)

    history_rows.append(
        {
            'edital_id': edital['id'],
            'data_publicacao': now_iso,
            'status': 'success' if result.success else 'failed',
            'asset_path': result.asset_path,
            'mensagem': result.message,
        }
    )
    return result.success


def main() -> None:
    logger = configure_logger(settings.log_file_path)
    storage = StorageService()
    instagram_service = InstagramService(settings)
    queue_service = PublicationQueueService(storage, settings.publication_queue_path)

    now = now_in_timezone(settings.timezone)
    now_iso = now.isoformat()

    editais = storage.read_json(settings.editais_path, default=[])
    history_rows = storage.read_csv(settings.historico_postagens_path)
    positions = queue_positions(storage)
    publish_targets = normalized_targets(settings.instagram_publish_target, settings.instagram_publish_stories)
    repost_targets = normalized_targets(settings.instagram_repost_target, settings.instagram_publish_stories)
    story_enabled = 'story' in publish_targets
    story_reposts_enabled = 'story' in repost_targets
    posted_story_today_ids = ids_with_story_today(history_rows, now)

    published = 0
    attempted = 0
    attempted_ids: set[str] = set()
    ordered_candidates = sorted(
        ready_editais(editais),
        key=lambda edital: candidate_sort_key(edital, positions, story_enabled),
    )

    if settings.instagram_bootstrap_publish_all:
        for edital in select_bootstrap_candidates(ordered_candidates, story_enabled):
            attempted += 1
            attempted_ids.add(edital.get('id', ''))
            if attempt_publication(
                edital,
                instagram_service,
                now_iso,
                history_rows,
                logger,
                'Tentando publicar item da carga inicial',
            ):
                published += 1
                if edital.get('instagram_story_media_id'):
                    posted_story_today_ids.add(edital.get('id', ''))

        queue_service.export(editais, now_iso)
        storage.write_json(settings.editais_path, editais)
        storage.write_csv(
            settings.historico_postagens_path,
            history_rows,
            ['edital_id', 'data_publicacao', 'status', 'asset_path', 'mensagem'],
        )

        logger.info('Carga inicial habilitada. Tentativas de publicacao apos sync: %s', attempted)
        logger.info('Carga inicial habilitada. Publicacoes concluidas apos sync: %s', published)
        return

    for edital in select_new_publication_candidates(ordered_candidates, story_enabled):
        attempted += 1
        attempted_ids.add(edital.get('id', ''))
        if attempt_publication(
            edital,
            instagram_service,
            now_iso,
            history_rows,
            logger,
            'Tentando publicar item prioritario da fila',
        ):
            published += 1
            if edital.get('instagram_story_media_id'):
                posted_story_today_ids.add(edital.get('id', ''))
            break

    for edital in select_story_repost_candidates(
        ordered_candidates,
        story_reposts_enabled,
        posted_story_today_ids,
        attempted_ids,
    ):
        attempted += 1
        attempted_ids.add(edital.get('id', ''))
        if attempt_publication(
            edital,
            instagram_service,
            now_iso,
            history_rows,
            logger,
            'Tentando repostar story diario para edital valido',
        ):
            published += 1
            break

    queue_service.export(editais, now_iso)
    storage.write_json(settings.editais_path, editais)
    storage.write_csv(
        settings.historico_postagens_path,
        history_rows,
        ['edital_id', 'data_publicacao', 'status', 'asset_path', 'mensagem'],
    )

    logger.info('Tentativas de publicacao apos sync: %s', attempted)
    logger.info('Publicacoes concluidas apos sync: %s', published)


if __name__ == '__main__':
    main()
