from __future__ import annotations

from datetime import datetime, timezone
from functools import lru_cache
import httpx
import mimetypes
from pathlib import Path
import uuid

from supabase import Client, create_client
from supabase.lib.client_options import SyncClientOptions

from ..config import ATTACHMENT_DIR, settings


VOLATILE_ATTACHMENT_FIELDS = {"content_base64", "signed_url"}
_bucket_initialized = False
_SUPABASE_POSTGREST_TIMEOUT = httpx.Timeout(120.0, connect=10.0)
_SUPABASE_STORAGE_TIMEOUT = 20
_SUPABASE_FUNCTION_TIMEOUT = 5


@lru_cache(maxsize=1)
def _get_supabase_httpx_client() -> httpx.Client:
    return httpx.Client(timeout=_SUPABASE_POSTGREST_TIMEOUT, follow_redirects=True)


@lru_cache(maxsize=1)
def _get_supabase_client_options() -> SyncClientOptions:
    return SyncClientOptions(
        postgrest_client_timeout=_SUPABASE_POSTGREST_TIMEOUT,
        storage_client_timeout=_SUPABASE_STORAGE_TIMEOUT,
        function_client_timeout=_SUPABASE_FUNCTION_TIMEOUT,
        httpx_client=_get_supabase_httpx_client(),
    )


@lru_cache(maxsize=1)
def get_supabase_client() -> Client:
    if not settings.supabase_url or not settings.supabase_service_role_key:
        raise RuntimeError("Supabase Storage is not configured")
    return create_client(
        settings.supabase_url,
        settings.supabase_service_role_key,
        options=_get_supabase_client_options(),
    )


def ensure_storage_bucket() -> None:
    global _bucket_initialized
    if _bucket_initialized:
        return

    client = get_supabase_client()
    bucket = settings.supabase_storage_bucket
    try:
        client.storage.get_bucket(bucket)
    except Exception:
        try:
            client.storage.create_bucket(bucket, options={"public": False})
        except Exception as exc:
            if "Duplicate" not in str(exc) and "already exists" not in str(exc):
                raise
    _bucket_initialized = True


def store_attachment_bytes(
    *,
    content: bytes,
    mime_type: str | None,
    source_type: str,
    source_id: str,
    user_scope: str,
) -> dict:
    if settings.supabase_url and settings.supabase_service_role_key:
        return _store_attachment_in_supabase(
            content=content,
            mime_type=mime_type,
            source_type=source_type,
            source_id=source_id,
            user_scope=user_scope,
        )
    return _store_attachment_locally(
        content=content,
        mime_type=mime_type,
        source_type=source_type,
        source_id=source_id,
    )


def attachment_for_persistence(attachment: dict) -> dict:
    return {key: value for key, value in attachment.items() if key not in VOLATILE_ATTACHMENT_FIELDS}


def infer_source_type_from_mime(mime_type: str | None) -> str:
    normalized = (mime_type or "").lower()
    if normalized.startswith("image/"):
        return "image"
    if normalized.startswith("audio/"):
        return "audio"
    if normalized.startswith("video/"):
        return "video"
    return "file"


def load_attachment_bytes(attachment: dict) -> bytes:
    provider = attachment.get("storage_provider")
    if provider == "local":
        local_path = attachment.get("local_path")
        if not local_path:
            raise FileNotFoundError("Attachment local_path is missing")
        return Path(local_path).read_bytes()
    if provider == "supabase":
        bucket = attachment.get("storage_bucket") or settings.supabase_storage_bucket
        path = attachment.get("storage_path")
        if not bucket or not path:
            raise FileNotFoundError("Attachment storage reference is incomplete")
        client = get_supabase_client()
        return client.storage.from_(bucket).download(path)
    raise FileNotFoundError(f"Unsupported attachment provider: {provider}")


def _store_attachment_in_supabase(
    *,
    content: bytes,
    mime_type: str | None,
    source_type: str,
    source_id: str,
    user_scope: str,
) -> dict:
    ensure_storage_bucket()
    client = get_supabase_client()
    suffix = _guess_suffix(mime_type)
    object_path = _build_object_path(user_scope=user_scope, source_type=source_type, source_id=source_id, suffix=suffix)

    client.storage.from_(settings.supabase_storage_bucket).upload(
        path=object_path,
        file=content,
        file_options={"content-type": mime_type or "application/octet-stream", "upsert": "true"},
    )
    signed = client.storage.from_(settings.supabase_storage_bucket).create_signed_url(
        object_path,
        settings.supabase_signed_url_ttl_seconds,
    )

    return {
        "type": source_type,
        "mime_type": mime_type or "application/octet-stream",
        "size": len(content),
        "storage_provider": "supabase",
        "storage_bucket": settings.supabase_storage_bucket,
        "storage_path": object_path,
        "signed_url": signed.get("signedURL") or signed.get("signedUrl"),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


def _store_attachment_locally(*, content: bytes, mime_type: str | None, source_type: str, source_id: str) -> dict:
    suffix = _guess_suffix(mime_type)
    target = ATTACHMENT_DIR / f"{source_id}.{suffix}"
    target.write_bytes(content)
    return {
        "type": source_type,
        "mime_type": mime_type or "application/octet-stream",
        "size": len(content),
        "storage_provider": "local",
        "local_path": str(target),
        "uploaded_at": datetime.now(timezone.utc).isoformat(),
    }


def _build_object_path(*, user_scope: str, source_type: str, source_id: str, suffix: str) -> str:
    now = datetime.now(timezone.utc)
    safe_scope = user_scope.replace("/", "-")
    unique = uuid.uuid4().hex[:8]
    return (
        f"{safe_scope}/{now:%Y/%m/%d}/{source_type}/"
        f"{source_id}-{unique}.{suffix}"
    )


def _guess_suffix(mime_type: str | None) -> str:
    if mime_type:
        guessed = mimetypes.guess_extension(mime_type.split(";")[0].strip())
        if guessed:
            return guessed.lstrip(".")
    return "bin"
