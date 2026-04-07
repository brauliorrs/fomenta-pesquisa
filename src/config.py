from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path

from dotenv import load_dotenv


ROOT_DIR = Path(__file__).resolve().parent.parent
DATA_DIR = ROOT_DIR / "data"
LOGS_DIR = ROOT_DIR / "logs"
POSTS_DIR = ROOT_DIR / "posts"
TEMPLATES_DIR = ROOT_DIR / "templates"

load_dotenv(ROOT_DIR / ".env")


@dataclass(frozen=True)
class Settings:
    timezone: str = os.getenv("TIMEZONE", "America/Sao_Paulo")
    instagram_publish_mode: str = os.getenv("INSTAGRAM_PUBLISH_MODE", "mock")
    instagram_access_token: str = os.getenv("INSTAGRAM_ACCESS_TOKEN", "")
    instagram_business_account_id: str = os.getenv("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    instagram_api_host: str = os.getenv("INSTAGRAM_API_HOST", "https://graph.instagram.com")
    instagram_api_version: str = os.getenv("INSTAGRAM_API_VERSION", "v24.0")
    public_asset_base_url: str = os.getenv("PUBLIC_ASSET_BASE_URL", "")
    instagram_publish_stories: bool = os.getenv("INSTAGRAM_PUBLISH_STORIES", "false").lower() == "true"
    meta_app_id: str = os.getenv("META_APP_ID", "")
    meta_app_secret: str = os.getenv("META_APP_SECRET", "")
    github_repository: str = os.getenv("GITHUB_REPOSITORY", "")
    github_token: str = os.getenv("GITHUB_TOKEN", "")
    fontes_path: Path = DATA_DIR / "fontes.json"
    editais_path: Path = DATA_DIR / "editais.json"
    historico_postagens_path: Path = DATA_DIR / "historico_postagens.csv"
    publication_queue_path: Path = DATA_DIR / "fila_publicacao.json"
    log_file_path: Path = LOGS_DIR / "bot.log"
    posts_dir: Path = POSTS_DIR


settings = Settings()
