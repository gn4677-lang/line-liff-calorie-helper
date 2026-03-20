from __future__ import annotations

from datetime import date, datetime, timedelta, timezone

from app.models import Food, GoldenOrder, MealLog, RecommendationProfile, RecommendationSession, User


def _get_user(db):
    return db.query(User).filter_by(line_user_id="test-user").one()


def test_body_goal_activity_and_journal_flow(client):
    today = date.today().isoformat()
    start = (date.today() - timedelta(days=6)).isoformat()

    goal_response = client.patch(
        "/api/body-goal",
        json={
            "target_weight_kg": 65.0,
            "estimated_tdee_kcal": 2200,
            "default_daily_deficit_kcal": 400,
        },
    )
    assert goal_response.status_code == 200
    body_goal = goal_response.json()["payload"]["body_goal"]
    assert body_goal["base_target_kcal"] == 1800
    assert body_goal["target_weight_kg"] == 65.0

    activity_response = client.post(
        "/api/activity-adjustments",
        json={
            "date": today,
            "label": "快走 45 分鐘",
            "estimated_burn_kcal": 220,
            "duration_minutes": 45,
        },
    )
    assert activity_response.status_code == 200
    assert activity_response.json()["summary"]["effective_target_kcal"] == 2020

    manual_log_response = client.post(
        "/api/meal-logs/manual",
        json={
            "date": today,
            "meal_type": "lunch",
            "description_raw": "雞胸便當",
            "kcal_estimate": 620,
        },
    )
    assert manual_log_response.status_code == 200
    summary = manual_log_response.json()["summary"]
    log_id = manual_log_response.json()["log"]["id"]
    assert summary["consumed_kcal"] == 620
    assert summary["remaining_kcal"] == 1400
    assert summary["today_activity_burn_kcal"] == 220
    assert summary["meal_subtotals"]["lunch"] == 620

    day_summary_response = client.get(f"/api/day-summary?date={today}")
    assert day_summary_response.status_code == 200
    day_summary = day_summary_response.json()["summary"]
    assert day_summary["base_target_kcal"] == 1800
    assert day_summary["effective_target_kcal"] == 2020
    assert len(day_summary["logs"]) == 1

    range_response = client.get(f"/api/logbook-range?start={start}&end={today}")
    assert range_response.status_code == 200
    days = range_response.json()["payload"]["days"]
    assert len(days) == 7
    assert days[-1]["consumed_kcal"] == 620
    assert days[-1]["meal_count"] == 1

    patch_response = client.patch(
        f"/api/meal-logs/{log_id}",
        json={
            "description_raw": "雞胸便當加青菜",
            "kcal_estimate": 560,
            "meal_type": "dinner",
        },
    )
    assert patch_response.status_code == 200
    patched_summary = patch_response.json()["summary"]
    assert patched_summary["consumed_kcal"] == 560
    assert patched_summary["remaining_kcal"] == 1460
    assert patched_summary["logs"][0]["meal_type"] == "dinner"

    delete_response = client.delete(f"/api/meal-logs/{log_id}")
    assert delete_response.status_code == 200
    deleted_summary = delete_response.json()["summary"]
    assert deleted_summary["consumed_kcal"] == 0
    assert deleted_summary["logs"] == []


def test_progress_series_and_weight_tracking(client):
    today = date.today()
    yesterday = today - timedelta(days=1)

    client.patch(
        "/api/body-goal",
        json={
            "target_weight_kg": 64.0,
            "estimated_tdee_kcal": 2300,
            "default_daily_deficit_kcal": 500,
        },
    )
    client.post("/api/weights", json={"date": yesterday.isoformat(), "weight": 72.0})
    client.post("/api/weights", json={"date": today.isoformat(), "weight": 71.5})
    client.post(
        "/api/meal-logs/manual",
        json={
            "date": yesterday.isoformat(),
            "meal_type": "lunch",
            "description_raw": "便當",
            "kcal_estimate": 680,
        },
    )
    client.post(
        "/api/meal-logs/manual",
        json={
            "date": today.isoformat(),
            "meal_type": "dinner",
            "description_raw": "烤雞沙拉",
            "kcal_estimate": 760,
        },
    )
    client.post(
        "/api/activity-adjustments",
        json={
            "date": yesterday.isoformat(),
            "label": "慢跑",
            "estimated_burn_kcal": 180,
        },
    )

    series_response = client.get("/api/progress-series?range=7d")
    assert series_response.status_code == 200
    series = series_response.json()["payload"]["series"]
    assert series["range"] == "7d"
    assert len(series["weight_points"]) >= 2
    assert len(series["calorie_points"]) == 7
    assert any(point["value"] == 680 for point in series["calorie_points"])
    assert any(point["value"] == 180 for point in series["activity_points"])


def test_eat_feed_acceptance_updates_recommendation_profile_and_session(client, db_session_factory):
    with db_session_factory() as db:
        user = _get_user(db)
        now = datetime.now(timezone.utc)
        db.add(
            GoldenOrder(
                user_id=user.id,
                title="Subway 雞胸潛艇堡",
                store_name="Subway",
                kcal_low=420,
                kcal_high=480,
                meal_types=["lunch"],
                usage_count=8,
                last_used_at=now,
            )
        )
        db.add(
            Food(
                user_id=user.id,
                name="雞胸沙拉",
                meal_types=["lunch"],
                kcal_low=320,
                kcal_high=420,
                is_favorite=True,
                usage_count=5,
                last_used_at=now,
            )
        )
        db.commit()

    eat_feed_response = client.post(
        "/api/eat-feed",
        json={
            "meal_type": "lunch",
            "time_context": "now",
            "style_context": "",
            "location_mode": "none",
        },
    )
    assert eat_feed_response.status_code == 200
    eat_feed = eat_feed_response.json()["payload"]["eat_feed"]
    assert eat_feed["top_pick"] is not None
    assert eat_feed["top_pick"]["title"] == "Subway 雞胸潛艇堡"
    assert eat_feed["smart_chips"]

    manual_log_response = client.post(
        "/api/meal-logs/manual",
        json={
            "date": date.today().isoformat(),
            "meal_type": "lunch",
            "description_raw": eat_feed["top_pick"]["title"],
            "kcal_estimate": eat_feed["top_pick"]["kcal_low"],
        },
    )
    assert manual_log_response.status_code == 200
    log_id = manual_log_response.json()["log"]["id"]

    with db_session_factory() as db:
        session = db.get(RecommendationSession, eat_feed["session_id"])
        profile = db.query(RecommendationProfile).filter_by(user_id=_get_user(db).id).one()
        assert session is not None
        assert session.status == "accepted"
        assert session.accepted_event_type == "accepted_top_pick"
        assert profile.sample_size == 1
        assert profile.favorite_bias_strength > 0.6

    patch_response = client.patch(
        f"/api/meal-logs/{log_id}",
        json={"kcal_estimate": eat_feed["top_pick"]["kcal_high"] + 120},
    )
    assert patch_response.status_code == 200

    with db_session_factory() as db:
        session = db.get(RecommendationSession, eat_feed["session_id"])
        assert session.status == "corrected_after_acceptance"
        assert session.accepted_event_type == "post_log_manual_correction"


def test_eat_feed_smart_chips_change_by_context_and_rerank_only_session(client, db_session_factory):
    with db_session_factory() as db:
        user = _get_user(db)
        now = datetime.now(timezone.utc)
        db.add_all(
            [
                Food(
                    user_id=user.id,
                    name="鮪魚飯糰",
                    meal_types=["breakfast"],
                    kcal_low=230,
                    kcal_high=300,
                    is_favorite=True,
                    usage_count=5,
                    last_used_at=now,
                ),
                Food(
                    user_id=user.id,
                    name="優格水果杯",
                    meal_types=["breakfast"],
                    kcal_low=180,
                    kcal_high=240,
                    is_favorite=True,
                    usage_count=4,
                    last_used_at=now,
                ),
                GoldenOrder(
                    user_id=user.id,
                    title="Subway 雞胸潛艇堡",
                    store_name="Subway",
                    kcal_low=420,
                    kcal_high=480,
                    meal_types=["lunch"],
                    usage_count=9,
                    last_used_at=now,
                ),
                Food(
                    user_id=user.id,
                    name="牛肉湯麵",
                    meal_types=["lunch"],
                    kcal_low=510,
                    kcal_high=610,
                    is_favorite=True,
                    usage_count=6,
                    last_used_at=now,
                ),
                Food(
                    user_id=user.id,
                    name="海鮮湯麵",
                    meal_types=["lunch"],
                    kcal_low=500,
                    kcal_high=590,
                    is_favorite=True,
                    usage_count=5,
                    last_used_at=now,
                ),
                Food(
                    user_id=user.id,
                    name="鮭魚沙拉",
                    meal_types=["lunch"],
                    kcal_low=360,
                    kcal_high=430,
                    is_favorite=True,
                    usage_count=4,
                    last_used_at=now,
                ),
                MealLog(
                    user_id=user.id,
                    meal_session_id="session-recent-soup",
                    date=date.today() - timedelta(days=1),
                    meal_type="lunch",
                    description_raw="牛肉湯麵",
                    kcal_estimate=560,
                    kcal_low=520,
                    kcal_high=610,
                    confidence=1.0,
                    source_mode="manual",
                    parsed_items=[{"name": "牛肉湯麵", "kcal": 560}],
                    uncertainty_note="",
                ),
            ]
        )
        db.commit()

    breakfast_feed = client.post(
        "/api/eat-feed",
        json={"meal_type": "breakfast", "time_context": "now", "style_context": "", "location_mode": "none"},
    )
    assert breakfast_feed.status_code == 200
    breakfast_payload = breakfast_feed.json()["payload"]["eat_feed"]
    breakfast_chip_ids = {item["id"] for item in breakfast_payload["smart_chips"]}
    assert breakfast_chip_ids

    lunch_feed = client.post(
        "/api/eat-feed",
        json={"meal_type": "lunch", "time_context": "now", "style_context": "", "location_mode": "none"},
    )
    assert lunch_feed.status_code == 200
    lunch_payload = lunch_feed.json()["payload"]["eat_feed"]
    lunch_chip_ids = [item["id"] for item in lunch_payload["smart_chips"]]
    assert set(lunch_chip_ids) != breakfast_chip_ids
    assert all("supported_candidate_count" in item and item["supported_candidate_count"] > 0 for item in lunch_payload["smart_chips"])

    assert lunch_payload["smart_chips"]
    rerank_chip = lunch_payload["smart_chips"][0]
    before_top_three = [
        lunch_payload["top_pick"]["title"],
        *[item["title"] for item in lunch_payload["backup_picks"]],
    ]

    reranked_feed = client.post(
        "/api/eat-feed",
        json={
            "meal_type": "lunch",
            "time_context": "now",
            "style_context": "",
            "location_mode": "none",
            "selected_chip_id": rerank_chip["id"],
        },
    )
    assert reranked_feed.status_code == 200
    reranked_payload = reranked_feed.json()["payload"]["eat_feed"]
    after_top_three = [
        reranked_payload["top_pick"]["title"],
        *[item["title"] for item in reranked_payload["backup_picks"]],
    ]
    assert after_top_three != before_top_three

    with db_session_factory() as db:
        profile = db.query(RecommendationProfile).filter_by(user_id=_get_user(db).id).one_or_none()
        if profile is not None:
            assert profile.sample_size == 0


def test_contextual_endpoints_support_eat_surface(client):
    save_place_response = client.post(
        "/api/saved-places",
        json={
            "label": "公司",
            "address": "台北市信義區松仁路",
            "provider": "manual",
            "is_default": True,
        },
    )
    assert save_place_response.status_code == 200

    saved_places_response = client.get("/api/saved-places")
    assert saved_places_response.status_code == 200
    saved_places = saved_places_response.json()["payload"]["saved_places"]
    assert len(saved_places) == 1
    assert saved_places[0]["label"] == "公司"
    saved_place_id = saved_places[0]["id"]

    favorite_store_response = client.post(
        "/api/favorite-stores",
        json={
            "name": "Subway 市府店",
            "label": "Subway 市府店",
            "address": "信義區市府路",
            "external_link": "https://example.com/subway",
        },
    )
    assert favorite_store_response.status_code == 200

    favorites_response = client.get("/api/favorite-stores")
    assert favorites_response.status_code == 200
    favorites = favorites_response.json()["payload"]["favorite_stores"]
    assert len(favorites) == 1
    assert favorites[0]["name"] == "Subway 市府店"

    eat_feed_response = client.post(
        "/api/eat-feed",
        json={
            "meal_type": "lunch",
            "time_context": "now",
            "location_mode": "saved_place",
            "saved_place_id": saved_place_id,
        },
    )
    assert eat_feed_response.status_code == 200
    eat_feed = eat_feed_response.json()["payload"]["eat_feed"]
    assert eat_feed["location_context_used"] == "公司"


def test_store_context_and_timing_patterns_shape_session_smart_chips(client, db_session_factory):
    with db_session_factory() as db:
        user = _get_user(db)
        now = datetime.now(timezone.utc)
        db.add_all(
            [
                Food(
                    user_id=user.id,
                    name="牛肉湯麵",
                    meal_types=["lunch"],
                    kcal_low=480,
                    kcal_high=560,
                    is_favorite=True,
                    usage_count=5,
                    last_used_at=now,
                    store_context={
                        "top_store_key": "place-beef-noodle",
                        "top_store_name": "老張牛肉麵",
                        "top_place_id": "place-beef-noodle",
                        "top_avg_kcal": 590,
                        "top_portion_ratio": 1.12,
                        "top_location_context": "公司附近",
                        "distinct_store_count": 1,
                        "by_store": {
                            "place-beef-noodle": {
                                "store_name": "老張牛肉麵",
                                "place_id": "place-beef-noodle",
                                "count": 4,
                                "avg_kcal": 590,
                                "kcal_low": 540,
                                "kcal_high": 640,
                                "portion_ratio": 1.12,
                                "meal_type_counts": {"lunch": 4},
                            }
                        },
                    },
                ),
                MealLog(
                    user_id=user.id,
                    meal_session_id="timing-1",
                    date=date.today() - timedelta(days=7),
                    event_at=now - timedelta(days=7),
                    meal_type="lunch",
                    description_raw="牛肉湯麵",
                    kcal_estimate=590,
                    kcal_low=540,
                    kcal_high=640,
                    confidence=1.0,
                    source_mode="manual",
                    parsed_items=[{"name": "牛肉湯麵", "kcal": 590}],
                    uncertainty_note="",
                    memory_metadata={"store_name": "老張牛肉麵", "place_id": "place-beef-noodle", "location_context": "公司附近"},
                ),
                MealLog(
                    user_id=user.id,
                    meal_session_id="timing-2",
                    date=date.today() - timedelta(days=5),
                    event_at=now - timedelta(days=5),
                    meal_type="lunch",
                    description_raw="海鮮湯麵",
                    kcal_estimate=530,
                    kcal_low=500,
                    kcal_high=590,
                    confidence=1.0,
                    source_mode="manual",
                    parsed_items=[{"name": "海鮮湯麵", "kcal": 530}],
                    uncertainty_note="",
                ),
            ]
        )
        db.commit()

    response = client.post(
        "/api/eat-feed",
        json={"meal_type": "lunch", "time_context": "now", "style_context": "", "location_mode": "none"},
    )
    assert response.status_code == 200
    payload = response.json()["payload"]["eat_feed"]
    top_pick = payload["top_pick"]
    assert top_pick["title"] == "牛肉湯麵"
    assert top_pick["store_name"] == "老張牛肉麵"
    assert payload["smart_chips"] == [] or any(chip["id"] in {"soup", "rice_or_noodle", "repeat_safe"} for chip in payload["smart_chips"])
    assert any("份量" in reason or "老張牛肉麵" in reason for reason in top_pick["reason_factors"])
