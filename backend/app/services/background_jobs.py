from __future__ import annotations

from datetime import datetime
import json
import threading
import time
from typing import Any

from sqlalchemy import select

from ..config import settings
from ..database import SessionLocal as DefaultSessionLocal
from ..database import get_session_factory
from ..models import MealLog, SearchJob, User
from .daily_nudge import process_proactive_pushes_once
from .line import build_action_flex_message, build_liff_tab_url, push_line_message
from .observability import finish_task_run, record_error_event, route_layers_for_task, start_task_run
from .google_places import search_nearby_places, search_text_places
from .proactive import create_notification, upsert_place_cache
from .proactive import build_external_food_job_result
from .video_intake import build_video_refinement_result


MAX_JOB_RETRIES = 3
SessionLocal = DefaultSessionLocal
_worker_thread: threading.Thread | None = None
_stop_event = threading.Event()

JOB_TASK_FAMILY = {
    "nearby_places": "nearby_recommendation",
    "menu_precision": "suggested_update_review",
    "brand_lookup": "suggested_update_review",
    "external_food_check": "nutrition_or_food_qa",
    "video_extract": "meal_log_now",
    "video_transcript": "meal_log_now",
    "video_precision": "meal_log_now",
    "video_brand_lookup": "meal_log_now",
}


def start_background_worker() -> None:
    global _worker_thread
    if _worker_thread and _worker_thread.is_alive():
        return
    _stop_event.clear()
    _worker_thread = threading.Thread(target=_worker_loop, name="search-job-worker", daemon=True)
    _worker_thread.start()


def stop_background_worker() -> None:
    _stop_event.set()


def process_search_jobs_once(limit: int | None = None) -> None:
    batch_size = limit or settings.background_job_batch_size
    with _session_factory()() as db:
        pending_jobs = list(
            db.scalars(
                select(SearchJob).where(SearchJob.status == "pending").order_by(SearchJob.created_at).limit(batch_size)
            )
        )
        for job in pending_jobs:
            _process_one_job(db, job)


def _worker_loop() -> None:
    while not _stop_event.is_set():
        try:
            process_search_jobs_once()
            with _session_factory()() as db:
                process_proactive_pushes_once(db)
        except Exception:
            pass
        _stop_event.wait(settings.background_poll_interval_seconds)


def _process_one_job(db, job: SearchJob) -> None:
    trace_id = str((job.request_payload or {}).get("trace_id") or job.id)
    task_family = JOB_TASK_FAMILY.get(job.job_type, "fallback_ambiguous")
    route_layer_1, route_layer_2 = route_layers_for_task(task_family)
    task_run_id = start_task_run(
        db,
        trace_id=trace_id,
        user_id=job.user_id,
        task_family=task_family,
        route_layer_1=route_layer_1,
        route_layer_2=route_layer_2,
        provider_name="background_worker",
        model_name=job.job_type,
    )
    try:
        job.status = "running"
        db.add(job)
        db.commit()
        db.refresh(job)

        if job.job_type == "nearby_places":
            result_payload, suggested_update = _run_nearby_places_job(job.request_payload or {})
        elif job.job_type in {"video_extract", "video_transcript", "video_precision", "video_brand_lookup"}:
            result_payload, suggested_update = _run_video_job(job.request_payload or {})
        elif job.job_type in {"menu_precision", "brand_lookup", "external_food_check"}:
            result_payload, suggested_update = _run_external_food_job(db, job.request_payload or {})
        else:
            result_payload, suggested_update = ({"message": "Unsupported job type"}, {})

        job.result_payload = result_payload
        job.suggested_update = suggested_update
        job.status = "completed"

        if (job.request_payload or {}).get("notify_on_complete") and (result_payload or suggested_update):
            _maybe_create_job_notification(db, job)

        db.add(job)
        db.commit()
        finish_task_run(
            db,
            task_run_id,
            status="success",
            result_summary={
                "job_type": job.job_type,
                "status": job.status,
                "suggested_update": bool(job.suggested_update),
                "result_payload_keys": list((job.result_payload or {}).keys())[:12],
            },
        )
    except Exception as exc:
        job.job_retry_count += 1
        job.last_error = str(exc)
        job.status = "failed" if job.job_retry_count >= MAX_JOB_RETRIES else "pending"
        db.add(job)
        db.commit()
        record_error_event(
            db,
            trace_id=trace_id,
            task_run_id=task_run_id,
            user_id=job.user_id,
            component="background_worker",
            operation=job.job_type,
            severity="error",
            error_code="job_retry_exhausted" if job.status == "failed" else "job_retry_pending",
            exception_type=type(exc).__name__,
            message=str(exc),
            retry_count=job.job_retry_count,
            fallback_used=job.status == "pending",
            user_visible_impact="silent_background_failure" if job.status == "failed" else "degraded",
            request_metadata={"job_id": job.id},
        )
        finish_task_run(
            db,
            task_run_id,
            status="failed" if job.status == "failed" else "fallback",
            error_type=type(exc).__name__,
            fallback_reason="retry_pending" if job.status == "pending" else "retry_exhausted",
            result_summary={"job_id": job.id, "retry_count": job.job_retry_count, "job_status": job.status},
        )


def _run_nearby_places_job(request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    lat = request_payload.get("lat")
    lng = request_payload.get("lng")
    query = request_payload.get("query")
    meal_type = request_payload.get("meal_type")

    if lat is not None and lng is not None:
        places = search_nearby_places(lat=float(lat), lng=float(lng), meal_type=meal_type)
    elif query:
        places = search_text_places(query=query)
    else:
        places = []

    with _session_factory()() as db:
        upsert_place_cache(db, places)

    result = {"places": places[:8], "query": query, "meal_type": meal_type}
    return result, {}


def _run_external_food_job(db, request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    text = request_payload.get("text", "")
    source_hint = request_payload.get("source_hint")
    result_payload, suggested_update = build_external_food_job_result(text, source_hint=source_hint)
    target_log_id = request_payload.get("target_log_id")
    if target_log_id and suggested_update:
        log = db.get(MealLog, target_log_id)
        if log:
            suggested_update["target_log_id"] = log.id
            suggested_update.setdefault("store_name", _extract_store_name(log.description_raw))
            suggested_update.setdefault("external_link", "")
    return result_payload, suggested_update


def _run_video_job(request_payload: dict[str, Any]) -> tuple[dict[str, Any], dict[str, Any]]:
    return build_video_refinement_result(request_payload)


def _maybe_create_job_notification(db, job: SearchJob) -> None:
    user = db.get(User, job.user_id)
    if not user:
        return

    title = "Async update ready"
    body = "A background check found a more detailed result."
    notification_type = "async_update"
    if job.job_type == "nearby_places":
        title = "Nearby search updated"
        body = "I found more precise nearby options."
        notification_type = "nearby_update"
    elif job.job_type in {"video_extract", "video_transcript", "video_precision", "video_brand_lookup"}:
        title = "Video analysis updated"
        body = "I finished a background pass on your meal video."
        notification_type = "video_update"

    create_notification(
        db,
        user,
        notification_type=notification_type,
        title=title,
        body=body,
        payload={"job_id": job.id, "suggested_update": job.suggested_update, "result_payload": job.result_payload},
        related_job_id=job.id,
    )
    line_text = body
    flex_message = None
    if job.job_type == "nearby_places":
        place_count = len((job.result_payload or {}).get("places", []))
        line_text = f"我幫你把附近選項查完了，現在有 {place_count} 個更精準的候選可以看。"
        flex_message = build_action_flex_message(
            title="附近結果已更新",
            subtitle=f"找到 {place_count} 個更精準候選",
            lines=[
                "我已經把附近的選項整理好了。",
                "打開吃什麼頁，就能直接看主推與更多候選。",
            ],
            primary_label="看推薦",
            primary_uri=build_liff_tab_url("eat"),
            secondary_label="看今天",
            secondary_uri=build_liff_tab_url("today"),
        )
    elif job.job_type in {"menu_precision", "brand_lookup", "external_food_check"}:
        line_text = "我找到更精準的熱量資訊了。打開今天頁面就能決定要不要套用。"
        flex_message = build_action_flex_message(
            title="熱量更新好了",
            subtitle="有更精準的背景結果",
            lines=[
                "我重新查了一次資料，現在有更精準的熱量範圍。",
                "打開今日頁面就能決定要不要套用。",
            ],
            primary_label="看今天",
            primary_uri=build_liff_tab_url("today"),
        )
    elif job.job_type in {"video_extract", "video_transcript", "video_precision", "video_brand_lookup"}:
        line_text = "我把影片再跑了一次背景分析，現在有更完整的結果可以看。"
        flex_message = build_action_flex_message(
            title="影片背景分析完成",
            subtitle="已整理出更完整的內容",
            lines=[
                "我又跑了一次背景分析。",
                "現在打開今日頁面，就能直接看更新後的結果。",
            ],
            primary_label="看今天",
            primary_uri=build_liff_tab_url("today"),
        )
    try:
        import asyncio

        asyncio.run(push_line_message(user.line_user_id, line_text, flex_message=flex_message))
    except Exception:
        pass
    job.notification_sent_at = datetime.now()


def _extract_store_name(description: str) -> str:
    return description.split()[0][:80] if description.strip() else ""


def _session_factory():
    return SessionLocal if SessionLocal is not DefaultSessionLocal else get_session_factory()
