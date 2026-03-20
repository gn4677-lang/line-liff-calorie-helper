from __future__ import annotations

from datetime import datetime, timezone
import json
import uuid
from typing import Any

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from ..models import FavoriteStore, GoldenOrder, MealLog, Notification, PlaceCache, SavedPlace, SearchJob, User, utcnow
from ..schemas import (
    FavoriteStoreRequest,
    FavoriteStoreResponse,
    GoldenOrderResponse,
    NearbyRecommendationItem,
    NearbyRecommendationsResponse,
    NotificationItemResponse,
    SavedPlaceRequest,
    SavedPlaceResponse,
    SearchJobResponse,
)
from .knowledge import build_suggested_update_packet, should_search


GENERIC_PLACE_BANDS = {
    "restaurant": (520, 900),
    "meal_takeaway": (450, 820),
    "sandwich_shop": (320, 620),
    "cafe": (250, 560),
    "breakfast_restaurant": (320, 650),
    "bubble_tea_store": (180, 420),
    "juice_shop": (120, 260),
    "dessert_shop": (280, 520),
    "food_court": (500, 880),
}


def resolve_location_context(db: Session, user: User, payload: dict[str, Any]) -> dict[str, Any]:
    mode = payload.get("mode") or "manual"
    if mode == "saved_place":
        saved_place_id = payload.get("saved_place_id")
        saved = db.get(SavedPlace, saved_place_id) if saved_place_id else None
        if not saved or saved.user_id != user.id:
            raise ValueError("Saved place not found")
        return {
            "source": "saved_place",
            "label": saved.label,
            "query": saved.address or saved.label,
            "lat": saved.lat,
            "lng": saved.lng,
            "place_id": saved.place_id,
            "address": saved.address,
            "location_context": saved.label,
        }

    if mode == "geolocation":
        lat = payload.get("lat")
        lng = payload.get("lng")
        if lat is None or lng is None:
            raise ValueError("Geolocation requires latitude and longitude")
        label = payload.get("label") or "目前位置附近"
        return {
            "source": "geolocation",
            "label": label,
            "query": label,
            "lat": float(lat),
            "lng": float(lng),
            "place_id": None,
            "address": payload.get("query") or "",
            "location_context": label,
        }

    query = (payload.get("query") or payload.get("label") or "").strip()
    if not query:
        raise ValueError("Manual location requires a query")

    return {
        "source": "manual",
        "label": query,
        "query": query,
        "lat": payload.get("lat"),
        "lng": payload.get("lng"),
        "place_id": None,
        "address": query,
        "location_context": query,
    }


def save_place(db: Session, user: User, request: SavedPlaceRequest) -> SavedPlace:
    existing = db.scalar(
        select(SavedPlace).where(SavedPlace.user_id == user.id, SavedPlace.label == request.label)
    )
    if request.is_default:
        for item in db.scalars(select(SavedPlace).where(SavedPlace.user_id == user.id)):
            item.is_default = False
            db.add(item)

    if existing:
        existing.provider = request.provider
        existing.place_id = request.place_id
        existing.lat = request.lat
        existing.lng = request.lng
        existing.address = request.address
        existing.is_default = request.is_default
        existing.updated_at = utcnow()
        db.add(existing)
        db.commit()
        db.refresh(existing)
        return existing

    saved = SavedPlace(
        user_id=user.id,
        label=request.label,
        provider=request.provider,
        place_id=request.place_id,
        lat=request.lat,
        lng=request.lng,
        address=request.address,
        is_default=request.is_default,
    )
    db.add(saved)
    db.commit()
    db.refresh(saved)
    return saved


def list_saved_places(db: Session, user: User) -> list[SavedPlaceResponse]:
    places = list(
        db.scalars(select(SavedPlace).where(SavedPlace.user_id == user.id).order_by(desc(SavedPlace.is_default), SavedPlace.label))
    )
    return [saved_place_to_response(item) for item in places]


def upsert_favorite_store(db: Session, user: User, request: FavoriteStoreRequest) -> tuple[FavoriteStore, GoldenOrder | None]:
    store = db.scalar(select(FavoriteStore).where(FavoriteStore.user_id == user.id, FavoriteStore.name == request.name))
    if store:
        store.label = request.label or store.label or request.name
        store.place_id = request.place_id or store.place_id
        store.address = request.address or store.address
        store.external_link = request.external_link or store.external_link
        store.usage_count += 1
        store.last_used_at = utcnow()
    else:
        store = FavoriteStore(
            user_id=user.id,
            name=request.name,
            label=request.label or request.name,
            place_id=request.place_id,
            address=request.address,
            external_link=request.external_link,
            usage_count=1,
            source="manual",
        )
    db.add(store)
    db.flush()

    golden_order = None
    if request.mark_golden and request.kcal_low is not None and request.kcal_high is not None:
        golden_order = db.scalar(select(GoldenOrder).where(GoldenOrder.user_id == user.id, GoldenOrder.title == request.name))
        if golden_order:
            golden_order.store_name = request.name
            golden_order.place_id = request.place_id or golden_order.place_id
            golden_order.kcal_low = request.kcal_low
            golden_order.kcal_high = request.kcal_high
            golden_order.meal_types = request.meal_types
            golden_order.usage_count += 1
            golden_order.last_used_at = utcnow()
        else:
            golden_order = GoldenOrder(
                user_id=user.id,
                title=request.name,
                store_name=request.name,
                place_id=request.place_id,
                kcal_low=request.kcal_low,
                kcal_high=request.kcal_high,
                meal_types=request.meal_types,
                usage_count=1,
            )
        db.add(golden_order)

    db.commit()
    db.refresh(store)
    if golden_order:
        db.refresh(golden_order)
    return store, golden_order


def list_favorite_stores(db: Session, user: User) -> list[FavoriteStoreResponse]:
    golden_by_place = {
        item.place_id: item.id
        for item in db.scalars(select(GoldenOrder).where(GoldenOrder.user_id == user.id))
        if item.place_id
    }
    stores = list(
        db.scalars(select(FavoriteStore).where(FavoriteStore.user_id == user.id).order_by(desc(FavoriteStore.usage_count), desc(FavoriteStore.last_used_at)))
    )
    return [favorite_store_to_response(item, golden_by_place.get(item.place_id)) for item in stores]


def list_golden_orders(db: Session, user: User) -> list[GoldenOrderResponse]:
    rows = list(
        db.scalars(select(GoldenOrder).where(GoldenOrder.user_id == user.id).order_by(desc(GoldenOrder.usage_count), desc(GoldenOrder.last_used_at)))
    )
    return [golden_order_to_response(row) for row in rows]


def build_nearby_heuristics(
    db: Session,
    user: User,
    *,
    location_context: dict[str, Any],
    meal_type: str | None,
    remaining_kcal: int,
) -> NearbyRecommendationsResponse:
    favorite_rows = list_favorite_stores(db, user)[:4]
    saved_places = [item.model_dump() for item in list_saved_places(db, user)[:4]]
    items: list[NearbyRecommendationItem] = []

    for order in list_golden_orders(db, user):
        if meal_type and order.meal_types and meal_type not in order.meal_types:
            continue
        if order.kcal_high and order.kcal_high > max(remaining_kcal + 200, 400):
            continue
        items.append(
            NearbyRecommendationItem(
                name=order.title,
                place_id=order.place_id,
                kcal_low=order.kcal_low,
                kcal_high=order.kcal_high,
                reason="從你反覆接受的穩定選項開始。",
                reason_factors=["穩定選項", "和你平常會接受的範圍一致"],
                source="golden_order",
            )
        )

    for store in favorite_rows:
        if any(item.name == store.name for item in items):
            continue
        kcal_low, kcal_high = _generic_kcal_band("restaurant")
        items.append(
            NearbyRecommendationItem(
                name=store.name,
                place_id=store.place_id,
                kcal_low=kcal_low,
                kcal_high=kcal_high,
                reason="先從你常去的店開始。",
                reason_factors=["常去店家", "背景搜尋還在補充時的穩定預設"],
                external_link=store.external_link,
                source="favorite_store",
            )
        )

    for place in db.scalars(select(PlaceCache).order_by(desc(PlaceCache.fetched_at)).limit(6)):
        if any(item.place_id == place.place_id for item in items if item.place_id):
            continue
        kcal_low, kcal_high = _generic_kcal_band((place.primary_types or ["restaurant"])[0])
        if kcal_high > max(remaining_kcal + 300, 450):
            continue
        items.append(
            NearbyRecommendationItem(
                name=place.name,
                place_id=place.place_id,
                distance_meters=None,
                travel_minutes=None,
                open_now=place.open_now,
                kcal_low=kcal_low,
                kcal_high=kcal_high,
                reason="先用最近快取到的附近候選。",
                reason_factors=["本地快取", "不用等搜尋完成也能先給你可行選項"],
                external_link=place.external_link,
                source="place_cache",
            )
        )
        if len(items) >= 6:
            break

    return NearbyRecommendationsResponse(
        location_context_used=location_context.get("location_context") or location_context.get("label") or "manual",
        heuristic_items=items[:6],
        search_job_id=None,
        saved_place_options=saved_places,
        favorite_stores=[item.model_dump() for item in favorite_rows[:4]],
    )


def create_search_job(db: Session, user: User, *, job_type: str, request_payload: dict[str, Any]) -> SearchJob:
    job = SearchJob(
        id=str(uuid.uuid4()),
        user_id=user.id,
        job_type=job_type,
        status="pending",
        request_payload=request_payload,
    )
    db.add(job)
    db.commit()
    db.refresh(job)
    return job


def search_job_to_response(job: SearchJob) -> SearchJobResponse:
    return SearchJobResponse(
        id=job.id,
        job_type=job.job_type,
        status=job.status,
        job_retry_count=job.job_retry_count,
        last_error=job.last_error or "",
        result_payload=job.result_payload or {},
        suggested_update=job.suggested_update or {},
        notification_ready=bool(job.notification_sent_at),
    )


def create_notification(
    db: Session,
    user: User,
    *,
    notification_type: str,
    title: str,
    body: str,
    payload: dict[str, Any],
    related_job_id: str | None = None,
) -> Notification:
    row = Notification(
        id=str(uuid.uuid4()),
        user_id=user.id,
        type=notification_type,
        title=title,
        body=body,
        payload=payload,
        related_job_id=related_job_id,
    )
    db.add(row)
    db.commit()
    db.refresh(row)
    return row


def list_notifications(db: Session, user: User) -> list[NotificationItemResponse]:
    rows = list(
        db.scalars(select(Notification).where(Notification.user_id == user.id).order_by(desc(Notification.created_at)).limit(20))
    )
    return [notification_to_response(row) for row in rows]


def mark_notification_read(db: Session, user: User, notification_id: str) -> NotificationItemResponse:
    row = db.get(Notification, notification_id)
    if not row or row.user_id != user.id:
        raise ValueError("Notification not found")
    row.status = "read"
    row.read_at = utcnow()
    db.add(row)
    db.commit()
    db.refresh(row)
    return notification_to_response(row)


def count_unread_notifications(db: Session, user: User) -> int:
    rows = list(db.scalars(select(Notification).where(Notification.user_id == user.id, Notification.status == "unread")))
    return len(rows)


def apply_search_job(db: Session, user: User, job: SearchJob) -> SearchJobResponse:
    if job.user_id != user.id:
        raise ValueError("Search job not found")

    suggested_update = job.suggested_update or {}
    target_log_id = suggested_update.get("target_log_id")
    if target_log_id:
        log = db.get(MealLog, target_log_id)
        if not log or log.user_id != user.id:
            raise ValueError("Target meal log not found")
        original = log.kcal_estimate
        log.kcal_estimate = int(suggested_update.get("suggested_kcal", log.kcal_estimate))
        log.kcal_low = int(suggested_update.get("suggested_range", {}).get("low", log.kcal_low))
        log.kcal_high = int(suggested_update.get("suggested_range", {}).get("high", log.kcal_high))
        metadata = dict(log.memory_metadata or {})
        metadata["async_update_applied"] = True
        metadata["async_update_reason"] = suggested_update.get("reason")
        metadata["async_update_sources"] = suggested_update.get("sources", [])
        metadata["original_kcal_before_async_update"] = original
        if suggested_update.get("store_name"):
            metadata["store_name"] = suggested_update["store_name"]
        log.memory_metadata = metadata
        db.add(log)

        if suggested_update.get("store_name"):
            upsert_favorite_store(
                db,
                user,
                FavoriteStoreRequest(
                    name=suggested_update["store_name"],
                    label=suggested_update["store_name"],
                    place_id=suggested_update.get("place_id"),
                    external_link=suggested_update.get("external_link", ""),
                    kcal_low=int(suggested_update.get("suggested_range", {}).get("low", log.kcal_low)),
                    kcal_high=int(suggested_update.get("suggested_range", {}).get("high", log.kcal_high)),
                    meal_types=[log.meal_type],
                    mark_golden=True,
                ),
            )

    job.status = "applied"
    db.add(job)
    db.commit()
    db.refresh(job)
    return search_job_to_response(job)


def dismiss_search_job(db: Session, user: User, job: SearchJob) -> SearchJobResponse:
    if job.user_id != user.id:
        raise ValueError("Search job not found")
    job.status = "dismissed"
    db.add(job)
    db.commit()
    db.refresh(job)
    return search_job_to_response(job)


def upsert_place_cache(db: Session, places: list[dict[str, Any]], *, provider: str = "google_places") -> None:
    for item in places:
        place_id = item.get("place_id")
        if not place_id:
            continue
        row = db.scalar(select(PlaceCache).where(PlaceCache.provider == provider, PlaceCache.place_id == place_id))
        if row is None:
            row = PlaceCache(provider=provider, place_id=place_id, name=item.get("name") or place_id)
        row.name = item.get("name") or row.name
        row.lat = item.get("lat")
        row.lng = item.get("lng")
        row.address = item.get("address") or row.address
        row.rating = item.get("rating")
        row.price_level = item.get("price_level")
        row.open_now = item.get("open_now")
        row.primary_types = item.get("primary_types") or []
        row.external_link = item.get("external_link") or row.external_link
        row.fetched_at = utcnow()
        db.add(row)
    db.commit()


def maybe_queue_menu_precision_job(
    db: Session,
    user: User,
    *,
    trace_id: str | None = None,
    text: str,
    log: MealLog | None = None,
    notify_on_complete: bool = True,
) -> SearchJob | None:
    if not text.strip():
        return None
    if not (should_search(text) or build_suggested_update_packet(text)[0]):
        return None
    payload = {
        "text": text,
        "target_log_id": log.id if log else None,
        "notify_on_complete": notify_on_complete,
    }
    if trace_id:
        payload["trace_id"] = trace_id
    return create_search_job(db, user, job_type="menu_precision", request_payload=payload)


def build_external_food_job_result(question: str, *, source_hint: str | None = None) -> tuple[dict[str, Any], dict[str, Any]]:
    suggested_update, sources = build_suggested_update_packet(question, source_hint=source_hint)
    return (
        {"question": question, "sources": sources},
        suggested_update or {},
    )


def saved_place_to_response(item: SavedPlace) -> SavedPlaceResponse:
    return SavedPlaceResponse(
        id=item.id,
        label=item.label,
        provider=item.provider,
        place_id=item.place_id,
        lat=item.lat,
        lng=item.lng,
        address=item.address,
        is_default=item.is_default,
    )


def favorite_store_to_response(item: FavoriteStore, golden_order_id: int | None = None) -> FavoriteStoreResponse:
    return FavoriteStoreResponse(
        id=item.id,
        name=item.name,
        label=item.label,
        place_id=item.place_id,
        address=item.address,
        external_link=item.external_link,
        usage_count=item.usage_count,
        golden_order_id=golden_order_id,
    )


def golden_order_to_response(item: GoldenOrder) -> GoldenOrderResponse:
    return GoldenOrderResponse(
        id=item.id,
        title=item.title,
        store_name=item.store_name,
        place_id=item.place_id,
        kcal_low=item.kcal_low,
        kcal_high=item.kcal_high,
        meal_types=item.meal_types or [],
    )


def notification_to_response(item: Notification) -> NotificationItemResponse:
    return NotificationItemResponse(
        id=item.id,
        type=item.type,
        title=item.title,
        body=item.body,
        status=item.status,
        payload=item.payload or {},
        created_at=item.created_at,
    )


def _generic_kcal_band(primary_type: str) -> tuple[int, int]:
    return GENERIC_PLACE_BANDS.get(primary_type or "restaurant", (500, 850))
