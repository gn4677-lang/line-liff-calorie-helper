from __future__ import annotations

import threading
from dataclasses import dataclass
from typing import Any, TypeVar

from pydantic import BaseModel

from backend.app.providers.factory import get_ai_provider
from backend.app.services.llm_support import complete_structured_sync

from .config import get_settings


ModelT = TypeVar("ModelT", bound=BaseModel)


@dataclass(slots=True)
class StructuredCallResult:
    payload: BaseModel | None
    provider_name: str
    model_name: str
    prompt_version: str
    usage: dict[str, Any]
    fallback_reason: str | None = None


class StructuredOutputProvider:
    def __init__(self) -> None:
        self.settings = get_settings()
        self.provider = get_ai_provider()

    def enabled(self) -> bool:
        return bool(self.settings.builder_space_token)

    def complete_structured(
        self,
        model: type[ModelT],
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        prompt_version: str,
        timeout_s: float,
        model_hint: str = "chat",
        max_tokens: int = 320,
        temperature: float = 0.1,
        request_options: dict[str, Any] | None = None,
    ) -> StructuredCallResult:
        if not self.enabled():
            return StructuredCallResult(
                payload=None,
                provider_name="deterministic",
                model_name=self.settings.builder_space_model_by_hint.get(model_hint, self.settings.builder_space_model),
                prompt_version=prompt_version,
                usage={},
                fallback_reason="remote_runtime_unavailable",
            )

        raw: dict[str, Any] | None = self._call_with_timeout(
            system_prompt=system_prompt,
            user_payload=user_payload,
            timeout_s=timeout_s,
            model_hint=model_hint,
            max_tokens=max_tokens,
            temperature=temperature,
            request_options=request_options,
        )
        if raw is None:
            return StructuredCallResult(
                payload=None,
                provider_name="builderspace",
                model_name=self.settings.builder_space_model_by_hint.get(model_hint, self.settings.builder_space_model),
                prompt_version=prompt_version,
                usage={},
                fallback_reason="timeout",
            )
        if not raw:
            return StructuredCallResult(
                payload=None,
                provider_name="builderspace",
                model_name=self.settings.builder_space_model_by_hint.get(model_hint, self.settings.builder_space_model),
                prompt_version=prompt_version,
                usage={},
                fallback_reason="empty_response",
            )
        usage = raw.pop("_provider_usage", None)
        usage = usage if isinstance(usage, dict) else {}
        provider_name = str(usage.get("provider_name") or "builderspace")
        model_name = str(
            usage.get("model_name") or self.settings.builder_space_model_by_hint.get(model_hint, self.settings.builder_space_model)
        )
        try:
            payload = model.model_validate(raw)
        except Exception:
            return StructuredCallResult(
                payload=None,
                provider_name=provider_name,
                model_name=model_name,
                prompt_version=prompt_version,
                usage=usage,
                fallback_reason="invalid_schema",
            )
        return StructuredCallResult(
            payload=payload,
            provider_name=provider_name,
            model_name=model_name,
            prompt_version=prompt_version,
            usage=usage,
        )

    def _call_with_timeout(
        self,
        *,
        system_prompt: str,
        user_payload: dict[str, Any],
        timeout_s: float,
        model_hint: str,
        max_tokens: int,
        temperature: float,
        request_options: dict[str, Any] | None,
    ) -> dict[str, Any] | None:
        result_holder: dict[str, Any] = {}
        error_holder: list[BaseException] = []

        def runner() -> None:
            try:
                result_holder.update(
                    complete_structured_sync(
                        self.provider,
                        system_prompt=system_prompt,
                        user_payload=user_payload,
                        max_tokens=max_tokens,
                        temperature=temperature,
                        model_hint=model_hint,
                        request_options=request_options,
                    )
                )
            except BaseException as exc:  # pragma: no cover
                error_holder.append(exc)

        thread = threading.Thread(target=runner, daemon=True)
        thread.start()
        thread.join(timeout=max(timeout_s, 0.1))
        if thread.is_alive():
            return None
        if error_holder:
            return {}
        return result_holder
