def test_weight_summary_and_recommendations(client):
    client.post("/api/weights", json={"weight": 72.4})
    draft = client.post("/api/intake", json={"text": "雞胸便當 半飯", "mode": "quick"}).json()
    client.post(f"/api/intake/{draft['draft']['id']}/confirm", json={"force_confirm": True})

    summary = client.get("/api/day-summary")
    assert summary.status_code == 200
    assert "remaining_kcal" in summary.json()["summary"]

    recommendations = client.get("/api/recommendations")
    assert recommendations.status_code == 200
    assert len(recommendations.json()["recommendations"]["items"]) > 0
