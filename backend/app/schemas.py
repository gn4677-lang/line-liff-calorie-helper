from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field


MealMode = Literal["quick", "standard", "fine"]


class IntakeRequest(BaseModel):
    text: str = ""
    meal_type: Optional[str] = None
    source_mode: str = "text"
    mode: MealMode = "standard"
    attachments: list[dict[str, Any]] = Field(default_factory=list)


class ClarifyRequest(BaseModel):
    answer: str


class ConfirmRequest(BaseModel):
    force_confirm: bool = False


class WeightLogRequest(BaseModel):
    weight: float
    date: Optional[date] = None


class PreferencesUpdateRequest(BaseModel):
    likes: Optional[list[str]] = None
    dislikes: Optional[list[str]] = None
    must_have_carbs: Optional[bool] = None
    meal_style: Optional[str] = None
    dinner_style: Optional[str] = None
    compensation_style: Optional[str] = None
    notes: Optional[str] = None


class PlanRequest(BaseModel):
    context: Optional[str] = None
    meal_type: Optional[str] = None
    event_type: Optional[str] = None
    expected_extra_kcal: int = 0


class MealEditRequest(BaseModel):
    description_raw: str
    mode: MealMode = "standard"


class DraftResponse(BaseModel):
    id: str
    date: date
    meal_type: str
    status: str
    source_mode: str
    mode: str
    parsed_items: list[dict[str, Any]]
    missing_slots: list[str]
    followup_question: Optional[str]
    estimate_kcal: int
    kcal_low: int
    kcal_high: int
    confidence: float
    uncertainty_note: str


class MealLogResponse(BaseModel):
    id: int
    date: date
    meal_type: str
    description_raw: str
    kcal_estimate: int
    kcal_low: int
    kcal_high: int
    confidence: float
    source_mode: str
    parsed_items: list[dict[str, Any]]
    uncertainty_note: str


class DaySummaryResponse(BaseModel):
    date: date
    target_kcal: int
    consumed_kcal: int
    remaining_kcal: int
    logs: list[MealLogResponse]
    seven_day_average_weight: Optional[float]
    fourteen_day_direction: str
    target_adjustment_hint: str


class RecommendationItem(BaseModel):
    food_id: Optional[int] = None
    name: str
    meal_types: list[str]
    kcal_low: int
    kcal_high: int
    group: str
    reason: str
    external_links: list[str] = Field(default_factory=list)
    is_favorite: bool = False
    is_golden: bool = False


class RecommendationsResponse(BaseModel):
    remaining_kcal: int
    items: list[RecommendationItem]


class DayPlanResponse(BaseModel):
    target_kcal: int
    allocations: dict[str, int]
    coach_message: str


class CompensationResponse(BaseModel):
    options: list[dict[str, Any]]
    coach_message: str


class MeResponse(BaseModel):
    line_user_id: str
    display_name: str
    daily_calorie_target: int
    provider: str
    now: datetime


class ClientConfigResponse(BaseModel):
    liff_id: Optional[str] = None
    auth_required: bool


class StandardResponse(BaseModel):
    coach_message: str
    draft: Optional[DraftResponse] = None
    summary: Optional[DaySummaryResponse] = None
    log: Optional[MealLogResponse] = None
    recommendations: Optional[RecommendationsResponse] = None
    plan: Optional[DayPlanResponse] = None
    compensation: Optional[CompensationResponse] = None
    payload: dict[str, Any] = Field(default_factory=dict)
