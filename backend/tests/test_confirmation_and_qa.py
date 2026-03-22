from datetime import date

import pytest

from app.models import User
from app.providers.base import EstimateResult
from app.services.confirmation import decide_confirmation
from app.services.knowledge import build_suggested_update_packet

pytestmark = pytest.mark.agentic


def test_intake_returns_confirmation_metadata_and_answer_options(client):
    response = client.post("/api/intake", json={"text": "simple breakfast", "mode": "standard"})
    assert response.status_code == 200

    draft = response.json()["draft"]
    assert draft["confirmation_mode"] in {"needs_clarification", "needs_confirmation", "auto_recordable"}
    assert "estimation_confidence" in draft
    assert "confirmation_calibration" in draft
    assert isinstance(draft["primary_uncertainties"], list)
    if draft["answer_mode"] == "chips_first_with_text_fallback":
        assert len(draft["answer_options"]) > 0


def test_day_summary_includes_weekly_fields(client):
    response = client.get("/api/day-summary")
    assert response.status_code == 200
    summary = response.json()["summary"]
    assert "weekly_target_kcal" in summary
    assert "weekly_consumed_kcal" in summary
    assert "weekly_drift_kcal" in summary
    assert "weekly_drift_status" in summary
    assert "weekly_coach_message" in summary
    assert "weekly_strategy_label" in summary
    assert "weekly_reason_factors" in summary


def test_local_nutrition_qa_hits_familymart_archetype_pack(client):
    response = client.post(
        "/api/qa/nutrition",
        json={"question": "FamilyMart sweet potato calories", "allow_search": False},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["payload"]["used_search"] is False
    assert any(source["path"].endswith("convenience_store_archetypes_tw.json") for source in body["payload"]["sources"])
    assert "140-220" in body["coach_message"]


def test_local_nutrition_qa_hits_subway_structured_menu_pack(client):
    response = client.post(
        "/api/qa/nutrition",
        json={"question": "Subway roasted chicken breast calories", "allow_search": False},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["payload"]["used_search"] is False
    assert any(source["path"].endswith("chain_menu_cards_tw.json") for source in body["payload"]["sources"])
    assert "331" in body["coach_message"]


def test_local_nutrition_qa_hits_kebuke_structured_menu_pack(client):
    response = client.post(
        "/api/qa/nutrition",
        json={"question": "KEBUKE white pearl milk tea large calories", "allow_search": False},
    )
    assert response.status_code == 200

    body = response.json()
    assert body["payload"]["used_search"] is False
    assert any(source["path"].endswith("chain_menu_cards_tw.json") for source in body["payload"]["sources"])
    assert "581" in body["coach_message"]


def test_build_suggested_update_packet_uses_new_structured_packs():
    packet, sources = build_suggested_update_packet("Subway roast beef")
    assert packet is not None
    assert packet["suggested_kcal"] == 346
    assert any(source["path"].endswith("chain_menu_cards_tw.json") for source in sources)


def test_high_confidence_audio_can_auto_record(db_session_factory):
    with db_session_factory() as db:
        user = db.query(User).filter_by(line_user_id="test-user").one()
        estimate = EstimateResult(
            parsed_items=[{"name": "拿鐵", "kcal": 180}],
            estimate_kcal=180,
            kcal_low=160,
            kcal_high=210,
            confidence=0.9,
            missing_slots=[],
            uncertainty_note="",
            evidence_slots={
                "source_mode": "audio",
                "identified_items": True,
                "portion_signal": True,
                "high_calorie_modifiers": True,
            },
        )

        decision = decide_confirmation(
            db,
            user,
            estimate=estimate,
            mode="standard",
            target_date=date.today(),
            clarification_used=0,
        )

    assert decision.confirmation_mode == "auto_recordable"
    assert decision.stop_reason in {"resolved", "high_confidence_voice_shortcut"}
