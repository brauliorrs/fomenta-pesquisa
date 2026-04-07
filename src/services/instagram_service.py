from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
from time import monotonic, sleep
from urllib.parse import urljoin

import requests
from PIL import Image, ImageColor, ImageDraw, ImageFilter, ImageFont

from src.config import Settings
from src.models import Edital, PublicationResult


@dataclass(frozen=True)
class DraftAssets:
    feed_image_path: str
    story_image_path: str
    mock_path: str


class InstagramService:
    FEED_WIDTH = 1080
    FEED_HEIGHT = 1350
    STORY_WIDTH = 1080
    STORY_HEIGHT = 1920
    FONT_CANDIDATES = {
        "regular": (
            Path("C:/Windows/Fonts/georgia.ttf"),
            Path("C:/Windows/Fonts/times.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif.ttf"),
            Path("/Library/Fonts/Georgia.ttf"),
        ),
        "bold": (
            Path("C:/Windows/Fonts/georgiab.ttf"),
            Path("C:/Windows/Fonts/timesbd.ttf"),
            Path("/usr/share/fonts/truetype/dejavu/DejaVuSerif-Bold.ttf"),
            Path("/Library/Fonts/Georgia Bold.ttf"),
        ),
    }

    def __init__(self, settings: Settings) -> None:
        self.settings = settings
        self.posts_dir = settings.posts_dir
        self.posts_dir.mkdir(parents=True, exist_ok=True)

    def publish(self, edital: Edital) -> PublicationResult:
        assets = self.build_draft_assets(edital, prefix="post")
        return self._publish_assets(edital, assets)

    def publish_prepared_asset(
        self,
        edital: Edital,
        image_path: str | None = None,
        story_image_path: str | None = None,
        mock_path: str | None = None,
    ) -> PublicationResult:
        resolved_feed_image_path = image_path or edital.instagram_asset
        resolved_story_image_path = story_image_path or edital.instagram_story_asset or resolved_feed_image_path
        if not resolved_feed_image_path:
            raise ValueError("Nenhum asset de feed preparado encontrado para publicacao.")
        if not resolved_story_image_path:
            raise ValueError("Nenhum asset de story preparado encontrado para publicacao.")

        assets = DraftAssets(
            feed_image_path=resolved_feed_image_path,
            story_image_path=resolved_story_image_path,
            mock_path=mock_path or edital.instagram_mock_asset,
        )
        return self._publish_assets(edital, assets)

    def _publish_assets(self, edital: Edital, assets: DraftAssets) -> PublicationResult:
        requested_targets = self._configured_targets(edital)
        primary_asset_path = self._primary_asset_path(assets, requested_targets)
        payload = {
            "id": edital.id,
            "caption": edital.instagram_caption,
            "feed_image_path": assets.feed_image_path,
            "story_image_path": assets.story_image_path,
            "mock_path": assets.mock_path,
            "published_targets": [],
        }

        if self.settings.instagram_publish_mode.lower() != "real":
            payload["mode"] = "mock"
            payload["requested_targets"] = list(requested_targets)
            return PublicationResult(
                success=True,
                payload=payload,
                asset_path=primary_asset_path,
                message=f"Mock de publicacao executado com sucesso para: {', '.join(requested_targets)}.",
            )

        payload["mode"] = "real"
        payload["requested_targets"] = list(requested_targets)
        errors: list[str] = []

        if "feed" in requested_targets:
            try:
                feed_media_url = self._public_asset_url(Path(assets.feed_image_path).name)
                feed_creation_id = self._create_feed_container(feed_media_url, edital.instagram_caption)
                feed_media_id = self._publish_container(feed_creation_id)
                payload["feed_media_url"] = feed_media_url
                payload["feed_media_id"] = feed_media_id
                payload["published_targets"].append("feed")
            except Exception as exc:
                errors.append(f"feed: {exc}")

        if "story" in requested_targets:
            try:
                story_media_url = self._public_asset_url(Path(assets.story_image_path).name)
                story_creation_id = self._create_story_container(story_media_url)
                story_media_id = self._publish_container(story_creation_id)
                payload["story_media_url"] = story_media_url
                payload["story_media_id"] = story_media_id
                payload["published_targets"].append("story")
            except Exception as exc:
                errors.append(f"story: {exc}")

        success = bool(payload["published_targets"])
        if errors:
            payload["errors"] = errors

        if success and not errors:
            message = f"Publicacao real executada com sucesso para: {', '.join(payload['published_targets'])}."
        elif success:
            message = (
                f"Publicacao parcial executada com sucesso para: {', '.join(payload['published_targets'])}. "
                f"Falhas: {' | '.join(errors)}"
            )
        else:
            message = f"Falha na publicacao real: {' | '.join(errors) or 'nenhum destino publicado'}"

        return PublicationResult(
            success=success,
            payload=payload,
            asset_path=self._primary_asset_path(
                assets,
                tuple(payload["published_targets"]) if payload["published_targets"] else requested_targets,
            ),
            message=message,
        )

    def build_draft_assets(self, edital: Edital, prefix: str = "draft") -> DraftAssets:
        feed_image_path = self._write_feed_asset(edital, prefix)
        story_image_path = self._write_story_asset(edital, prefix)
        mock_path = self._write_mock_asset(edital, prefix)
        return DraftAssets(
            feed_image_path=str(feed_image_path),
            story_image_path=str(story_image_path),
            mock_path=str(mock_path),
        )

    def _configured_targets(self, edital: Edital) -> tuple[str, ...]:
        publish_targets = self._normalize_targets(self.settings.instagram_publish_target)
        repost_targets = self._normalize_targets(self.settings.instagram_repost_target)

        if edital.instagram_feed_publicado:
            return repost_targets

        if "feed" in publish_targets and "story" in publish_targets and edital.instagram_story_media_id:
            return ("feed",)

        return publish_targets

    def _normalize_targets(self, value: str | None) -> tuple[str, ...]:
        normalized = (value or "").strip().lower()
        if not normalized:
            return ("feed", "story") if self.settings.instagram_publish_stories else ("feed",)
        if normalized == "both":
            return ("feed", "story")

        targets: list[str] = []
        for item in normalized.replace(";", ",").split(","):
            candidate = item.strip()
            if candidate in {"feed", "story"} and candidate not in targets:
                targets.append(candidate)

        if targets:
            return tuple(targets)

        return ("feed", "story") if self.settings.instagram_publish_stories else ("feed",)

    def _primary_asset_path(self, assets: DraftAssets, targets: tuple[str, ...]) -> str:
        if targets == ("story",):
            return assets.story_image_path
        return assets.feed_image_path

    def _write_mock_asset(self, edital: Edital, prefix: str) -> Path:
        asset_path = self.posts_dir / f"{prefix}_{edital.id}.txt"
        payload = self._build_mock_asset(edital, prefix)
        asset_path.write_text(payload, encoding="utf-8")
        return asset_path

    def _write_feed_asset(self, edital: Edital, prefix: str) -> Path:
        asset_path = self.posts_dir / f"{prefix}_{edital.id}.jpg"
        image = self._build_feed_image(edital)
        image.save(asset_path, format="JPEG", quality=92, subsampling=0)
        return asset_path

    def _write_story_asset(self, edital: Edital, prefix: str) -> Path:
        asset_path = self.posts_dir / f"{prefix}_{edital.id}_story.jpg"
        image = self._build_story_image(edital)
        image.save(asset_path, format="JPEG", quality=92, subsampling=0)
        return asset_path

    def _build_mock_asset(self, edital: Edital, prefix: str) -> str:
        metadata = [
            f"[MOCK INSTAGRAM {prefix.upper()}]",
            f"id: {edital.id}",
            f"fonte: {edital.fonte}",
            f"orgao: {edital.orgao}",
            f"prazo: {edital.data_expiracao or 'nao informado'}",
            f"card_feed: {prefix}_{edital.id}.jpg",
            f"card_story: {prefix}_{edital.id}_story.jpg",
            "",
            edital.instagram_caption,
        ]
        return "\n".join(metadata)

    def _public_asset_url(self, asset_name: str) -> str:
        base_url = (self.settings.public_asset_base_url or "").strip()
        if not base_url:
            raise ValueError("PUBLIC_ASSET_BASE_URL nao configurada. A Meta exige URL publica para publicar a midia.")
        return urljoin(base_url.rstrip("/") + "/", asset_name)

    def public_asset_url(self, asset_name: str) -> str:
        return self._public_asset_url(asset_name)

    def _create_feed_container(self, media_url: str, caption: str) -> str:
        payload = {
            "image_url": media_url,
            "caption": caption,
            "access_token": self.settings.instagram_access_token,
        }
        response = requests.post(self._graph_url("media"), data=payload, timeout=60)
        response.raise_for_status()
        return response.json()["id"]

    def _create_story_container(self, media_url: str) -> str:
        payload = {
            "image_url": media_url,
            "media_type": "STORIES",
            "access_token": self.settings.instagram_access_token,
        }
        response = requests.post(self._graph_url("media"), data=payload, timeout=60)
        response.raise_for_status()
        return response.json()["id"]

    def _publish_container(self, creation_id: str) -> str:
        self._wait_until_container_ready(creation_id)
        payload = {
            "creation_id": creation_id,
            "access_token": self.settings.instagram_access_token,
        }
        response = requests.post(self._graph_url("media_publish"), data=payload, timeout=60)
        response.raise_for_status()
        return response.json()["id"]

    def _wait_until_container_ready(
        self,
        creation_id: str,
        timeout_seconds: int = 180,
        poll_interval_seconds: int = 5,
    ) -> None:
        deadline = monotonic() + timeout_seconds
        while True:
            status = self._get_container_status(creation_id)
            if status == "FINISHED":
                return
            if status in {"ERROR", "EXPIRED"}:
                raise RuntimeError(f"Container do Instagram retornou status terminal: {status}.")
            if monotonic() >= deadline:
                raise TimeoutError(f"Container do Instagram ainda nao ficou pronto. Ultimo status: {status}.")
            sleep(poll_interval_seconds)

    def _get_container_status(self, creation_id: str) -> str:
        host = self.settings.instagram_api_host.rstrip("/")
        version = self.settings.instagram_api_version.strip("/")
        token = self.settings.instagram_access_token
        if not token:
            raise ValueError(self._credentials_hint())
        response = requests.get(
            f"{host}/{version}/{creation_id}",
            params={"fields": "status_code", "access_token": token},
            timeout=60,
        )
        response.raise_for_status()
        return str(response.json().get("status_code", "")).upper() or "UNKNOWN"

    def _graph_url(self, edge: str) -> str:
        host = self.settings.instagram_api_host.rstrip("/")
        version = self.settings.instagram_api_version.strip("/")
        ig_user_id = self.settings.instagram_business_account_id
        if not ig_user_id or not self.settings.instagram_access_token:
            raise ValueError(self._credentials_hint())
        return f"{host}/{version}/{ig_user_id}/{edge}"

    def _credentials_hint(self) -> str:
        host = self.settings.instagram_api_host.lower()
        if "graph.instagram.com" in host:
            return (
                "Credenciais do Instagram nao configuradas para publicacao real. "
                "Para Instagram Login, use INSTAGRAM_ACCESS_TOKEN com o token do usuario do Instagram "
                "e INSTAGRAM_BUSINESS_ACCOUNT_ID com o IG User ID da conta profissional."
            )
        return (
            "Credenciais do Instagram nao configuradas para publicacao real. "
            "Para Facebook Login, use INSTAGRAM_ACCESS_TOKEN com o Page Access Token "
            "e INSTAGRAM_BUSINESS_ACCOUNT_ID com o Instagram Business Account ID."
        )

    def _build_feed_image(self, edital: Edital) -> Image.Image:
        palette = self._palette(edital)
        title_lines = self._wrap_text(edital.card_title or edital.titulo, 18, 3)
        summary_lines = self._wrap_text(edital.card_summary or edital.resumo or "Resumo nao informado.", 42, 5)
        header = edital.card_header or f"EDITAL {edital.fonte}"
        deadline = edital.card_deadline or "PRAZO A DEFINIR"
        handle = edital.card_handle or "@editais.pesquisa"
        footer_note = edital.card_footer_note or "Link e detalhes no post do perfil"

        image = self._build_background(palette, self.FEED_WIDTH, self.FEED_HEIGHT)
        draw = ImageDraw.Draw(image)

        header_font = self._load_font("regular", 28)
        title_font = self._load_font("bold", 74)
        summary_font = self._load_font("regular", 34)
        deadline_font = self._load_font("bold", 34)
        footer_font = self._load_font("regular", 28)
        handle_font = self._load_font("regular", 28)

        draw.text((84, 120), header, font=header_font, fill=(245, 240, 233))

        y = 260
        for line in title_lines:
            draw.text((84, y), line, font=title_font, fill=(248, 244, 237))
            y += 88

        badge_box = (84, 610, 404, 692)
        draw.rounded_rectangle(badge_box, radius=22, fill=(255, 248, 236))
        deadline_bbox = draw.textbbox((0, 0), deadline, font=deadline_font)
        deadline_y = badge_box[1] + ((badge_box[3] - badge_box[1]) - (deadline_bbox[3] - deadline_bbox[1])) // 2 - 2
        draw.text((badge_box[0] + 32, deadline_y), deadline, font=deadline_font, fill=self._hex_to_rgb(palette["deadline_text"]))

        y = 760
        for line in summary_lines:
            draw.text((84, y), line, font=summary_font, fill=(244, 240, 233))
            y += 48

        draw.text((84, 1188), footer_note, font=footer_font, fill=(244, 240, 233))
        draw.text((84, 1248), handle, font=handle_font, fill=(246, 241, 234))
        return image

    def _build_story_image(self, edital: Edital) -> Image.Image:
        palette = self._palette(edital)
        image = self._build_background(palette, self.STORY_WIDTH, self.STORY_HEIGHT)

        card = self._build_feed_image(edital)
        card = self._resize_to_fit(card, max_width=900, max_height=1120)
        shadow_overlay = Image.new("RGBA", (self.STORY_WIDTH, self.STORY_HEIGHT), (0, 0, 0, 0))
        shadow_overlay = self._apply_blurred_circle(
            shadow_overlay,
            self.STORY_WIDTH,
            self.STORY_HEIGHT,
            color="#0e221d",
            bbox=(130, 120, 950, 1270),
            alpha=72,
            blur_radius=50,
        )
        image = Image.alpha_composite(image.convert("RGBA"), shadow_overlay).convert("RGB")
        draw = ImageDraw.Draw(image)

        card_x = (self.STORY_WIDTH - card.width) // 2
        card_y = 120
        image.paste(card, (card_x, card_y))

        callout_box = (72, 1380, 1008, 1760)
        draw.rounded_rectangle(callout_box, radius=42, fill=(255, 248, 236))
        draw.rounded_rectangle(callout_box, radius=42, outline=(217, 198, 169), width=3)

        title_font = self._load_font("bold", 58)
        body_font = self._load_font("regular", 34)
        handle_font = self._load_font("bold", 36)

        draw.text((120, 1438), "Mais detalhes no post", font=title_font, fill=self._hex_to_rgb(palette["deadline_text"]))

        story_lines = [
            "Link oficial e informacoes completas",
            "ficam logo abaixo na legenda do",
            "post do perfil @editais.pesquisa.",
        ]
        text_y = 1532
        for line in story_lines:
            draw.text((120, text_y), line, font=body_font, fill=(60, 52, 45))
            text_y += 44

        draw.text((120, 1672), "Abra o post do perfil para ver o edital.", font=handle_font, fill=(42, 74, 64))
        return image

    def _build_background(self, palette: dict[str, str], width: int, height: int) -> Image.Image:
        image = Image.new("RGB", (width, height))
        draw = ImageDraw.Draw(image)
        split = int(height * 0.58)
        start = self._hex_to_rgb(palette["bg_start"])
        mid = self._hex_to_rgb(palette["bg_mid"])
        end = self._hex_to_rgb(palette["bg_end"])

        for y in range(height):
            if y <= split:
                ratio = y / max(split, 1)
                color = self._blend_color(start, mid, ratio)
            else:
                ratio = (y - split) / max(height - split - 1, 1)
                color = self._blend_color(mid, end, ratio)
            draw.line((0, y, width, y), fill=color)

        overlay = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        overlay = self._apply_blurred_circle(
            overlay,
            width,
            height,
            color=palette["glow"],
            bbox=(int(width * 0.52), int(height * -0.06), int(width * 1.16), int(height * 0.45)),
            alpha=96,
            blur_radius=max(70, int(min(width, height) * 0.08)),
        )
        overlay = self._apply_blurred_circle(
            overlay,
            width,
            height,
            color=palette["accent"],
            bbox=(int(width * 0.04), 0, int(width * 0.39), int(height * 0.28)),
            alpha=78,
            blur_radius=max(60, int(min(width, height) * 0.07)),
        )
        overlay = self._apply_blurred_circle(
            overlay,
            width,
            height,
            color="#ffffff",
            bbox=(int(width * 0.73), int(height * 0.76), int(width * 1.06), int(height * 1.03)),
            alpha=32,
            blur_radius=max(12, int(min(width, height) * 0.015)),
        )

        return Image.alpha_composite(image.convert("RGBA"), overlay).convert("RGB")

    def _apply_blurred_circle(
        self,
        overlay: Image.Image,
        width: int,
        height: int,
        color: str,
        bbox: tuple[int, int, int, int],
        alpha: int,
        blur_radius: int,
    ) -> Image.Image:
        circle = Image.new("RGBA", (width, height), (0, 0, 0, 0))
        draw = ImageDraw.Draw(circle)
        draw.ellipse(bbox, fill=self._hex_to_rgb(color) + (alpha,))
        if blur_radius > 0:
            circle = circle.filter(ImageFilter.GaussianBlur(radius=blur_radius))
        return Image.alpha_composite(overlay, circle)

    def _resize_to_fit(self, image: Image.Image, max_width: int, max_height: int) -> Image.Image:
        ratio = min(max_width / image.width, max_height / image.height)
        resample_attr = getattr(Image, "Resampling", Image)
        new_size = (max(1, int(round(image.width * ratio))), max(1, int(round(image.height * ratio))))
        return image.resize(new_size, resample=resample_attr.LANCZOS)

    def _load_font(self, weight: str, size: int) -> ImageFont.ImageFont | ImageFont.FreeTypeFont:
        for font_path in self.FONT_CANDIDATES.get(weight, ()):
            if font_path.exists():
                try:
                    return ImageFont.truetype(str(font_path), size=size)
                except OSError:
                    continue
        try:
            return ImageFont.truetype("DejaVuSerif.ttf", size=size)
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
        source = (edital.fonte or "").upper()
        palettes = {
            "CAPES": {
                "bg_start": "#0d3c82",
                "bg_mid": "#2a69b8",
                "bg_end": "#d6e7ff",
                "glow": "#ffffff",
                "accent": "#f5db8d",
                "deadline_text": "#17312b",
            },
            "CNPQ": {
                "bg_start": "#17552f",
                "bg_mid": "#2d8c4d",
                "bg_end": "#d9f3e2",
                "glow": "#ffffff",
                "accent": "#96f0c6",
                "deadline_text": "#17312b",
            },
            "CONFAP": {
                "bg_start": "#7c3413",
                "bg_mid": "#be5d1e",
                "bg_end": "#ffedd8",
                "glow": "#ffffff",
                "accent": "#ffd0a0",
                "deadline_text": "#4a2410",
            },
            "IPEA": {
                "bg_start": "#5f203d",
                "bg_mid": "#9f355d",
                "bg_end": "#f7dde6",
                "glow": "#ffffff",
                "accent": "#f4bdd0",
                "deadline_text": "#3c1730",
            },
        }
        palette = dict(
            palettes.get(
                source,
                {
                    "bg_start": "#11463f",
                    "bg_mid": "#1e6e63",
                    "bg_end": "#d8eee9",
                    "glow": "#ffffff",
                    "accent": "#d7f1ec",
                    "deadline_text": "#17312b",
                },
            )
        )

        days_left = self._days_left(edital.data_expiracao)
        category = (edital.categoria or "").lower()
        title = (edital.titulo or "").lower()

        if days_left is not None and days_left <= 3:
            palette["accent"] = "#ff9ca8"
            palette["deadline_text"] = "#8f1d2c"
        elif days_left is not None and days_left <= 14:
            palette["accent"] = "#ffd088"

        if "bolsa" in category or "bolsa" in title:
            palette["accent"] = "#fff0af"
        if any(token in category or token in title for token in ("inov", "empreendedor", "centelha")):
            palette["accent"] = "#a6fff3"

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
        words = (value or "").split()
        if not words:
            return [""]

        lines: list[str] = []
        current = ""
        for word in words:
            candidate = f"{current} {word}".strip()
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
