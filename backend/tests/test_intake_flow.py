def test_text_intake_and_confirm(client):
    intake = client.post("/api/intake", json={"text": "雞胸便當 半飯 無糖豆漿", "mode": "standard"})
    assert intake.status_code == 200
    payload = intake.json()
    assert payload["draft"]["estimate_kcal"] > 0

    confirm = client.post(f"/api/intake/{payload['draft']['id']}/confirm", json={"force_confirm": True})
    assert confirm.status_code == 200
    assert confirm.json()["summary"]["consumed_kcal"] > 0


def test_clarification_flow(client):
    intake = client.post("/api/intake", json={"text": "便當", "mode": "standard"})
    assert intake.status_code == 200
    payload = intake.json()
    assert payload["draft"]["status"] == "awaiting_clarification"

    clarify = client.post(f"/api/intake/{payload['draft']['id']}/clarify", json={"answer": "雞腿飯，飯半碗，有滷蛋"})
    assert clarify.status_code == 200
    followup = clarify.json()
    assert followup["draft"]["estimate_kcal"] > 0
