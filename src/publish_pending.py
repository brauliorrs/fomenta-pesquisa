from __future__ import annotations

from pathlib import Path

from src.config import settings
from src.models import Edital
from src.services.instagram_service import InstagramService
from src.services.repost_service import RepostService
from src.services.storage_service import StorageService
from src.utils.dates import now_in_timezone
from src.utils.logger import configure_logger


def main() -> None:
    logger = configure_logger(settings.log_file_path)
    storage = StorageService()
    repost_service = RepostService()
    instagram_service = InstagramService(settings)

    now = now_in_timezone(settings.timezone)
    now_iso = now.isoformat()

    editais = storage.read_json(settings.editais_path, default=[])
    history_rows = storage.read_csv(settings.historico_postagens_path)

    published = 0
    attempted = 0
    for edital in editais:
        if edital.get('status') == 'encerrado' or not edital.get('pronto_para_postagem'):
            continue
        if not repost_service.should_repost(edital.get('data_expiracao'), edital.get('ultima_postagem'), now):
            continue

        asset_path = edital.get('instagram_asset') or ''
        if not asset_path:
            logger.warning('Item %s sem asset preparado para publicacao.', edital.get('id'))
            continue

        asset_name = Path(asset_path).name
        logger.info('Tentando publicar %s usando asset publico %s', edital.get('id'), asset_name)
        attempted += 1
        result = instagram_service.publish_prepared_asset(
            Edital(**edital),
            image_path=asset_path,
            mock_path=edital.get('instagram_mock_asset', ''),
        )

        if result.success:
            edital['ultima_postagem'] = now_iso
            edital['quantidade_postagens'] = int(edital.get('quantidade_postagens', 0)) + 1
            edital['instagram_asset'] = result.asset_path
            edital['instagram_mock_asset'] = result.payload.get('mock_path', edital.get('instagram_mock_asset', ''))
            published += 1

        history_rows.append(
            {
                'edital_id': edital['id'],
                'data_publicacao': now_iso,
                'status': 'success' if result.success else 'failed',
                'asset_path': result.asset_path,
                'mensagem': result.message,
            }
        )

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
