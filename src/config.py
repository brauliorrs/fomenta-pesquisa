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


def env_or_default(name: str, default: str = "") -> str:
    value = os.getenv(name)
    if value is None:
        return default
    value = value.strip()
    return value if value else default


def env_flag(name: str, default: bool = False) -> bool:
    fallback = "true" if default else "false"
    return env_or_default(name, fallback).lower() == "true"


@dataclass(frozen=True)
class Settings:
    timezone: str = env_or_default("TIMEZONE", "America/Sao_Paulo")
    instagram_publish_mode: str = env_or_default("INSTAGRAM_PUBLISH_MODE", "mock")
    instagram_defer_publish: bool = env_flag("INSTAGRAM_DEFER_PUBLISH", default=False)
    instagram_access_token: str = env_or_default("INSTAGRAM_ACCESS_TOKEN", "")
    instagram_business_account_id: str = env_or_default("INSTAGRAM_BUSINESS_ACCOUNT_ID", "")
    instagram_api_host: str = env_or_default("INSTAGRAM_API_HOST", "https://graph.instagram.com")
    instagram_api_version: str = env_or_default("INSTAGRAM_API_VERSION", "v24.0")
    public_asset_base_url: str = env_or_default("PUBLIC_ASSET_BASE_URL", "")
    instagram_publish_target: str = env_or_default("INSTAGRAM_PUBLISH_TARGET", "both").lower()
    instagram_repost_target: str = env_or_default("INSTAGRAM_REPOST_TARGET", "story").lower()
    instagram_publish_stories: bool = env_flag("INSTAGRAM_PUBLISH_STORIES", default=False)
    instagram_bootstrap_publish_all: bool = env_flag("INSTAGRAM_BOOTSTRAP_PUBLISH_ALL", default=False)
    meta_app_id: str = env_or_default("META_APP_ID", "")
    meta_app_secret: str = env_or_default("META_APP_SECRET", "")
    github_repository: str = env_or_default("GITHUB_REPOSITORY", "")
    github_token: str = env_or_default("GITHUB_TOKEN", "")
    fontes_path: Path = DATA_DIR / "fontes.json"
    editais_path: Path = DATA_DIR / "editais.json"
    historico_postagens_path: Path = DATA_DIR / "historico_postagens.csv"
    publication_queue_path: Path = DATA_DIR / "fila_publicacao.json"
    log_file_path: Path = LOGS_DIR / "bot.log"
    posts_dir: Path = POSTS_DIR


settings = Settings()
