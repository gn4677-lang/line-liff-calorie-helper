from pathlib import Path
from typing import Optional

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "backend" / "data"
ATTACHMENT_DIR = DATA_DIR / "attachments"
DEFAULT_DB = DATA_DIR / "app.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LINE LIFF Calorie Helper"
    environment: str = "development"
    database_url: Optional[str] = None
    supabase_db_url: Optional[str] = None
    supabase_url: Optional[str] = None
    supabase_publishable_key: Optional[str] = None
    supabase_anon_key: Optional[str] = None
    supabase_service_role_key: Optional[str] = None
    supabase_storage_bucket: str = "meal-attachments"
    supabase_signed_url_ttl_seconds: int = 3600
    api_prefix: str = "/api"

    ai_provider: str = "heuristic"
    ai_builder_base_url: str = "https://space.ai-builders.com/backend/v1"
    ai_builder_token: Optional[str] = None
    builderspace_chat_model: str = "supermind-agent-v1"
    builderspace_vision_model: str = "supermind-agent-v1"
    builderspace_transcription_lang: str = "zh-TW"

    default_daily_calorie_target: int = 1800
    default_user_id: str = "demo-user"
    allowlist_line_user_id: Optional[str] = None

    line_channel_id: Optional[str] = None
    line_login_channel_id: Optional[str] = None
    line_channel_secret: Optional[str] = None
    line_channel_access_token: Optional[str] = None
    liff_channel_id: Optional[str] = None
    frontend_dist_dir: str = str(BASE_DIR / "frontend" / "dist")


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)


def resolved_database_url() -> str:
    if settings.supabase_db_url:
        return settings.supabase_db_url
    if settings.database_url:
        return settings.database_url
    return f"sqlite:///{DEFAULT_DB.as_posix()}"
