from __future__ import annotations

from functools import lru_cache
from pathlib import Path
from typing import Literal

from pydantic import field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from backend.app.config import resolved_database_url as legacy_resolved_database_url
from backend.app.config import settings as legacy_settings


ROOT = Path(__file__).resolve().parents[2]


def _csv_list(raw: str | None) -> list[str]:
    if not raw:
        return []
    return [item.strip() for item in raw.split(",") if item.strip()]


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="AGENTIC_", extra="ignore")

    app_name: str = "line-liff-calorie-helper-agentic"
    environment: Literal["development", "test", "production"] = legacy_settings.environment if legacy_settings.environment in {"development", "test", "production"} else "development"
    database_url: str | None = None
    app_runtime_role: Literal["web", "worker"] = "web"
    app_base_url: str | None = legacy_settings.app_base_url
    frontend_dist_dir: str = str(ROOT / "frontend" / "dist")

    agentic_enabled: bool = True
    canary_allowlist: str = legacy_settings.canary_user_ids or ""
    canary_line_allowlist: str = legacy_settings.canary_line_user_ids or ""
    rollout_pct: int = 0

    builder_space_base_url: str = legacy_settings.ai_builder_base_url
    builder_space_model: str = legacy_settings.builderspace_chat_model
    builder_space_router_model: str = legacy_settings.builderspace_router_model
    builder_space_frontier_model: str = legacy_settings.builderspace_frontier_model
    builder_space_token: str | None = legacy_settings.ai_builder_token

    agent_persona: str = "calm coach-partner"
    timezone: str = legacy_settings.app_timezone

    understand_timeout_s: float = 10.0
    plan_timeout_s: float = 10.0
    respond_timeout_s: float = 10.0
    delivery_timeout_s: float = 5.0
    turn_timeout_s: float = 30.0

    line_daily_unsolicited_cap: int = 2
    line_min_gap_hours: int = 4
    same_topic_cooldown_hours: int = 24

    liff_channel_id: str | None = legacy_settings.liff_channel_id
    line_channel_secret: str | None = legacy_settings.line_channel_secret
    line_channel_access_token: str | None = legacy_settings.line_channel_access_token
    liff_session_secret: str | None = legacy_settings.liff_session_secret
    liff_session_ttl_hours: int = legacy_settings.liff_session_ttl_hours

    allow_demo_headers: bool = legacy_settings.environment != "production"

    @field_validator("rollout_pct")
    @classmethod
    def clamp_rollout_pct(cls, value: int) -> int:
        return max(0, min(int(value), 100))

    @property
    def resolved_database_url(self) -> str:
        if self.database_url:
            return self.database_url
        return legacy_resolved_database_url()

    @property
    def frontend_dist_path(self) -> Path:
        return Path(self.frontend_dist_dir)

    @property
    def builder_space_model_by_hint(self) -> dict[str, str]:
        return {
            "chat": self.builder_space_model,
            "router": self.builder_space_router_model,
            "frontier": self.builder_space_frontier_model,
            "vision": self.builder_space_model,
        }

    @property
    def canary_user_ids(self) -> set[str]:
        values = set(_csv_list(self.canary_allowlist))
        if self.allow_demo_headers:
            values.add("agentic-demo-user")
        return values

    @property
    def canary_line_user_ids(self) -> set[str]:
        values = set(_csv_list(self.canary_line_allowlist))
        if self.allow_demo_headers:
            values.add("agentic-demo-user")
        return values


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()
