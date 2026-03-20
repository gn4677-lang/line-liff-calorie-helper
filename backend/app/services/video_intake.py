from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
import shutil
import subprocess
import tempfile
from typing import Any

from sqlalchemy.orm import Session

from ..models import MealDraft, MealLog, User
from ..providers.factory import get_ai_provider
from ..schemas import IntakeRequest
from .knowledge import build_estimation_knowledge_packet, ground_brand_menu_context
from .proactive import create_search_job
from .storage import attachment_for_persistence, infer_source_type_from_mime, load_attachment_bytes, store_attachment_bytes


VIDEO_JOB_TYPES = {"video_extract", "video_transcript", "video_precision", "video_brand_lookup"}
FRAME_CAPTURE_COUNT = 3
SUGGESTED_UPDATE_MIN_DELTA_KCAL = 80


def is_video_attachment(attachment: dict[str, Any]) -> bool:
    mime_type = str(attachment.get("mime_type") or "")
    attachment_type = str(attachment.get("type") or "")
    return mime_type.startswith("video/") or attachment_type == "video"


def first_video_attachment(attachments: list[dict[str, Any]]) -> dict[str, Any] | None:
    for attachment in attachments:
        if is_video_attachment(attachment):
            return attachment
    return None


def request_has_video(request: IntakeRequest) -> bool:
    return request.source_mode == "video" or first_video_attachment(request.attachments) is not None


def enrich_video_intake_request(request: IntakeRequest, *, source_label: str) -> IntakeRequest:
    if not request_has_video(request):
        return request

    attachment = first_video_attachment(request.attachments)
    metadata = {
        **(request.metadata or {}),
        "video_source_label": source_label,
        "video_analysis_status": "pending_refinement",
        "video_refinement_pending": True,
        "video_duration_seconds": attachment.get("duration_seconds") if attachment else None,
        "video_dimensions": {
            "width": attachment.get("width") if attachment else None,
            "height": attachment.get("height") if attachment else None,
        },
        "keyframe_refs": [],
        "transcript": (request.metadata or {}).get("transcript", ""),
        "ocr_hits": (request.metadata or {}).get("ocr_hits", []),
        "brand_hints": (request.metadata or {}).get("brand_hints", []),
        "scene_sequence": (request.metadata or {}).get("scene_sequence", []),
    }
    return request.model_copy(update={"source_mode": "video", "metadata": metadata})


def video_context_from_request(request: IntakeRequest) -> dict[str, Any]:
    if not request_has_video(request):
        return {}
    metadata = request.metadata or {}
    return {
        "video_analysis_status": metadata.get("video_analysis_status", "pending_refinement"),
        "video_duration_seconds": metadata.get("video_duration_seconds"),
        "video_dimensions": metadata.get("video_dimensions", {}),
        "keyframe_refs": metadata.get("keyframe_refs", []),
        "transcript": metadata.get("transcript", ""),
        "ocr_hits": metadata.get("ocr_hits", []),
        "brand_hints": metadata.get("brand_hints", []),
        "scene_sequence": metadata.get("scene_sequence", []),
        "video_refinement_pending": metadata.get("video_refinement_pending", True),
        "video_source_label": metadata.get("video_source_label", "api_video_upload"),
    }


def video_metadata_from_context(context: dict[str, Any]) -> dict[str, Any]:
    if "video_analysis_status" not in context and "video_source_label" not in context:
        return {}
    return {
        "video_used": True,
        "video_analysis_status": context.get("video_analysis_status", "pending_refinement"),
        "video_duration_seconds": context.get("video_duration_seconds"),
        "video_dimensions": context.get("video_dimensions", {}),
        "keyframe_refs": context.get("keyframe_refs", []),
        "transcript": context.get("transcript", ""),
        "ocr_hits": context.get("ocr_hits", []),
        "brand_hints": context.get("brand_hints", []),
        "scene_sequence": context.get("scene_sequence", []),
        "video_refinement_pending": context.get("video_refinement_pending", False),
        "video_source_label": context.get("video_source_label"),
    }


def probe_video_bytes(content: bytes, mime_type: str | None) -> dict[str, Any]:
    suffix = _suffix_for_mime(mime_type)
    with tempfile.TemporaryDirectory(prefix="video-probe-") as tmpdir:
        input_path = Path(tmpdir) / f"input{suffix}"
        input_path.write_bytes(content)
        payload = _ffprobe_json(input_path)
    video_stream = next((stream for stream in payload.get("streams", []) if stream.get("codec_type") == "video"), {})
    duration_raw = payload.get("format", {}).get("duration") or video_stream.get("duration")
    duration_seconds = _safe_float(duration_raw)
    return {
        "duration_seconds": round(duration_seconds, 2) if duration_seconds is not None else None,
        "width": _safe_int(video_stream.get("width")),
        "height": _safe_int(video_stream.get("height")),
    }


def enrich_attachment_with_video_probe(attachment: dict[str, Any], *, content: bytes, mime_type: str | None) -> dict[str, Any]:
    if not is_video_attachment({"type": attachment.get("type"), "mime_type": mime_type or attachment.get("mime_type")}):
        return attachment
    try:
        probed = probe_video_bytes(content, mime_type or attachment.get("mime_type"))
    except Exception as exc:
        return {
            **attachment,
            "type": "video",
            "mime_type": mime_type or attachment.get("mime_type") or "video/mp4",
            "video_probe_error": str(exc),
        }
    return {
        **attachment,
        "type": "video",
        "mime_type": mime_type or attachment.get("mime_type") or "video/mp4",
        **probed,
    }


def build_video_refinement_payload(
    *,
    user: User,
    trace_id: str | None,
    text: str,
    meal_type: str | None,
    attachments: list[dict[str, Any]],
    metadata: dict[str, Any],
    draft: MealDraft | None = None,
    log: MealLog | None = None,
    notify_on_complete: bool,
) -> dict[str, Any]:
    attachment = first_video_attachment(attachments) or {}
    payload: dict[str, Any] = {
        "line_user_id": user.line_user_id,
        "text": text,
        "meal_type": meal_type,
        "attachments": attachments,
        "notify_on_complete": notify_on_complete,
        "video_source_label": metadata.get("video_source_label", "video"),
        "video_duration_seconds": metadata.get("video_duration_seconds") or attachment.get("duration_seconds"),
        "transcript": metadata.get("transcript", ""),
        "brand_hints": metadata.get("brand_hints", []),
        "scene_sequence": metadata.get("scene_sequence", []),
    }
    if trace_id:
        payload["trace_id"] = trace_id
    if draft is not None:
        payload["target_draft_id"] = draft.id
    if log is not None:
        payload["target_log_id"] = log.id
        payload["current_kcal"] = log.kcal_estimate
    return payload


def maybe_queue_video_refinement_job(
    db: Session,
    user: User,
    *,
    trace_id: str | None = None,
    text: str,
    meal_type: str | None,
    attachments: list[dict[str, Any]],
    metadata: dict[str, Any],
    draft: MealDraft | None = None,
    log: MealLog | None = None,
    notify_on_complete: bool = False,
) -> Any:
    if first_video_attachment(attachments) is None:
        return None
    payload = build_video_refinement_payload(
        user=user,
        trace_id=trace_id,
        text=text,
        meal_type=meal_type,
        attachments=attachments,
        metadata=metadata,
        draft=draft,
        log=log,
        notify_on_complete=notify_on_complete,
    )
    return create_search_job(db, user, job_type="video_precision", request_payload=payload)


def build_video_refinement_result(request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    attachments = request_payload.get("attachments") or []
    attachment = first_video_attachment(attachments)
    if not attachment:
        return {"analysis_status": "failed", "notes": ["No video attachment available"]}, {}

    user_scope = request_payload.get("line_user_id") or "video-user"
    source_id = request_payload.get("target_log_id") or request_payload.get("target_draft_id") or "video"
    transcript = str(request_payload.get("transcript") or "")
    notes: list[str] = []
    try:
        keyframes = extract_video_keyframes(
            attachment,
            user_scope=user_scope,
            source_id=str(source_id),
            frame_count=FRAME_CAPTURE_COUNT,
        )
    except Exception as exc:
        keyframes = []
        notes.append(f"keyframe_extraction_failed: {exc}")
    if not transcript:
        try:
            transcript = extract_video_transcript_sync(attachment)
        except Exception as exc:
            notes.append(f"transcript_extraction_failed: {exc}")
            transcript = ""

    try:
        ocr_hits = extract_video_ocr_hits(keyframes, hint_text=request_payload.get("text", ""))
    except Exception as exc:
        notes.append(f"ocr_failed: {exc}")
        ocr_hits = []

    ocr_text = "\n".join(hit.get("text", "") for hit in ocr_hits if hit.get("text"))
    provider_attachments = keyframes
    combined_text = "\n".join(part for part in [request_payload.get("text", ""), transcript, ocr_text] if part).strip()
    try:
        knowledge_packet = build_estimation_knowledge_packet(
            combined_text,
            source_hint="\n".join(part for part in [transcript, ocr_text] if part),
            ocr_hits=ocr_hits,
            meal_type=request_payload.get("meal_type"),
            source_mode="video",
        )
        estimate = asyncio.run(
            get_ai_provider().estimate_meal(
                text=combined_text,
                meal_type=request_payload.get("meal_type"),
                mode="standard",
                source_mode="video",
                clarification_count=0,
                attachments=provider_attachments,
                knowledge_packet=knowledge_packet,
            )
        )
    except Exception as exc:
        notes.append(f"video_estimate_failed: {exc}")
        estimate = asyncio.run(
            get_ai_provider().estimate_meal(
                text=request_payload.get("text", ""),
                meal_type=request_payload.get("meal_type"),
                mode="standard",
                source_mode="video",
                clarification_count=0,
                attachments=[],
                knowledge_packet=build_estimation_knowledge_packet(
                    request_payload.get("text", ""),
                    source_hint=transcript,
                    meal_type=request_payload.get("meal_type"),
                    source_mode="video",
                ),
            )
        )

    grounding = ground_brand_menu_context(
        request_payload.get("text", ""),
        source_hint="\n".join(
            part
            for part in [
                transcript,
                ocr_text,
                " ".join(str(item) for item in request_payload.get("brand_hints", []) if item),
            ]
            if part
        ),
        ocr_hits=ocr_hits,
    )

    persisted_keyframes = [attachment_for_persistence(item) for item in keyframes]
    result_payload = {
        "analysis_status": "completed",
        "video_source_label": request_payload.get("video_source_label", "video"),
        "video_duration_seconds": request_payload.get("video_duration_seconds") or attachment.get("duration_seconds"),
        "transcript": transcript,
        "brand_hints": grounding.get("brand_hints") or request_payload.get("brand_hints", []),
        "scene_sequence": request_payload.get("scene_sequence", []),
        "keyframe_refs": persisted_keyframes,
        "ocr_hits": ocr_hits,
        "parsed_items": estimate.parsed_items,
        "estimate_kcal": estimate.estimate_kcal,
        "kcal_low": estimate.kcal_low,
        "kcal_high": estimate.kcal_high,
        "missing_slots": estimate.missing_slots,
        "uncertainty_note": estimate.uncertainty_note,
        "ambiguity_flags": estimate.ambiguity_flags,
        "grounding_query": grounding.get("query", ""),
        "grounded_catalog_matches": grounding.get("catalog_matches", []),
        "grounded_menu_card_matches": grounding.get("menu_card_matches", []),
        "grounded_convenience_store_sku_matches": grounding.get("convenience_store_sku_matches", []),
        "grounded_convenience_store_archetype_matches": grounding.get("convenience_store_archetype_matches", []),
        "visual_portion_anchor_hits": grounding.get("visual_portion_anchor_hits", []),
        "grounded_brand_cards": grounding.get("brand_cards", []),
        "grounding_type": grounding.get("grounding_type", "unknown"),
        "packaging_cues": grounding.get("packaging_cues", []),
        "likely_convenience_store": grounding.get("likely_convenience_store", False),
        "grounding_sources": grounding.get("sources", []),
        "notes": notes,
    }

    suggested_update = build_video_suggested_update(
        request_payload=request_payload,
        estimate=result_payload,
        grounding=grounding,
    )
    return result_payload, suggested_update


def build_video_suggested_update(
    *,
    request_payload: dict[str, Any],
    estimate: dict[str, Any],
    grounding: dict[str, Any] | None = None,
) -> dict[str, Any]:
    target_log_id = request_payload.get("target_log_id")
    current_kcal = _safe_int(request_payload.get("current_kcal"))
    suggested_kcal = _safe_int(estimate.get("estimate_kcal"))
    if not target_log_id or current_kcal is None:
        return {}

    visual_candidate: dict[str, Any] | None = None
    if suggested_kcal is not None and abs(suggested_kcal - current_kcal) >= SUGGESTED_UPDATE_MIN_DELTA_KCAL:
        visual_candidate = {
            "target_log_id": target_log_id,
            "suggested_kcal": suggested_kcal,
            "suggested_range": {
                "low": _safe_int(estimate.get("kcal_low")) or suggested_kcal,
                "high": _safe_int(estimate.get("kcal_high")) or suggested_kcal,
            },
            "reason": "Refined from meal video keyframes and optional transcript.",
            "sources": [
                {"title": "video_keyframes", "kind": "internal", "count": len(estimate.get("keyframe_refs", []))},
                {"title": "video_transcript", "kind": "internal", "present": bool(estimate.get("transcript"))},
                {"title": "video_ocr", "kind": "internal", "count": len(estimate.get("ocr_hits", []))},
            ],
            "refinement_mode": "video_visual",
        }

    grounding_candidate = dict((grounding or {}).get("suggested_update") or {})
    if grounding_candidate:
        grounded_kcal = _safe_int(grounding_candidate.get("suggested_kcal"))
        if grounded_kcal is None or abs(grounded_kcal - current_kcal) < SUGGESTED_UPDATE_MIN_DELTA_KCAL:
            grounding_candidate = {}
        else:
            grounding_type = str(grounding_candidate.get("grounding_type") or (grounding or {}).get("grounding_type") or "grounded")
            grounding_candidate.update(
                {
                    "target_log_id": target_log_id,
                    "reason": (
                        f"Grounded against local menu knowledge and video evidence."
                        if (grounding or {}).get("brand_hints")
                        else grounding_candidate.get("reason", "Grounded against local menu knowledge.")
                    ),
                    "sources": _merge_sources(grounding_candidate.get("sources", []), visual_candidate.get("sources", []) if visual_candidate else []),
                    "refinement_mode": f"video_{grounding_type}",
                }
            )
            if (grounding or {}).get("brand_hints"):
                grounding_candidate.setdefault("store_name", (grounding or {}).get("brand_hints", [""])[0])

    selected = grounding_candidate or visual_candidate or {}
    if not selected:
        return {}
    selected["original_kcal"] = current_kcal
    selected["difference_kcal"] = int(selected.get("suggested_kcal", current_kcal)) - current_kcal
    return selected


def extract_video_keyframes(
    attachment: dict[str, Any],
    *,
    user_scope: str,
    source_id: str,
    frame_count: int,
) -> list[dict[str, Any]]:
    content = load_attachment_bytes(attachment)
    mime_type = attachment.get("mime_type") or "video/mp4"
    suffix = _suffix_for_mime(mime_type)
    probed = probe_video_bytes(content, mime_type)
    duration_seconds = float(probed.get("duration_seconds") or 0.0)
    timestamps = _representative_timestamps(duration_seconds, frame_count)

    with tempfile.TemporaryDirectory(prefix="video-frames-") as tmpdir:
        input_path = Path(tmpdir) / f"input{suffix}"
        input_path.write_bytes(content)
        frames: list[dict[str, Any]] = []
        for index, timestamp in enumerate(timestamps, start=1):
            output_path = Path(tmpdir) / f"frame-{index}.jpg"
            _run_ffmpeg_capture(input_path, output_path, timestamp)
            image_bytes = output_path.read_bytes()
            stored = store_attachment_bytes(
                content=image_bytes,
                mime_type="image/jpeg",
                source_type="image",
                source_id=f"{source_id}-frame-{index}",
                user_scope=user_scope,
            )
            stored["timestamp_seconds"] = round(timestamp, 2)
            stored["content_base64"] = base64.b64encode(image_bytes).decode("utf-8")
            frames.append(stored)
    return frames


def extract_video_transcript_sync(attachment: dict[str, Any]) -> str:
    content = load_attachment_bytes(attachment)
    mime_type = attachment.get("mime_type") or "video/mp4"
    suffix = _suffix_for_mime(mime_type)
    with tempfile.TemporaryDirectory(prefix="video-audio-") as tmpdir:
        input_path = Path(tmpdir) / f"input{suffix}"
        output_path = Path(tmpdir) / "audio.wav"
        input_path.write_bytes(content)
        try:
            subprocess.run(
                [
                    "ffmpeg",
                    "-y",
                    "-i",
                    str(input_path),
                    "-vn",
                    "-acodec",
                    "pcm_s16le",
                    "-ar",
                    "16000",
                    "-ac",
                    "1",
                    str(output_path),
                ],
                check=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
            )
        except subprocess.CalledProcessError:
            return ""
        if not output_path.exists() or output_path.stat().st_size == 0:
            return ""
        audio_bytes = output_path.read_bytes()
    return asyncio.run(get_ai_provider().transcribe_audio(content=audio_bytes, mime_type="audio/wav")).strip()


def extract_video_ocr_hits(keyframes: list[dict[str, Any]], *, hint_text: str = "") -> list[dict[str, Any]]:
    local_hits = _extract_ocr_hits_with_tesseract(keyframes)
    if local_hits:
        return local_hits

    extractor = getattr(get_ai_provider(), "extract_visible_text", None)
    if callable(extractor):
        try:
            hits = asyncio.run(extractor(attachments=keyframes, hint=hint_text))
        except Exception:
            hits = []
        if isinstance(hits, list):
            return _normalize_ocr_hits(hits)
    return []


def _ffprobe_json(input_path: Path) -> dict[str, Any]:
    result = subprocess.run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_format",
            "-show_streams",
            "-print_format",
            "json",
            str(input_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return json.loads(result.stdout or "{}")


def _run_ffmpeg_capture(input_path: Path, output_path: Path, timestamp_seconds: float) -> None:
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{timestamp_seconds:.2f}",
            "-i",
            str(input_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )


def _representative_timestamps(duration_seconds: float, frame_count: int) -> list[float]:
    if duration_seconds <= 1.5:
        return [0.0]
    raw = [duration_seconds * 0.2, duration_seconds * 0.5, duration_seconds * 0.8]
    timestamps: list[float] = []
    for value in raw[:frame_count]:
        clipped = max(0.0, min(value, max(duration_seconds - 0.2, 0.0)))
        rounded = round(clipped, 2)
        if rounded not in timestamps:
            timestamps.append(rounded)
    return timestamps or [0.0]


def _suffix_for_mime(mime_type: str | None) -> str:
    source_type = infer_source_type_from_mime(mime_type)
    if source_type == "video":
        return ".mp4"
    if source_type == "audio":
        return ".wav"
    return ".bin"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _extract_ocr_hits_with_tesseract(keyframes: list[dict[str, Any]]) -> list[dict[str, Any]]:
    tesseract = shutil.which("tesseract")
    if not tesseract:
        return []

    hits: list[dict[str, Any]] = []
    for index, attachment in enumerate(keyframes, start=1):
        image_bytes = load_attachment_bytes(attachment)
        with tempfile.TemporaryDirectory(prefix="video-ocr-") as tmpdir:
            input_path = Path(tmpdir) / f"frame-{index}.jpg"
            input_path.write_bytes(image_bytes)
            try:
                result = subprocess.run(
                    [tesseract, str(input_path), "stdout", "--psm", "6"],
                    check=True,
                    stdout=subprocess.PIPE,
                    stderr=subprocess.PIPE,
                    text=True,
                )
            except subprocess.CalledProcessError:
                continue
        for line in result.stdout.splitlines():
            cleaned = " ".join(line.split()).strip()
            if len(cleaned) < 2:
                continue
            hits.append(
                {
                    "text": cleaned[:120],
                    "kind": "ocr",
                    "confidence": 0.55,
                    "source": f"frame_{index}",
                }
            )
    return _normalize_ocr_hits(hits)


def _normalize_ocr_hits(hits: list[dict[str, Any]]) -> list[dict[str, Any]]:
    normalized: list[dict[str, Any]] = []
    seen: set[str] = set()
    for item in hits:
        text = " ".join(str(item.get("text", "")).split()).strip()
        if len(text) < 2:
            continue
        key = text.lower()
        if key in seen:
            continue
        seen.add(key)
        normalized.append(
            {
                "text": text[:120],
                "kind": str(item.get("kind") or "ocr")[:40],
                "confidence": round(float(item.get("confidence", 0.5)), 2),
                "source": str(item.get("source") or "ocr"),
            }
        )
    return normalized[:10]


def _merge_sources(primary: list[dict[str, Any]], secondary: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[tuple[str, str]] = set()
    for source in [*primary, *secondary]:
        title = str(source.get("title", ""))
        locator = str(source.get("path") or source.get("url") or source.get("kind") or "")
        key = (title, locator)
        if key in seen:
            continue
        seen.add(key)
        merged.append(source)
    return merged
