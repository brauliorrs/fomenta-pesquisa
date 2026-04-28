from __future__ import annotations

from pathlib import Path

from src.config import settings
from src.models import Edital, SourceConfig
from src.services.dedup_service import DedupService
from src.services.history_service import prune_history_rows
from src.services.instagram_service import InstagramService
from src.services.normalize_service import NormalizeService
from src.services.publication_queue_service import PublicationQueueService
from src.services.render_service import RenderService
from src.services.repost_service import RepostService
from src.services.scraper_service import ScraperService
from src.services.storage_service import StorageService
from src.utils.dates import now_in_timezone
from src.utils.logger import configure_logger


CONFAP_INCLUDE = ('edital', 'chamada', 'inscri', 'prêmio', 'premio', 'centelha', 'bolsa', 'compet')
CONFAP_EXCLUDE = ('resultado', 'fórum', 'forum', 'publicada na', 'investiga', 'usa novas tecnologias', 'projeto apoiado')
CAPES_STRICT_REVIEW = ('prorroga prazo', 'prorroga o prazo', 'chamamento')
CAPES_EXCLUDE = ('cadastramento de bolsas', 'cadastramento', 'registro de informações', 'registro de informacoes', 'instabilidade no sistema', 'instabilidade constatada no sistema')
GENERIC_TITLE_FLAGS = ('resultado', 'lista final', 'seminário', 'seminario', 'webinar', 'fórum', 'forum', 'governo anuncia')
MIN_SUMMARY_LENGTH = 80


def load_source_configs(storage: StorageService) -> list[SourceConfig]:
    payload = storage.read_json(settings.fontes_path, default=[])
    return [SourceConfig(**item) for item in payload]


DEFINITIVE_BLOCK_REASONS = (
    'Edital encerrado.',
    'Link oficial ausente.',
    'Titulo ausente.',
    'Resumo ausente.',
    'Titulo com perfil de noticia lateral ou institucional.',
    'Item da CONFAP classificado como noticia lateral/resultado.',
    'Item da CONFAP sem marcador forte de edital ou chamada.',
    'Item da CAPES classificado como aviso operacional, nao como edital.',
)

REVIEW_REASONS = (
    'Prazo final nao identificado.',
    'Item da CAPES precisa de revisao manual de prazo antes da postagem.',
)


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


def evaluate_editorial_quality(edital: dict) -> tuple[int, list[str], bool, bool]:
    pendencias: list[str] = []
    score = 100

    if edital.get('status') == 'encerrado':
        pendencias.append('Edital encerrado.')
        score -= 100

    if not edital.get('link'):
        pendencias.append('Link oficial ausente.')
        score -= 40
    if not edital.get('titulo'):
        pendencias.append('Titulo ausente.')
        score -= 40
    if not edital.get('orgao'):
        pendencias.append('Orgao ausente.')
        score -= 15
    if not edital.get('resumo'):
        pendencias.append('Resumo ausente.')
        score -= 30
    elif len((edital.get('resumo') or '').strip()) < MIN_SUMMARY_LENGTH:
        pendencias.append('Resumo curto para postagem automatica.')
        score -= 10

    if not edital.get('data_expiracao'):
        pendencias.append('Prazo final nao identificado.')
        score -= 20
    if not edital.get('publico_alvo'):
        pendencias.append('Publico-alvo nao identificado.')
        score -= 5

    title = (edital.get('titulo') or '').lower()
    source = (edital.get('fonte') or '').upper()

    if any(keyword in title for keyword in GENERIC_TITLE_FLAGS):
        pendencias.append('Titulo com perfil de noticia lateral ou institucional.')
        score -= 30

    if source == 'CONFAP':
        if any(keyword in title for keyword in CONFAP_EXCLUDE):
            pendencias.append('Item da CONFAP classificado como noticia lateral/resultado.')
            score -= 60
        if not any(keyword in title for keyword in CONFAP_INCLUDE):
            pendencias.append('Item da CONFAP sem marcador forte de edital ou chamada.')
            score -= 40

    if source == 'CAPES' and any(keyword in title for keyword in CAPES_STRICT_REVIEW) and not edital.get('data_expiracao'):
        pendencias.append('Item da CAPES precisa de revisao manual de prazo antes da postagem.')
        score -= 35

    if source == 'CAPES':
        summary = (edital.get('resumo') or '').lower()
        combined = f'{title} {summary}'
        if any(keyword in combined for keyword in CAPES_EXCLUDE):
            pendencias.append('Item da CAPES classificado como aviso operacional, nao como edital.')
            score -= 60

    score = max(score, 0)
    bloqueio_definitivo = any(pending in DEFINITIVE_BLOCK_REASONS for pending in pendencias)
    revisao_humana = (not bloqueio_definitivo) and any(pending in REVIEW_REASONS for pending in pendencias)
    return score, pendencias, revisao_humana, bloqueio_definitivo


def classify_posting_readiness(edital: dict) -> tuple[bool, str, int, list[str], bool, bool]:
    score, pendencias, revisao_humana, bloqueio_definitivo = evaluate_editorial_quality(edital)
    ready = not revisao_humana and not bloqueio_definitivo
    reason = '' if ready else pendencias[0]
    return ready, reason, score, pendencias, revisao_humana, bloqueio_definitivo


def mark_expired(editais: list[dict], current_date: str) -> int:
    expired = 0
    for edital in editais:
        expiration = edital.get('data_expiracao')
        if expiration and expiration < current_date:
            edital['status'] = 'encerrado'
            expired += 1
        ready, reason, score, pendencias, revisao_humana, bloqueio_definitivo = classify_posting_readiness(edital)
        edital['pronto_para_postagem'] = ready
        edital['motivo_bloqueio_postagem'] = reason
        edital['score_editorial'] = score
        edital['pendencias_editoriais'] = pendencias
        edital['revisao_humana_obrigatoria'] = revisao_humana
        edital['bloqueio_editorial_definitivo'] = bloqueio_definitivo
    return expired


def rebuild_captions(editais: list[dict], render_service: RenderService) -> None:
    for edital in editais:
        hydrated = Edital(**edital)
        edital['instagram_caption'] = render_service.build_caption(hydrated)
        edital.update(render_service.build_card_fields(hydrated))


def normalize_payload_ids(editais: list[dict], normalize_service: NormalizeService) -> None:
    seen_ids: set[str] = set()
    for edital in editais:
        desired_id = normalize_service.build_edital_id(
            edital.get('orgao', ''),
            edital.get('titulo', ''),
            edital.get('link', ''),
        )
        if desired_id in seen_ids:
            desired_id = f'{desired_id}_{normalize_service.content_hash(edital)}'
        edital['id'] = desired_id
        seen_ids.add(desired_id)


def normalize_payload_text_fields(editais: list[dict], normalize_service: NormalizeService) -> None:
    text_fields = (
        'titulo',
        'orgao',
        'fonte',
        'uf',
        'categoria',
        'resumo',
        'publico_alvo',
        'status',
        'motivo_bloqueio_postagem',
    )
    for edital in editais:
        for field_name in text_fields:
            edital[field_name] = normalize_service.clean_text(edital.get(field_name))


def normalize_publication_state(editais: list[dict]) -> None:
    for edital in editais:
        edital['instagram_feed_publicado'] = bool(
            edital.get('instagram_feed_publicado')
            or str(edital.get('instagram_feed_media_id', '') or '').strip()
        )


def sync_draft_assets(editais: list[dict], instagram_service: InstagramService) -> None:
    for edital in editais:
        if edital.get('status') == 'encerrado' or not edital.get('pronto_para_postagem'):
            continue
        assets = instagram_service.build_draft_assets(Edital(**edital))
        edital['instagram_asset'] = assets.feed_image_path
        edital['instagram_story_asset'] = assets.story_image_path
        edital['instagram_mock_asset'] = assets.mock_path


def prune_expired_editais(editais: list[dict], current_date: str) -> tuple[list[dict], list[dict]]:
    ativos: list[dict] = []
    expirados: list[dict] = []
    for edital in editais:
        expiration = edital.get('data_expiracao')
        if expiration and expiration < current_date:
            expirados.append(edital)
            continue
        ativos.append(edital)
    return ativos, expirados


def cleanup_expired_assets(expired_editais: list[dict], active_editais: list[dict]) -> None:
    posts_dir = settings.posts_dir.resolve()
    protected_paths: set[Path] = set()

    for edital in active_editais:
        for field_name in ('instagram_asset', 'instagram_story_asset', 'instagram_mock_asset'):
            raw_path = str(edital.get(field_name) or '').strip()
            if not raw_path:
                continue
            path = Path(raw_path)
            try:
                protected_paths.add(path.resolve())
            except OSError:
                continue

    for edital in expired_editais:
        for field_name in ('instagram_asset', 'instagram_story_asset', 'instagram_mock_asset'):
            raw_path = str(edital.get(field_name) or '').strip()
            if not raw_path:
                continue
            path = Path(raw_path)
            try:
                resolved = path.resolve()
            except OSError:
                continue
            if resolved in protected_paths:
                continue
            if posts_dir not in resolved.parents:
                continue
            if resolved.exists():
                resolved.unlink()


def main() -> None:
    logger = configure_logger(settings.log_file_path)
    storage = StorageService()
    normalize_service = NormalizeService()
    render_service = RenderService()
    scraper_service = ScraperService(logger, normalize_service, render_service)
    dedup_service = DedupService()
    repost_service = RepostService()
    instagram_service = InstagramService(settings)
    publication_queue_service = PublicationQueueService(storage, settings.publication_queue_path)

    now = now_in_timezone(settings.timezone)
    now_iso = now.isoformat()
    today = now.date().isoformat()

    logger.info('Inicio da execucao')

    source_configs = load_source_configs(storage)
    existing_editais = storage.read_json(settings.editais_path, default=[])
    collected_editais, errors = scraper_service.collect(source_configs, now_iso)
    existing_index = dedup_service.index_existing(existing_editais)
    merged_editais, counters = dedup_service.merge(existing_index, collected_editais)

    merged_payload = [item.to_dict() for item in merged_editais]
    merged_payload = dedup_service.collapse_payload(merged_payload)
    normalize_payload_text_fields(merged_payload, normalize_service)
    normalize_payload_ids(merged_payload, normalize_service)
    normalize_publication_state(merged_payload)
    rebuild_captions(merged_payload, render_service)
    expired_count = mark_expired(merged_payload, today)
    active_payload, expired_payload = prune_expired_editais(merged_payload, today)
    cleanup_expired_assets(expired_payload, active_payload)
    sync_draft_assets(active_payload, instagram_service)
    publication_queue_service.export(active_payload, now_iso)

    history_rows = prune_history_rows(
        storage.read_csv(settings.historico_postagens_path),
        active_payload,
    )
    reposted = 0
    blocked = 0
    if settings.instagram_defer_publish:
        logger.info('Publicacao adiada para etapa posterior ao sync dos assets publicos.')
    else:
        for edital in active_payload:
            if edital.get('status') == 'encerrado':
                continue
            if not edital.get('pronto_para_postagem'):
                blocked += 1
                continue
            if repost_service.should_repost(edital.get('data_expiracao'), edital.get('ultima_postagem'), now):
                result = instagram_service.publish(Edital(**edital))
                if result.success:
                    apply_publication_result(edital, result, now_iso)
                    reposted += 1
                history_rows.append(
                    {
                        'edital_id': edital['id'],
                        'data_publicacao': now_iso,
                        'status': 'success' if result.success else 'failed',
                        'asset_path': result.asset_path,
                        'mensagem': result.message,
                        'feed_media_id': result.payload.get('feed_media_id', ''),
                        'story_media_id': result.payload.get('story_media_id', ''),
                        'publication_kind': 'single',
                    }
                )

    storage.write_json(settings.editais_path, active_payload)
    storage.write_csv(
        settings.historico_postagens_path,
        history_rows,
        ['edital_id', 'data_publicacao', 'status', 'asset_path', 'mensagem', 'feed_media_id', 'story_media_id', 'publication_kind'],
    )

    logger.info('Total coletado: %s', len(collected_editais))
    logger.info(
        'Novos: %s | Prorrogados: %s | Atualizados: %s | Mantidos: %s | Deduplicados por chave: %s',
        counters['novos'], counters['prorrogados'], counters['atualizados'], counters['mantidos'], counters['deduplicados_por_chave']
    )
    logger.info('Repostados/Publicados: %s', reposted)
    logger.info('Bloqueados para postagem: %s', blocked)
    logger.info('Expirados removidos da base: %s', expired_count)
    logger.info('Erros por fonte: %s', len(errors))
    logger.info('Fim da execucao')


if __name__ == '__main__':
    main()
