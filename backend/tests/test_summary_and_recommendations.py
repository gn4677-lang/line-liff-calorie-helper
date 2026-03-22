import pytest

pytestmark = pytest.mark.agentic


def test_weight_summary_and_recommendations(client):
    weight_response = client.post("/api/weights", json={"weight": 72.4})
    assert weight_response.status_code == 200
    weight_summary = weight_response.json()["summary"]
    assert "weekly_coach_message" in weight_summary
    assert "weekly_strategy_label" in weight_summary
    draft = client.post("/api/intake", json={"text": "雞胸便當 半飯", "mode": "quick"}).json()
    client.post(f"/api/intake/{draft['draft']['id']}/confirm", json={"force_confirm": True})

    summary = client.get("/api/day-summary")
    assert summary.status_code == 200
    assert "remaining_kcal" in summary.json()["summary"]

    recommendations = client.get("/api/recommendations", params={"meal_type": "lunch"})
    assert recommendations.status_code == 200
    body = recommendations.json()
    assert len(body["recommendations"]["items"]) > 0
    assert body["recommendations"]["hero_reason"]
    assert body["recommendations"]["coach_message"]
    assert body["recommendations"]["strategy_label"]
