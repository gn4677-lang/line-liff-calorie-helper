def test_onboarding_state_defaults_to_should_show(client):
    response = client.get("/api/onboarding-state")

    assert response.status_code == 200
    payload = response.json()
    assert payload["should_show"] is True
    assert payload["completed"] is False
    assert payload["preferences"]["breakfast_habit"] == "unknown"


def test_onboarding_seeds_preferences_and_memory_profile(client):
    response = client.post(
        "/api/preferences/onboarding",
        json={
            "breakfast_habit": "rare",
            "carb_need": "high",
            "dinner_style": "high_protein",
            "hard_dislikes": ["韓式"],
            "compensation_style": "gentle_1d",
        },
    )

    assert response.status_code == 200

    onboarding_state = client.get("/api/onboarding-state").json()
    assert onboarding_state["should_show"] is False
    assert onboarding_state["completed"] is True
    assert onboarding_state["preferences"]["hard_dislikes"] == ["韓式"]

    profile = client.get("/api/memory/profile")
    assert profile.status_code == 200
    payload = profile.json()
    labels = {item["label"] for item in payload["active_hypotheses"]}
    assert "rarely_eats_breakfast" in labels
    assert "needs_carbs" in labels
    assert any(item["canonical_label"] == "korean" for item in payload["stable_signals"])


def test_preference_correction_overrides_user_stated_memory(client):
    client.post(
        "/api/preferences/onboarding",
        json={
            "breakfast_habit": "rare",
            "carb_need": "high",
            "dinner_style": "normal",
            "hard_dislikes": [],
            "compensation_style": "normal_return",
        },
    )

    correction = client.post(
        "/api/preferences/correction",
        json={
            "breakfast_habit": "regular",
            "correction_note": "我最近開始吃早餐了",
        },
    )

    assert correction.status_code == 200

    profile = client.get("/api/memory/profile")
    assert profile.status_code == 200
    labels = {item["label"] for item in profile.json()["active_hypotheses"]}
    assert "rarely_eats_breakfast" not in labels
