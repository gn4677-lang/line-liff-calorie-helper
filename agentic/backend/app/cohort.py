from __future__ import annotations

import hashlib
from dataclasses import dataclass

from .config import get_settings


@dataclass(frozen=True, slots=True)
class CohortDecision:
    enabled: bool
    cohort: str
    core_version: str
    reason: str


def stable_user_bucket(user_key: str) -> int:
    digest = hashlib.sha256(user_key.encode("utf-8")).hexdigest()
    return int(digest[:8], 16) % 100


def decide_agentic_cohort(*, user_id: int | str | None, line_user_id: str | None = None) -> CohortDecision:
    settings = get_settings()
    if not settings.agentic_enabled:
        return CohortDecision(enabled=False, cohort="control", core_version="legacy", reason="agentic_disabled")

    if user_id is not None and str(user_id) in settings.canary_user_ids:
        return CohortDecision(enabled=True, cohort="canary", core_version="agentic", reason="user_allowlist")

    if line_user_id and line_user_id in settings.canary_line_user_ids:
        return CohortDecision(enabled=True, cohort="canary", core_version="agentic", reason="line_allowlist")

    stable_key = str(user_id or line_user_id or "")
    if stable_key and settings.rollout_pct > 0 and stable_user_bucket(stable_key) < settings.rollout_pct:
        return CohortDecision(enabled=True, cohort="canary", core_version="agentic", reason="percentage_rollout")

    return CohortDecision(enabled=False, cohort="control", core_version="legacy", reason="legacy_default")
