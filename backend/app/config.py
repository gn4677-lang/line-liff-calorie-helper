from pathlib import Path
from typing import Optional
from zoneinfo import ZoneInfo

from pydantic_settings import BaseSettings, SettingsConfigDict


BASE_DIR = Path(__file__).resolve().parents[2]
DATA_DIR = BASE_DIR / "backend" / "data"
ATTACHMENT_DIR = DATA_DIR / "attachments"
DEFAULT_DB = DATA_DIR / "app.db"


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = "LINE LIFF Calorie Helper"
    environment: str = "development"
    app_base_url: Optional[str] = None
    cors_allowed_origins: str = ""
    app_runtime_role: str = "web"
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
    builderspace_router_model: str = "deepseek"
    builderspace_main_model: str = "supermind-agent-v1"
    builderspace_frontier_model: str = "gpt-5"
    builderspace_chat_model: str = "supermind-agent-v1"
    builderspace_vision_model: str = "supermind-agent-v1"
    builderspace_transcription_lang: str = "zh-TW"
    builderspace_ocr_max_tokens: int = 220
    builderspace_text_max_tokens: int = 320
    builderspace_vision_max_tokens: int = 480
    builderspace_hybrid_text_shortcut: bool = True
    builderspace_result_cache_ttl_seconds: int = 600
    builderspace_result_cache_max_entries: int = 256
    builderspace_router_input_cost_per_1k_usd: float = 0.0
    builderspace_router_output_cost_per_1k_usd: float = 0.0
    builderspace_chat_input_cost_per_1k_usd: float = 0.0
    builderspace_chat_output_cost_per_1k_usd: float = 0.0
    builderspace_vision_input_cost_per_1k_usd: float = 0.0
    builderspace_vision_output_cost_per_1k_usd: float = 0.0
    builderspace_frontier_input_cost_per_1k_usd: float = 0.0
    builderspace_frontier_output_cost_per_1k_usd: float = 0.0
    builderspace_request_budget_per_hour: int = 0
    builderspace_token_budget_per_hour: int = 0
    builderspace_cost_budget_usd_per_day: float = 0.0

    google_places_api_key: Optional[str] = None
    google_places_base_url: str = "https://maps.googleapis.com/maps/api/place"
    background_poll_interval_seconds: int = 10
    background_job_batch_size: int = 4
    background_job_lease_seconds: int = 180
    background_job_heartbeat_seconds: int = 30
    app_timezone: str = "Asia/Taipei"
    proactive_push_enabled: bool = True
    daily_nudge_enabled: bool = True
    daily_nudge_hour: int = 20
    event_reminder_hour: int = 11
    observability_admin_passcode: Optional[str] = None
    observability_admin_session_ttl_hours: int = 12
    chat_capture_llm_enabled: bool = True
    eat_policy_llm_enabled: bool = True
    weekly_coach_llm_enabled: bool = True
    canary_line_user_ids: str = ""
    canary_user_ids: str = ""

    default_daily_calorie_target: int = 1800
    default_user_id: str = "demo-user"
    allowlist_line_user_id: Optional[str] = None

    line_channel_id: Optional[str] = None
    line_login_channel_id: Optional[str] = None
    line_channel_secret: Optional[str] = None
    line_channel_access_token: Optional[str] = None
    liff_channel_id: Optional[str] = None
    liff_session_secret: Optional[str] = None
    liff_session_ttl_hours: int = 168
    frontend_dist_dir: str = str(BASE_DIR / "frontend" / "dist")


settings = Settings()
DATA_DIR.mkdir(parents=True, exist_ok=True)
ATTACHMENT_DIR.mkdir(parents=True, exist_ok=True)


def _csv_env_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


def cors_origin_list() -> list[str]:
    return _csv_env_list(settings.cors_allowed_origins)


def canary_line_user_id_list() -> list[str]:
    return _csv_env_list(settings.canary_line_user_ids)


def canary_user_id_list() -> list[str]:
    return _csv_env_list(settings.canary_user_ids)


def runtime_role() -> str:
    role = (settings.app_runtime_role or "web").strip().lower()
    return role if role in {"web", "worker"} else "web"


def production_config_errors() -> list[str]:
    errors: list[str] = []
    if settings.environment != "production":
        return errors

    required = {
        "AI_PROVIDER": settings.ai_provider == "builderspace",
        "AI_BUILDER_TOKEN": bool(settings.ai_builder_token),
        "SUPABASE_URL": bool(settings.supabase_url),
        "SUPABASE_SERVICE_ROLE_KEY": bool(settings.supabase_service_role_key),
        "LINE_CHANNEL_SECRET": bool(settings.line_channel_secret),
        "LINE_CHANNEL_ACCESS_TOKEN": bool(settings.line_channel_access_token),
        "LIFF_CHANNEL_ID": bool(settings.liff_channel_id),
        "APP_BASE_URL": bool(settings.app_base_url),
        "CORS_ALLOWED_ORIGINS": bool(cors_origin_list()),
    }
    for key, ok in required.items():
        if not ok:
            errors.append(key)

    if runtime_role() not in {"web", "worker"}:
        errors.append("APP_RUNTIME_ROLE")
    return errors


def resolved_database_url() -> str:
    if settings.supabase_db_url:
        return settings.supabase_db_url
    if settings.database_url:
        return settings.database_url
    return f"sqlite:///{DEFAULT_DB.as_posix()}"


def resolved_timezone() -> ZoneInfo:
    try:
        return ZoneInfo(settings.app_timezone)
    except Exception:
        return ZoneInfo("UTC")
