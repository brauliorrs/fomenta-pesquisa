from __future__ import annotations

import html
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from urllib.parse import urljoin

import requests

from src.config import Settings
from src.models import Edital, PublicationResult


@dataclass(frozen=True)
class DraftAssets:
    image_path: str
    mock_path: str


class InstagramService:
    WIDTH = 1080
    HEIGHT = 1350

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.posts_dir = settings.posts_dir
        self.posts_dir.mkdir(parents=True, exist_ok=True)

    def publish(self, edital: Edital) -> PublicationResult:
        assets = self.build_draft_assets(edital, prefix='post')

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
        asset_path = self.posts_dir / f'{prefix}_{edital.id}.svg'
        asset_path.write_text(self._build_card_svg(edital), encoding='utf-8')
        return asset_path

    def _build_mock_asset(self, edital: Edital, prefix: str) -> str:
        metadata = [
            f'[MOCK INSTAGRAM {prefix.upper()}]',
            f'id: {edital.id}',
            f'fonte: {edital.fonte}',
            f'orgao: {edital.orgao}',
            f'prazo: {edital.data_expiracao or "nao informado"}',
            f'card: {prefix}_{edital.id}.svg',
            '',
            edital.instagram_caption,
        ]
        return '\n'.join(metadata)

    def _public_asset_url(self, asset_name: str) -> str:
        base_url = (self.settings.public_asset_base_url or '').strip()
        if not base_url:
            raise ValueError('PUBLIC_ASSET_BASE_URL nao configurada. A Meta exige URL publica para publicar a midia.')
        return urljoin(base_url.rstrip('/') + '/', asset_name)

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
            raise ValueError('Credenciais do Instagram nao configuradas para publicacao real.')
        return f'{host}/{version}/{ig_user_id}/{edge}'

    def _build_card_svg(self, edital: Edital) -> str:
        palette = self._palette(edital)
        title_lines = self._wrap_text(edital.card_title or edital.titulo, 18, 3)
        summary_lines = self._wrap_text(edital.card_summary or edital.resumo or 'Resumo não informado.', 42, 5)
        header = html.escape(edital.card_header or f'EDITAL {edital.fonte}')
        deadline = html.escape(edital.card_deadline or 'PRAZO A DEFINIR')
        handle = html.escape(edital.card_handle or '@editais.pesquisa')
        label = html.escape(edital.card_title or edital.titulo)

        title_svg = self._render_lines(title_lines, x=84, start_y=260, line_height=88, font_size=74, weight=700)
        summary_svg = self._render_lines(summary_lines, x=84, start_y=760, line_height=48, font_size=34, weight=500, fill='rgba(248,244,237,0.96)')

        return f"""<svg xmlns="http://www.w3.org/2000/svg" width="{self.WIDTH}" height="{self.HEIGHT}" viewBox="0 0 {self.WIDTH} {self.HEIGHT}" role="img" aria-label="{label}">
  <defs>
    <linearGradient id="bg" x1="0%" y1="0%" x2="100%" y2="100%">
      <stop offset="0%" stop-color="{palette['bg_start']}"/>
      <stop offset="58%" stop-color="{palette['bg_mid']}"/>
      <stop offset="100%" stop-color="{palette['bg_end']}"/>
    </linearGradient>
    <radialGradient id="glow" cx="84%" cy="14%" r="46%">
      <stop offset="0%" stop-color="{palette['glow']}" stop-opacity="0.38"/>
      <stop offset="100%" stop-color="{palette['glow']}" stop-opacity="0"/>
    </radialGradient>
    <radialGradient id="accent" cx="22%" cy="18%" r="20%">
      <stop offset="0%" stop-color="{palette['accent']}" stop-opacity="0.22"/>
      <stop offset="100%" stop-color="{palette['accent']}" stop-opacity="0"/>
    </radialGradient>
  </defs>
  <rect width="{self.WIDTH}" height="{self.HEIGHT}" rx="0" fill="url(#bg)"/>
  <rect width="{self.WIDTH}" height="{self.HEIGHT}" fill="url(#glow)"/>
  <rect width="{self.WIDTH}" height="{self.HEIGHT}" fill="url(#accent)"/>
  <circle cx="968" cy="1210" r="180" fill="rgba(255,255,255,0.12)"/>
  <text x="84" y="120" font-family="Georgia, 'Times New Roman', serif" font-size="28" letter-spacing="5" fill="rgba(248,244,237,0.86)">{header}</text>
  {title_svg}
  <g transform="translate(84 610)">
    <rect width="320" height="82" rx="22" fill="rgba(255,248,236,0.94)"/>
    <text x="32" y="52" font-family="Georgia, 'Times New Roman', serif" font-size="34" font-weight="700" letter-spacing="1.5" fill="{palette['deadline_text']}">{deadline}</text>
  </g>
  {summary_svg}
  <text x="84" y="1248" font-family="Georgia, 'Times New Roman', serif" font-size="28" letter-spacing="4" fill="rgba(248,244,237,0.88)">{handle}</text>
</svg>
"""

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

    def _render_lines(
        self,
        lines: list[str],
        x: int,
        start_y: int,
        line_height: int,
        font_size: int,
        weight: int,
        fill: str = '#f8f4ed',
    ) -> str:
        rendered: list[str] = []
        y = start_y
        for line in lines:
            rendered.append(
                f'<text x="{x}" y="{y}" font-family="Georgia, \'Times New Roman\', serif" font-size="{font_size}" font-weight="{weight}" fill="{fill}">{html.escape(line)}</text>'
            )
            y += line_height
        return '\n  '.join(rendered)
