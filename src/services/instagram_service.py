from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

from src.config import Settings
from src.models import Edital, PublicationResult


@dataclass(frozen=True)
class DraftAssets:
    image_path: str
    mock_path: str


class InstagramService:
    WIDTH = 1080
    HEIGHT = 1350
    FONT_CANDIDATES = {
        'regular': (
            Path('C:/Windows/Fonts/georgia.ttf'),
            Path('C:/Windows/Fonts/times.ttf'),
            Path('/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf'),
            Path('/Library/Fonts/Georgia.ttf'),
        ),
        'bold': (
            Path('C:/Windows/Fonts/georgiab.ttf'),
            Path('C:/Windows/Fonts/timesbd.ttf'),
            Path('/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf'),
            Path('/Library/Fonts/Georgia Bold.ttf'),
        ),
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.posts_dir = settings.posts_dir
        self.posts_dir.mkdir(parents=True, exist_ok=True)

    def publish(self, edital: Edital) -> PublicationResult:
        assets = self.build_draft_assets(edital, prefix='post')
        return self._publish_assets(edital, assets)

    def publish_prepared_asset(
        self,
        edital: Edital,
        image_path: str | None = None,
        mock_path: str | None = None,
    ) -> PublicationResult:
        resolved_image_path = image_path or edital.instagram_asset
        if not resolved_image_path:
            raise ValueError('Nenhum asset preparado encontrado para publicacao.')
        assets = DraftAssets(
            image_path=resolved_image_path,
            mock_path=mock_path or edital.instagram_mock_asset,
        )
        return self._publish_assets(edital, assets)

    def _publish_assets(self, edital: Edital, assets: DraftAssets) -> PublicationResult:
        if self.settings.instagram_publish_mode.lower() != 'real':
            return PublicationResult(
                success=True,
                payload={
                    'id': edital.id,
                    'caption': edital.instagram_caption,
                    'image_path': assets.image_path,
                    'mock_path': assets.mock_path,
                    'mode': 'mock',
                },
                asset_path=assets.image_path,
                message='Mock de publicacao executado com sucesso.',
            )

        try:
            media_url = self._public_asset_url(Path(assets.image_path).name)
            creation_id = self._create_feed_container(media_url, edital.instagram_caption)
            media_id = self._publish_container(creation_id)
            story_id = None
            if self.settings.instagram_publish_stories:
                story_creation_id = self._create_story_container(media_url)
                story_id = self._publish_container(story_creation_id)

            return PublicationResult(
                success=True,
                payload={
                    'id': edital.id,
                    'caption': edital.instagram_caption,
                    'image_path': assets.image_path,
                    'mock_path': assets.mock_path,
                    'media_url': media_url,
                    'feed_media_id': media_id,
                    'story_media_id': story_id,
                    'mode': 'real',
                },
                asset_path=assets.image_path,
                message='Publicacao real executada com sucesso.',
            )
        except Exception as exc:
            return PublicationResult(
                success=False,
                payload={
                    'id': edital.id,
                    'caption': edital.instagram_caption,
                    'image_path': assets.image_path,
                    'mock_path': assets.mock_path,
                    'mode': 'real',
                },
                asset_path=assets.image_path,
                message=f'Falha na publicacao real: {exc}',
            )

    def build_draft_assets(self, edital: Edital, prefix: str = 'draft') -> DraftAssets:
        image_path = self._write_card_asset(edital, prefix)
        mock_path = self._write_mock_asset(edital, prefix)
        return DraftAssets(image_path=str(image_path), mock_path=str(mock_path))

    def _write_mock_asset(self, edital: Edital, prefix: str) -> Path:
        asset_path = self.posts_dir / f'{prefix}_{edital.id}.txt'
        payload = self._build_mock_asset(edital, prefix)
        asset_path.write_text(payload, encoding='utf-8')
        return asset_path

    def _write_card_asset(self, edital: Edital, prefix: str) -> Path:
        asset_path = self.posts_dir / f'{prefix}_{edital.id}.jpg'
        image = self._build_card_image(edital)
        image.save(asset_path, format='JPEG', quality=92, subsampling=0)
        return asset_path

    def _build_mock_asset(self, edital: Edital, prefix: str) -> str:
        metadata = [
            f'[MOCK INSTAGRAM {prefix.upper()}]',
            f'id: {edital.id}',
            f'fonte: {edital.fonte}',
            f'orgao: {edital.orgao}',
            f'prazo: {edital.data_expiracao or "nao informado"}',
            f'card: {prefix}_{edital.id}.jpg',
            '',
            edital.instagram_caption,
        ]
        return '\n'.join(metadata)

    def _public_asset_url(self, asset_name: str) -> str:
        base_url = (self.settings.public_asset_base_url or '').strip()
        if not base_url:
            raise ValueError('PUBLIC_ASSET_BASE_URL nao configurada. A Meta exige URL publica para publicar a midia.')
        return urljoin(base_url.rstrip('/') + '/', asset_name)

    def public_asset_url(self, asset_name: str) -> str:
        return self._public_asset_url(asset_name)

    def _create_feed_container(self, media_url: str, caption: str) -> str:
        payload = {
            'image_url': media_url,
            'caption': caption,
            'access_token': self.settings.instagram_access_token,
        }
        response = requests.post(self._graph_url('media'), data=payload, timeout=60)
        response.raise_for_status()
        return response.json()['id']

    def _create_story_container(self, media_url: str) -> str:
        payload = {
            'image_url': media_url,
            'media_type': 'STORIES',
            'access_token': self.settings.instagram_access_token,
        }
        response = requests.post(self._graph_url('media'), data=payload, timeout=60)
        response.raise_for_status()
        return response.json()['id']

    def _publish_container(self, creation_id: str) -> str:
        payload = {
            'creation_id': creation_id,
            'access_token': self.settings.instagram_access_token,
        }
        response = requests.post(self._graph_url('media_publish'), data=payload, timeout=60)
        response.raise_for_status()
        return response.json()['id']

    def _graph_url(self, edge: str) -> str:
        host = self.settings.instagram_api_host.rstrip('/')
        version = self.settings.instagram_api_version.strip('/')
        ig_user_id = self.settings.instagram_business_account_id
        if not ig_user_id or not self.settings.instagram_access_token:
            raise ValueError(self._credentials_hint())
        return f'{host}/{version}/{ig_user_id}/{edge}'

    def _credentials_hint(self) -> str:
        host = self.settings.instagram_api_host.lower()
        if 'graph.instagram.com' in host:
            return (
                'Credenciais do Instagram nao configuradas para publicacao real. '
                'Para Instagram Login, use INSTAGRAM_ACCESS_TOKEN com o token do usuario do Instagram '
                'e INSTAGRAM_BUSINESS_ACCOUNT_ID com o IG User ID da conta profissional.'
            )
        return (
            'Credenciais do Instagram nao configuradas para publicacao real. '
            'Para Facebook Login, use INSTAGRAM_ACCESS_TOKEN com o Page Access Token '
            'e INSTAGRAM_BUSINESS_ACCOUNT_ID com o Instagram Business Account ID.'
        )

    def _build_card_image(self, edital: Edital) -> Image.Image:
        palette = self._palette(edital)
        title_lines = self._wrap_text(edital.card_title or edital.titulo, 18, 3)
        summary_lines = self._wrap_text(edital.card_summary or edital.resumo or 'Resumo nao informado.', 42, 5)
        header = edital.card_header or f'EDITAL {edital.fonte}'
        deadline = edital.card_deadline or 'PRAZO A DEFINIR'
        handle = edital.card_handle or '@editais.pesquisa'

        image = self._build_background(palette)
        draw = ImageDraw.Draw(image)

        header_font = self._load_font('regular', 28)
        title_font = self._load_font('bold', 74)
        summary_font = self._load_font('regular', 34)
        deadline_font = self._load_font('bold', 34)
        handle_font = self._load_font('regular', 28)

        draw.text((84, 120), header, font=header_font, fill=(245, 240, 233))

        y = 260
        for line in title_lines:
            draw.text((84, y), line, font=title_font, fill=(248, 244, 237))
            y += 88

        badge_box = (84, 610, 404, 692)
        draw.rounded_rectangle(badge_box, radius=22, fill=(255, 248, 236))
        deadline_bbox = draw.textbbox((0, 0), deadline, font=deadline_font)
        deadline_y = badge_box[1] + ((badge_box[3] - badge_box[1]) - (deadline_bbox[3] - deadline_bbox[1])) // 2 - 2
        draw.text((badge_box[0] + 32, deadline_y), deadline, font=deadline_font, fill=self._hex_to_rgb(palette['deadline_text']))

        y = 760
        for line in summary_lines:
            draw.text((84, y), line, font=summary_font, fill=(244, 240, 233))
            y += 48

        draw.text((84, 1248), handle, font=handle_font, fill=(246, 241, 234))
        return image

    def _build_background(self, palette: dict[str, str]) -> Image.Image:
        image = Image.new('RGB', (self.WIDTH, self.HEIGHT))
        draw = ImageDraw.Draw(image)
        split = int(self.HEIGHT * 0.58)
        start = self._hex_to_rgb(palette['bg_start'])
        mid = self._hex_to_rgb(palette['bg_mid'])
        end = self._hex_to_rgb(palette['bg_end'])

        for y in range(self.HEIGHT):
            if y <= split:
                ratio = y / max(split, 1)
                color = self._blend_color(start, mid, ratio)
            else:
                ratio = (y - split) / max(self.HEIGHT - split - 1, 1)
                color = self._blend_color(mid, end, ratio)
            draw.line((0, y, self.WIDTH, y), fill=color)

        overlay = Image.new('RGBA', (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        overlay = self._apply_blurred_circle(
            overlay,
            color=palette['glow'],
            bbox=(560, -80, 1250, 610),
            alpha=96,
            blur_radius=110,
        )
        overlay = self._apply_blurred_circle(
            overlay,
            color=palette['accent'],
            bbox=(40, 0, 420, 380),
            alpha=78,
            blur_radius=90,
        )
        overlay = self._apply_blurred_circle(
            overlay,
            color='#ffffff',
            bbox=(788, 1030, 1148, 1390),
            alpha=32,
            blur_radius=14,
        )

        return Image.alpha_composite(image.convert('RGBA'), overlay).convert('RGB')

    def _apply_blurred_circle(
        self,
        overlay: Image.Image,
        color: str,
        bbox: tuple[int, int, int, int],
        alpha: int,
        blur_radius: int,
    ) -> Image.Image:
        circle = Image.new('RGBA', (self.WIDTH, self.HEIGHT), (0, 0, 0, 0))
        draw = ImageDraw.Draw(circle)
        draw.ellipse(bbox, fill=self._hex_to_rgb(color) + (alpha,))
        if blur_radius > 0:
            circle = circle.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        return Image.alpha_composite(overlay, circle)

    def _load_font(self, weight: str, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
        for font_path in self.FONT_CANDIDATES.get(weight, ()):
            if font_path.exists():
                try:
                    return ImageFont.truetype(str(font_path), size=size)
                except OSError:
                    continue
        try:
            return ImageFont.truetype('DejaVuSerif.ttf', size=size)
        except OSError:
            return ImageFont.load_default()

    def _hex_to_rgb(self, value: str) -> tuple[int, int, int]:
        return ImageColor.getrgb(value)

    def _blend_color(
        self,
        start: tuple[int, int, int],
        end: tuple[int, int, int],
        ratio: float,
    ) -> tuple[int, int, int]:
        bounded_ratio = max(0.0, min(1.0, ratio))
        return tuple(
            int(round(start[channel] + (end[channel] - start[channel]) * bounded_ratio))
            for channel in range(3)
        )

    def _palette(self, edital: Edital) -> dict[str, str]:
        source = (edital.fonte or '').upper()
        palettes = {
            'CAPES': {'bg_start': '#0d3c82', 'bg_mid': '#2a69b8', 'bg_end': '#d6e7ff', 'glow': '#ffffff', 'accent': '#f5db8d', 'deadline_text': '#17312b'},
            'CNPQ': {'bg_start': '#17552f', 'bg_mid': '#2d8c4d', 'bg_end': '#d9f3e2', 'glow': '#ffffff', 'accent': '#96f0c6', 'deadline_text': '#17312b'},
            'CONFAP': {'bg_start': '#7c3413', 'bg_mid': '#be5d1e', 'bg_end': '#ffedd8', 'glow': '#ffffff', 'accent': '#ffd0a0', 'deadline_text': '#4a2410'},
            'IPEA': {'bg_start': '#5f203d', 'bg_mid': '#9f355d', 'bg_end': '#f7dde6', 'glow': '#ffffff', 'accent': '#f4bdd0', 'deadline_text': '#3c1730'},
        }
        palette = dict(palettes.get(source, {'bg_start': '#11463f', 'bg_mid': '#1e6e63', 'bg_end': '#d8eee9', 'glow': '#ffffff', 'accent': '#d7f1ec', 'deadline_text': '#17312b'}))

        days_left = self._days_left(edital.data_expiracao)
        category = (edital.categoria or '').lower()
        title = (edital.titulo or '').lower()

        if days_left is not None and days_left <= 3:
            palette['accent'] = '#ff9ca8'
            palette['deadline_text'] = '#8f1d2c'
        elif days_left is not None and days_left <= 14:
            palette['accent'] = '#ffd088'

        if 'bolsa' in category or 'bolsa' in title:
            palette['accent'] = '#fff0af'
        if any(token in category or token in title for token in ('inov', 'empreendedor', 'centelha')):
            palette['accent'] = '#a6fff3'

        return palette

    def _days_left(self, expiration_date: str | None) -> int | None:
        if not expiration_date:
            return None
        try:
            target = date.fromisoformat(expiration_date)
        except ValueError:
            return None
        return (target - date.today()).days

    def _wrap_text(self, value: str, max_chars: int, max_lines: int) -> list[str]:
        words = (value or '').split()
        if not words:
            return ['']

        lines: list[str] = []
        current = ''
        for word in words:
            candidate = f'{current} {word}'.strip()
            if len(candidate) <= max_chars or not current:
                current = candidate
                continue
            lines.append(current)
            current = word
            if len(lines) == max_lines - 1:
                break

        if current and len(lines) < max_lines:
            lines.append(current)

        return lines[:max_lines]
