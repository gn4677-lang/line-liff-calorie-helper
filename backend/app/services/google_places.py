from __future__ import annotations

from math import asin, cos, radians, sin, sqrt
from typing import Any

import httpx

from ..config import settings


PLACES_FIELD_MASK = ",".join(
    [
        "places.id",
        "places.displayName",
        "places.formattedAddress",
        "places.location",
        "places.rating",
        "places.priceLevel",
        "places.googleMapsUri",
        "places.regularOpeningHours.openNow",
        "places.primaryType",
        "places.types",
    ]
)


def google_places_enabled() -> bool:
    return bool(settings.google_places_api_key)


def search_nearby_places(*, lat: float, lng: float, meal_type: str | None = None, max_results: int = 8) -> list[dict[str, Any]]:
    if not google_places_enabled():
        return []

    included_types = _included_types_for_meal_type(meal_type)
    response = httpx.post(
        "https://places.googleapis.com/v1/places:searchNearby",
        headers={
            "X-Goog-Api-Key": settings.google_places_api_key or "",
            "X-Goog-FieldMask": PLACES_FIELD_MASK,
        },
        json={
            "includedTypes": included_types,
            "maxResultCount": max_results,
            "rankPreference": "DISTANCE",
            "locationRestriction": {
                "circle": {
                    "center": {"latitude": lat, "longitude": lng},
                    "radius": 1500.0,
                }
            },
        },
        timeout=12.0,
    )
    response.raise_for_status()
    payload = response.json()
    return [_normalize_place(item, origin=(lat, lng)) for item in payload.get("places", [])]


def search_text_places(*, query: str, lat: float | None = None, lng: float | None = None, max_results: int = 8) -> list[dict[str, Any]]:
    if not google_places_enabled():
        return []

    body: dict[str, Any] = {"textQuery": query, "maxResultCount": max_results}
    if lat is not None and lng is not None:
        body["locationBias"] = {
            "circle": {
                "center": {"latitude": lat, "longitude": lng},
                "radius": 3000.0,
            }
        }

    response = httpx.post(
        "https://places.googleapis.com/v1/places:searchText",
        headers={
            "X-Goog-Api-Key": settings.google_places_api_key or "",
            "X-Goog-FieldMask": PLACES_FIELD_MASK,
        },
        json=body,
        timeout=12.0,
    )
    response.raise_for_status()
    payload = response.json()
    origin = (lat, lng) if lat is not None and lng is not None else None
    return [_normalize_place(item, origin=origin) for item in payload.get("places", [])]


def _included_types_for_meal_type(meal_type: str | None) -> list[str]:
    if meal_type == "breakfast":
        return ["cafe", "bakery", "breakfast_restaurant"]
    if meal_type == "snack":
        return ["cafe", "bubble_tea_store", "juice_shop", "dessert_shop"]
    return ["restaurant", "meal_takeaway", "sandwich_shop", "food_court"]


def _normalize_place(place: dict[str, Any], *, origin: tuple[float, float] | None = None) -> dict[str, Any]:
    location = place.get("location") or {}
    lat = location.get("latitude")
    lng = location.get("longitude")
    distance = None
    if origin and lat is not None and lng is not None:
        distance = int(_haversine_meters(origin[0], origin[1], lat, lng))

    return {
        "place_id": place.get("id"),
        "name": ((place.get("displayName") or {}).get("text") or "").strip(),
        "lat": lat,
        "lng": lng,
        "address": place.get("formattedAddress") or "",
        "rating": place.get("rating"),
        "price_level": place.get("priceLevel"),
        "open_now": ((place.get("regularOpeningHours") or {}).get("openNow")),
        "primary_types": [place.get("primaryType")] if place.get("primaryType") else place.get("types", []),
        "external_link": place.get("googleMapsUri") or "",
        "distance_meters": distance,
    }


def _haversine_meters(lat1: float, lng1: float, lat2: float, lng2: float) -> float:
    radius = 6371000.0
    dlat = radians(lat2 - lat1)
    dlng = radians(lng2 - lng1)
    a = sin(dlat / 2) ** 2 + cos(radians(lat1)) * cos(radians(lat2)) * sin(dlng / 2) ** 2
    return 2 * radius * asin(sqrt(a))
