from __future__ import annotations

from pathlib import Path
import subprocess

from app.models import MealLog, SearchJob
from app.services import background_jobs
from app.services import video_intake
from app.services.knowledge import ground_brand_menu_context


def _create_test_video_bytes(tmp_path: Path) -> bytes:
    target = tmp_path / "meal-video.mp4"
    subprocess.run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "color=c=black:s=320x240:d=1.2",
            "-pix_fmt",
            "yuv420p",
            str(target),
        ],
        check=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
    )
    return target.read_bytes()


def _upload_video_attachment(client, tmp_path: Path) -> dict:
    content = _create_test_video_bytes(tmp_path)
    response = client.post(
        "/api/attachments",
        files={"file": ("meal.mp4", content, "video/mp4")},
    )
    assert response.status_code == 200
    return response.json()["payload"]["attachment"]


def test_attachment_upload_classifies_video_and_probes_metadata(client, tmp_path: Path):
    attachment = _upload_video_attachment(client, tmp_path)

    assert attachment["type"] == "video"
    assert attachment["mime_type"] == "video/mp4"
    assert attachment["duration_seconds"] is not None
    assert attachment["width"] == 320
    assert attachment["height"] == 240


def test_video_intake_route_creates_video_draft_and_job(client, db_session_factory, tmp_path: Path):
    attachment = _upload_video_attachment(client, tmp_path)

    response = client.post(
        "/api/intake/video",
        json={
            "attachment": attachment,
            "text": "chicken bento with rice",
            "mode": "standard",
        },
    )

    assert response.status_code == 200
    body = response.json()
    assert body["draft"]["source_mode"] == "video"
    assert body["draft"]["metadata"]["video_analysis_status"] == "pending_refinement"
    assert body["payload"]["search_job_id"]
    assert body["payload"]["pending_async_update"] is True

    search_job_id = body["payload"]["search_job_id"]
    with db_session_factory() as db:
        job = db.get(SearchJob, search_job_id)
        assert job is not None
        assert job.job_type == "video_precision"
        assert job.status == "pending"


def test_confirmed_video_log_keeps_metadata_and_background_job_refines_video(
    client,
    db_session_factory,
    monkeypatch,
    tmp_path: Path,
):
    attachment = _upload_video_attachment(client, tmp_path)
    response = client.post(
        "/api/intake/video",
        json={
            "attachment": attachment,
            "text": "subway chicken sandwich and tea",
            "mode": "quick",
            "notify_on_refinement": True,
        },
    )
    assert response.status_code == 200
    body = response.json()

    if body.get("log"):
        log_id = body["log"]["id"]
        search_job_id = body["payload"]["search_job_id"]
    else:
        draft_id = body["draft"]["id"]
        confirm = client.post(f"/api/intake/{draft_id}/confirm", json={"force_confirm": True})
        assert confirm.status_code == 200
        log_id = confirm.json()["log"]["id"]
        search_job_id = confirm.json()["payload"]["search_job_id"]

    with db_session_factory() as db:
        log = db.get(MealLog, log_id)
        assert log is not None
        assert log.source_mode == "video"
        assert log.memory_metadata["video_used"] is True
        assert log.memory_metadata["video_source_label"] in {"api_video_upload", "api_intake", "line_video"}

    monkeypatch.setattr(background_jobs, "SessionLocal", db_session_factory)
    background_jobs.process_search_jobs_once(limit=5)

    with db_session_factory() as db:
        job = db.get(SearchJob, search_job_id)
        assert job is not None
        assert job.status == "completed"
        assert job.result_payload["analysis_status"] == "completed"
        assert len(job.result_payload["keyframe_refs"]) >= 1
        assert "transcript" in job.result_payload
        assert "estimate_kcal" in job.result_payload


def test_video_refinement_grounds_brand_and_creates_richer_suggested_update(tmp_path: Path, monkeypatch):
    attachment_bytes = _create_test_video_bytes(tmp_path)
    attachment = {
        "type": "video",
        "mime_type": "video/mp4",
        "storage_provider": "local",
        "local_path": str(tmp_path / "grounding-video.mp4"),
        "size": len(attachment_bytes),
    }
    Path(attachment["local_path"]).write_bytes(attachment_bytes)

    monkeypatch.setattr(
        video_intake,
        "extract_video_ocr_hits",
        lambda keyframes, hint_text="": [
            {"text": "7-ELEVEN", "kind": "brand", "confidence": 0.9, "source": "mock"},
            {"text": "雞胸便當", "kind": "menu_item", "confidence": 0.88, "source": "mock"},
        ],
    )
    monkeypatch.setattr(video_intake, "extract_video_transcript_sync", lambda attachment: "")

    result_payload, suggested_update = video_intake.build_video_refinement_result(
        {
            "line_user_id": "test-user",
            "text": "雞胸便當",
            "meal_type": "lunch",
            "attachments": [attachment],
            "target_log_id": 99,
            "current_kcal": 280,
            "video_source_label": "api_video_upload",
        }
    )

    assert result_payload["ocr_hits"]
    assert result_payload["brand_hints"]
    assert result_payload["grounded_catalog_matches"]
    assert result_payload["grounding_type"] in {"chain_menu_card", "convenience_store_sku", "convenience_store_archetype", "catalog"}
    assert suggested_update
    assert suggested_update["target_log_id"] == 99
    assert suggested_update["refinement_mode"].startswith("video_")
    assert suggested_update["difference_kcal"] != 0


def test_ground_brand_menu_context_detects_menu_and_packaging_layers():
    menu_result = ground_brand_menu_context(
        "subway sliced chicken",
        source_hint="subway menu board 6-inch sandwich",
        ocr_hits=[{"text": "Subway", "kind": "brand", "confidence": 0.9}],
    )
    assert menu_result["menu_card_matches"]
    assert menu_result["grounding_type"] == "chain_menu_card"

    convenience_result = ground_brand_menu_context(
        "familymart chicken breast with medium bubble tea cup",
        source_hint="familymart packaged meal medium cup",
        ocr_hits=[
            {"text": "FamilyMart", "kind": "brand", "confidence": 0.9},
            {"text": "chicken breast", "kind": "menu_item", "confidence": 0.88},
            {"text": "medium bubble tea cup", "kind": "packaging", "confidence": 0.72},
        ],
    )
    assert convenience_result["likely_convenience_store"] is True
    assert convenience_result["packaging_cues"]
    assert convenience_result["visual_portion_anchor_hits"]
    assert convenience_result["convenience_store_archetype_matches"] or convenience_result["convenience_store_sku_matches"]


def test_video_refinement_prefers_convenience_store_grounding_when_packaging_is_clear(tmp_path: Path, monkeypatch):
    attachment_bytes = _create_test_video_bytes(tmp_path)
    attachment = {
        "type": "video",
        "mime_type": "video/mp4",
        "storage_provider": "local",
        "local_path": str(tmp_path / "familymart-video.mp4"),
        "size": len(attachment_bytes),
    }
    Path(attachment["local_path"]).write_bytes(attachment_bytes)

    monkeypatch.setattr(
        video_intake,
        "extract_video_ocr_hits",
        lambda keyframes, hint_text="": [
            {"text": "FamilyMart", "kind": "brand", "confidence": 0.91, "source": "mock"},
            {"text": "chicken breast", "kind": "menu_item", "confidence": 0.88, "source": "mock"},
            {"text": "medium bubble tea cup", "kind": "packaging", "confidence": 0.7, "source": "mock"},
        ],
    )
    monkeypatch.setattr(video_intake, "extract_video_transcript_sync", lambda attachment: "")

    result_payload, suggested_update = video_intake.build_video_refinement_result(
        {
            "line_user_id": "test-user",
            "text": "familymart chicken breast",
            "meal_type": "dinner",
            "attachments": [attachment],
            "target_log_id": 77,
            "current_kcal": 320,
            "video_source_label": "api_video_upload",
        }
    )

    assert result_payload["likely_convenience_store"] is True
    assert result_payload["packaging_cues"]
    assert result_payload["visual_portion_anchor_hits"]
    assert suggested_update
    assert suggested_update["target_log_id"] == 77
    assert suggested_update["refinement_mode"] in {"video_convenience_store_sku", "video_convenience_store_archetype", "video_catalog"}
