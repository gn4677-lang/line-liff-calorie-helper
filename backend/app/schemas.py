from __future__ import annotations

from datetime import date as DateValue, datetime
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


class VideoIntakeRequest(BaseModel):
    attachment: dict[str, Any]
    text: str = ""
    meal_type: Optional[str] = None
    mode: MealMode = "standard"
    event_at: Optional[datetime] = None
    event_context: str = "normal"
    location_context: Optional[str] = None
    metadata: dict[str, Any] = Field(default_factory=dict)
    notify_on_refinement: bool = False


class WeightLogRequest(BaseModel):
    weight: float
    date: Optional[DateValue] = None


class BodyGoalUpdateRequest(BaseModel):
    target_weight_kg: Optional[float] = None
    estimated_tdee_kcal: Optional[int] = None
    default_daily_deficit_kcal: Optional[int] = None


class ActivityAdjustmentRequest(BaseModel):
    date: Optional[DateValue] = None
    label: str
    estimated_burn_kcal: int
    duration_minutes: Optional[int] = None
    source: str = "manual"
    raw_input_text: str = ""
    notes: str = ""


class ActivityAdjustmentUpdateRequest(BaseModel):
    date: Optional[DateValue] = None
    label: Optional[str] = None
    estimated_burn_kcal: Optional[int] = None
    duration_minutes: Optional[int] = None
    notes: Optional[str] = None


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
    communication_profile: Optional[dict[str, Any]] = None


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
    apply_overlay: bool = False


class NutritionQARequest(BaseModel):
    question: str
    allow_search: bool = True
    source_hint: Optional[str] = None


class LocationResolveRequest(BaseModel):
    mode: Literal["geolocation", "manual", "saved_place"] = "manual"
    lat: Optional[float] = None
    lng: Optional[float] = None
    query: Optional[str] = None
    saved_place_id: Optional[int] = None
    label: Optional[str] = None


class NearbyRecommendationRequest(BaseModel):
    meal_type: Optional[str] = None
    remaining_kcal: Optional[int] = None
    mode: Literal["geolocation", "manual", "saved_place"] = "manual"
    lat: Optional[float] = None
    lng: Optional[float] = None
    query: Optional[str] = None
    saved_place_id: Optional[int] = None
    notify_on_complete: bool = False


class SavedPlaceRequest(BaseModel):
    label: str
    provider: str = "manual"
    place_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: str = ""
    is_default: bool = False


class FavoriteStoreRequest(BaseModel):
    name: str
    label: Optional[str] = None
    place_id: Optional[str] = None
    address: str = ""
    external_link: str = ""
    kcal_low: Optional[int] = None
    kcal_high: Optional[int] = None
    meal_types: list[str] = Field(default_factory=list)
    mark_golden: bool = False


class MealEventRequest(BaseModel):
    event_date: DateValue
    meal_type: Literal["breakfast", "lunch", "dinner", "snack"] = "dinner"
    title: str
    expected_kcal: Optional[int] = None
    notes: str = ""
    source: str = "manual"


class MealEditRequest(BaseModel):
    description_raw: Optional[str] = None
    kcal_estimate: Optional[int] = None
    meal_type: Optional[str] = None
    event_at: Optional[datetime] = None


class ManualMealLogRequest(BaseModel):
    date: Optional[DateValue] = None
    meal_type: str
    description_raw: str
    kcal_estimate: int
    event_at: Optional[datetime] = None


class EatFeedRequest(BaseModel):
    meal_type: str = "lunch"
    time_context: Literal["now", "later"] = "now"
    style_context: str = ""
    location_mode: Literal["none", "geolocation", "manual", "saved_place"] = "none"
    saved_place_id: Optional[int] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    query: Optional[str] = None
    selected_chip_id: Optional[str] = None
    explore_mode: bool = False


class DraftResponse(BaseModel):
    id: str
    meal_session_id: Optional[str] = None
    date: DateValue
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
    confirmation_mode: str = "needs_confirmation"
    estimation_confidence: float = 0.0
    confirmation_calibration: float = 1.0
    primary_uncertainties: list[str] = Field(default_factory=list)
    clarification_kind: Optional[str] = None
    answer_mode: Optional[str] = None
    answer_options: list[str] = Field(default_factory=list)


class MealLogResponse(BaseModel):
    id: int
    meal_session_id: Optional[str] = None
    date: DateValue
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
    date: DateValue
    target_kcal: int
    base_target_kcal: int = 0
    effective_target_kcal: int = 0
    consumed_kcal: int
    remaining_kcal: int
    today_activity_burn_kcal: int = 0
    meal_subtotals: dict[str, int] = Field(default_factory=dict)
    meal_counts: dict[str, int] = Field(default_factory=dict)
    logs: list[MealLogResponse]
    latest_weight: Optional[float] = None
    has_today_weight: bool = False
    target_weight_kg: Optional[float] = None
    delta_to_goal_kg: Optional[float] = None
    seven_day_average_weight: Optional[float]
    fourteen_day_direction: str
    target_adjustment_hint: str
    weekly_target_kcal: int = 0
    weekly_consumed_kcal: int = 0
    weekly_remaining_kcal: int = 0
    weekly_drift_kcal: int = 0
    weekly_drift_status: str = "on_track"
    should_offer_weekly_recovery: bool = False
    recovery_overlay: Optional[dict[str, Any]] = None
    pending_async_updates_count: int = 0


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
    location_context_used: Optional[str] = None
    saved_place_options: list[dict[str, Any]] = Field(default_factory=list)


class NearbyRecommendationItem(BaseModel):
    name: str
    place_id: Optional[str] = None
    distance_meters: Optional[int] = None
    travel_minutes: Optional[int] = None
    open_now: Optional[bool] = None
    kcal_low: int = 0
    kcal_high: int = 0
    reason: str = ""
    reason_factors: list[str] = Field(default_factory=list)
    external_link: str = ""
    source: str = "memory"


class NearbyRecommendationsResponse(BaseModel):
    location_context_used: str
    heuristic_items: list[NearbyRecommendationItem] = Field(default_factory=list)
    search_job_id: Optional[str] = None
    saved_place_options: list[dict[str, Any]] = Field(default_factory=list)
    favorite_stores: list[dict[str, Any]] = Field(default_factory=list)


class SearchJobResponse(BaseModel):
    id: str
    job_type: str
    status: str
    job_retry_count: int = 0
    last_error: str = ""
    result_payload: dict[str, Any] = Field(default_factory=dict)
    suggested_update: dict[str, Any] = Field(default_factory=dict)
    notification_ready: bool = False


class NotificationItemResponse(BaseModel):
    id: str
    type: str
    title: str
    body: str
    status: str
    payload: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime


class SavedPlaceResponse(BaseModel):
    id: int
    label: str
    provider: str
    place_id: Optional[str] = None
    lat: Optional[float] = None
    lng: Optional[float] = None
    address: str = ""
    is_default: bool = False


class FavoriteStoreResponse(BaseModel):
    id: int
    name: str
    label: str = ""
    place_id: Optional[str] = None
    address: str = ""
    external_link: str = ""
    usage_count: int = 0
    golden_order_id: Optional[int] = None


class GoldenOrderResponse(BaseModel):
    id: int
    title: str
    store_name: str = ""
    place_id: Optional[str] = None
    kcal_low: int
    kcal_high: int
    meal_types: list[str] = Field(default_factory=list)


class PlanEventResponse(BaseModel):
    id: int
    date: DateValue
    event_type: str
    title: str = ""
    expected_extra_kcal: int = 0
    planning_status: str = "unplanned"
    notes_summary: str = ""


class MealEventResponse(BaseModel):
    id: int
    plan_event_id: Optional[int] = None
    event_date: DateValue
    meal_type: str
    title: str
    expected_kcal: int = 0
    status: str = "planned"
    source: str = "manual"
    notes: str = ""


class DayPlanResponse(BaseModel):
    target_kcal: int
    allocations: dict[str, int]
    coach_message: str
    reason_factors: list[str] = Field(default_factory=list)


class CompensationResponse(BaseModel):
    options: list[dict[str, Any]]
    coach_message: str
    reason_factors: list[str] = Field(default_factory=list)


class BodyGoalResponse(BaseModel):
    target_weight_kg: Optional[float] = None
    estimated_tdee_kcal: int
    default_daily_deficit_kcal: int
    base_target_kcal: int
    calibration_confidence: float
    latest_weight: Optional[float] = None
    delta_to_goal_kg: Optional[float] = None
    last_calibrated_at: Optional[datetime] = None


class ActivityAdjustmentResponse(BaseModel):
    id: int
    date: DateValue
    label: str
    estimated_burn_kcal: int
    duration_minutes: Optional[int] = None
    source: str
    raw_input_text: str = ""
    notes: str = ""


class ProgressSeriesPoint(BaseModel):
    date: DateValue
    value: float | int
    target: Optional[float | int] = None


class ProgressSeriesResponse(BaseModel):
    range: str
    weight_points: list[ProgressSeriesPoint] = Field(default_factory=list)
    calorie_points: list[ProgressSeriesPoint] = Field(default_factory=list)
    activity_points: list[ProgressSeriesPoint] = Field(default_factory=list)


class LogbookRangeDayResponse(BaseModel):
    date: DateValue
    consumed_kcal: int
    target_kcal: int
    meal_count: int


class EatFeedCandidateResponse(BaseModel):
    candidate_id: str
    title: str
    store_name: str = ""
    meal_types: list[str] = Field(default_factory=list)
    kcal_low: int = 0
    kcal_high: int = 0
    distance_meters: Optional[int] = None
    travel_minutes: Optional[int] = None
    open_now: Optional[bool] = None
    source_type: str
    reason_factors: list[str] = Field(default_factory=list)
    external_link: str = ""


class EatFeedSectionResponse(BaseModel):
    key: str
    title: str
    items: list[EatFeedCandidateResponse] = Field(default_factory=list)


class SmartChipResponse(BaseModel):
    id: str
    label: str
    intent_kind: str
    supported_candidate_count: int = 0


class EatFeedResponse(BaseModel):
    session_id: str
    remaining_kcal: int
    top_pick: Optional[EatFeedCandidateResponse] = None
    backup_picks: list[EatFeedCandidateResponse] = Field(default_factory=list)
    exploration_sections: list[EatFeedSectionResponse] = Field(default_factory=list)
    location_context_used: Optional[str] = None
    smart_chips: list[SmartChipResponse] = Field(default_factory=list)
    hero_reason: str = ""
    more_results_available: bool = False


class JournalAddSuggestionsResponse(BaseModel):
    recent_items: list[dict[str, Any]] = Field(default_factory=list)
    frequent_items: list[dict[str, Any]] = Field(default_factory=list)
    last_used_at: str = ""


class PreferenceResponse(BaseModel):
    likes: list[str] = Field(default_factory=list)
    dislikes: list[str] = Field(default_factory=list)
    hard_dislikes: list[str] = Field(default_factory=list)
    breakfast_habit: BreakfastHabit = "unknown"
    carb_need: CarbNeed = "flexible"
    dinner_style: DinnerStyle = "normal"
    compensation_style: CompensationStyle = "gentle"
    notes: str = ""
    communication_profile: dict[str, Any] = Field(default_factory=dict)


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
    app_session_token: Optional[str] = None
    app_session_expires_at: Optional[datetime] = None
    auth_mode: str = "unknown"


class ClientConfigResponse(BaseModel):
    liff_id: Optional[str] = None
    auth_required: bool


class AdminLoginRequest(BaseModel):
    passcode: str
    label: str = "observability-admin"


class AdminSessionResponse(BaseModel):
    token: str
    label: str
    status: str
    expires_at: datetime


class AdminMeResponse(BaseModel):
    label: str
    status: str
    expires_at: datetime
    last_seen_at: datetime


class StandardResponse(BaseModel):
    coach_message: str
    draft: Optional[DraftResponse] = None
    summary: Optional[DaySummaryResponse] = None
    log: Optional[MealLogResponse] = None
    recommendations: Optional[RecommendationsResponse] = None
    plan: Optional[DayPlanResponse] = None
    compensation: Optional[CompensationResponse] = None
    payload: dict[str, Any] = Field(default_factory=dict)


class ObservabilityMetricResponse(BaseModel):
    metric_key: str
    task_family: Optional[str] = None
    window_hours: int
    value: float
    numerator: float = 0.0
    denominator: float = 0.0
    sample_size: int = 0
    dimensions: dict[str, Any] = Field(default_factory=dict)


class AlertRuleRequest(BaseModel):
    name: str
    metric_key: str
    comparator: Literal["gt", "gte", "lt", "lte"] = "gt"
    threshold: float
    window_hours: int = 168
    task_family: Optional[str] = None
    severity: Literal["warning", "high", "critical"] = "warning"
    min_sample_size: int = 1
    cooldown_minutes: int = 360
    status: Literal["active", "paused"] = "active"
    dimensions: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""


class AlertRuleResponse(BaseModel):
    id: int
    name: str
    metric_key: str
    comparator: str
    threshold: float
    window_hours: int
    task_family: Optional[str] = None
    severity: str
    min_sample_size: int
    cooldown_minutes: int
    status: str
    dimensions: dict[str, Any] = Field(default_factory=dict)
    notes: str = ""
    last_triggered_at: Optional[datetime] = None


class AlertEventResponse(BaseModel):
    id: str
    rule_id: Optional[int] = None
    metric_key: str
    task_family: Optional[str] = None
    severity: str
    status: str
    title: str
    summary: str
    metric_value: float
    threshold: Optional[float] = None
    sample_size: int = 0
    payload: dict[str, Any] = Field(default_factory=dict)
    first_seen_at: datetime
    last_seen_at: datetime
    occurrence_count: int = 1


class AlertStatusUpdateRequest(BaseModel):
    status: Literal["open", "acknowledged", "resolved"] = "acknowledged"


class ReviewQueueItemResponse(BaseModel):
    id: int
    queue_type: str
    status: str
    priority: int
    task_family: Optional[str] = None
    trace_id: Optional[str] = None
    source_table: str
    source_id: str
    title: str
    summary: str
    normalized_label: Optional[str] = None
    payload: dict[str, Any] = Field(default_factory=dict)
    assigned_to: str = ""
    notes: str = ""
    created_at: datetime
    updated_at: datetime
    reviewed_at: Optional[datetime] = None


class ReviewQueueUpdateRequest(BaseModel):
    status: Literal["new", "triaged", "in_progress", "resolved", "ignored"]
    notes: Optional[str] = None
    assigned_to: Optional[str] = None


class ObservabilitySummaryCardResponse(BaseModel):
    key: str
    title: str
    value: float | int | str
    status: Literal["healthy", "warning", "critical", "neutral"] = "neutral"
    subtitle: str = ""


class ObservabilityTaskHealthResponse(BaseModel):
    task_family: str
    sample_size: int = 0
    success_rate: float = 0.0
    fallback_rate: float = 0.0
    unknown_case_rate: float = 0.0
    dissatisfaction_rate: float = 0.0


class ObservabilityTrendPointResponse(BaseModel):
    date: str
    value: float = 0.0


class ObservabilityLabeledCountResponse(BaseModel):
    label: str
    count: int


class ObservabilityComponentErrorResponse(BaseModel):
    component: str
    total_count: int
    critical_count: int = 0
    degraded_count: int = 0
    last_seen_at: Optional[datetime] = None


class ObservabilityDashboardResponse(BaseModel):
    refreshed_at: datetime
    window_hours: int
    trend_days: int
    summary_cards: list[ObservabilitySummaryCardResponse] = Field(default_factory=list)
    task_health: list[ObservabilityTaskHealthResponse] = Field(default_factory=list)
    quality_trends: dict[str, list[ObservabilityTrendPointResponse]] = Field(default_factory=dict)
    usage_panels: dict[str, Any] = Field(default_factory=dict)
    product_panels: dict[str, Any] = Field(default_factory=dict)
    memory_panels: dict[str, Any] = Field(default_factory=dict)
    operational_panels: dict[str, Any] = Field(default_factory=dict)
    eval_panels: dict[str, Any] = Field(default_factory=dict)
    attention_panels: dict[str, Any] = Field(default_factory=dict)


class TraceListItemResponse(BaseModel):
    trace_id: str
    created_at: datetime
    task_family: str
    surface: str
    source_mode: Optional[str] = None
    input_preview: str = ""
    route_status: str = "unknown"
    provider_name: Optional[str] = None
    model_name: Optional[str] = None
    route_policy: Optional[str] = None
    route_target: Optional[str] = None
    llm_cache: Optional[str] = None
    latency_ms: Optional[int] = None
    has_error: bool = False
    has_feedback: bool = False
    has_unknown_case: bool = False
    outcome_summary: str = ""


class TraceDetailResponse(BaseModel):
    trace: dict[str, Any]
    task_runs: list[dict[str, Any]] = Field(default_factory=list)
    uncertainty_events: list[dict[str, Any]] = Field(default_factory=list)
    knowledge_events: list[dict[str, Any]] = Field(default_factory=list)
    error_events: list[dict[str, Any]] = Field(default_factory=list)
    feedback_events: list[dict[str, Any]] = Field(default_factory=list)
    unknown_case_events: list[dict[str, Any]] = Field(default_factory=list)
    outcome_events: list[dict[str, Any]] = Field(default_factory=list)
    related_review_items: list[ReviewQueueItemResponse] = Field(default_factory=list)
    related_alerts: list[AlertEventResponse] = Field(default_factory=list)
