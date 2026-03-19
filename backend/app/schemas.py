from __future__ import annotations

from datetime import date, datetime
from typing import Any, Literal, Optional

from pydantic import BaseModel, Field, field_validator


MealMode = Literal["quick", "standard", "fine"]
BreakfastHabit = Literal["regular", "occasional", "rare", "variable", "unknown"]
CarbNeed = Literal["high", "flexible", "low", "variable"]
DinnerStyle = Literal["light", "normal", "indulgent", "high_protein", "variable"]
CompensationStyle = Literal["normal_return", "gentle_1d", "distributed_2_3d", "let_system_decide", "gentle"]


class IntakeRequest(BaseModel):
    text: str = ""
    meal_type: Optional[str] = None
    source_mode: str = "text"
    mode: MealMode = "standard"
    attachments: list[dict[str, Any]] = Field(default_factory=list)
    event_at: Optional[datetime] = None
    event_context: str = "normal"
    location_context: Optional[str] = None
    meal_type_confidence: Optional[float] = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class ClarifyRequest(BaseModel):
    answer: str


class ConfirmRequest(BaseModel):
    force_confirm: bool = False


class WeightLogRequest(BaseModel):
    weight: float
    date: Optional[date] = None


class OnboardingPreferencesRequest(BaseModel):
    breakfast_habit: BreakfastHabit
    carb_need: CarbNeed
    dinner_style: DinnerStyle
    hard_dislikes: list[str] = Field(default_factory=list, max_length=3)
    compensation_style: CompensationStyle

    @field_validator("hard_dislikes")
    @classmethod
    def validate_dislikes(cls, values: list[str]) -> list[str]:
        if "none" in values and len(values) > 1:
            raise ValueError("hard_dislikes cannot contain other values when 'none' is selected")
        return values


class PreferencesUpdateRequest(BaseModel):
    likes: Optional[list[str]] = None
    dislikes: Optional[list[str]] = None
    hard_dislikes: Optional[list[str]] = None
    must_have_carbs: Optional[bool] = None
    breakfast_habit: Optional[BreakfastHabit] = None
    carb_need: Optional[CarbNeed] = None
    meal_style: Optional[str] = None
    dinner_style: Optional[DinnerStyle] = None
    compensation_style: Optional[CompensationStyle] = None
    notes: Optional[str] = None


class PreferenceCorrectionRequest(BaseModel):
    breakfast_habit: Optional[BreakfastHabit] = None
    carb_need: Optional[CarbNeed] = None
    dinner_style: Optional[DinnerStyle] = None
    hard_dislikes: Optional[list[str]] = None
    compensation_style: Optional[CompensationStyle] = None
    correction_note: Optional[str] = None


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
    meal_session_id: Optional[str] = None
    date: date
    event_at: Optional[datetime] = None
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
    metadata: dict[str, Any] = Field(default_factory=dict)


class MealLogResponse(BaseModel):
    id: int
    meal_session_id: Optional[str] = None
    date: date
    event_at: Optional[datetime] = None
    meal_type: str
    description_raw: str
    kcal_estimate: int
    kcal_low: int
    kcal_high: int
    confidence: float
    source_mode: str
    parsed_items: list[dict[str, Any]]
    uncertainty_note: str
    metadata: dict[str, Any] = Field(default_factory=dict)


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
    reason_factors: list[str] = Field(default_factory=list)
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
    reason_factors: list[str] = Field(default_factory=list)


class CompensationResponse(BaseModel):
    options: list[dict[str, Any]]
    coach_message: str
    reason_factors: list[str] = Field(default_factory=list)


class PreferenceResponse(BaseModel):
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    hard_dislikes: list[str] = Field(default_factory=list)
    breakfast_habit: BreakfastHabit = "unknown"
    carb_need: CarbNeed = "flexible"
    dinner_style: DinnerStyle = "normal"
    compensation_style: CompensationStyle = "gentle"
    notes: str = ""


class OnboardingStateResponse(BaseModel):
    should_show: bool
    completed: bool
    skipped: bool
    version: str
    preferences: PreferenceResponse


class MemorySignalResponse(BaseModel):
    id: int
    pattern_type: str
    dimension: str
    canonical_label: str
    source: str
    confidence: float
    evidence_count: int
    counter_evidence_count: int
    evidence_score: float
    counter_evidence_score: float
    status: str
    sample_log_ids: list[int] = Field(default_factory=list)


class MemoryHypothesisResponse(BaseModel):
    id: int
    dimension: str
    label: str
    statement: str
    source: str
    confidence: float
    evidence_count: int
    counter_evidence_count: int
    status: str
    supporting_signal_ids: list[int] = Field(default_factory=list)


class MemoryProfileResponse(BaseModel):
    onboarding: OnboardingStateResponse
    reporting_bias: dict[str, float]
    stable_signals: list[MemorySignalResponse] = Field(default_factory=list)
    active_hypotheses: list[MemoryHypothesisResponse] = Field(default_factory=list)
    intake_packet: dict[str, Any] = Field(default_factory=dict)
    recommendation_packet: dict[str, Any] = Field(default_factory=dict)
    planning_packet: dict[str, Any] = Field(default_factory=dict)


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
