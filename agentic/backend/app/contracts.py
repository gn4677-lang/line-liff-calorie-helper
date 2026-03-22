from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum
from typing import Any, Literal

from pydantic import BaseModel, Field


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AgentInputSource(str, Enum):
    line_message = "line_message"
    line_postback = "line_postback"
    liff_turn = "liff_turn"
    liff_structured_action = "liff_structured_action"
    system_trigger = "system_trigger"
    async_job_result = "async_job_result"


class InputModality(str, Enum):
    text = "text"
    image = "image"
    audio = "audio"
    video = "video"
    location = "location"
    postback = "postback"
    system = "system"


class PrimaryGoal(str, Enum):
    weight_loss = "weight_loss"
    maintenance = "maintenance"
    muscle_gain = "muscle_gain"
    consistency = "consistency"
    event_preparation = "event_preparation"
    symptom_management = "symptom_management"


class DeliverySurface(str, Enum):
    line = "line"
    liff = "liff"
    none = "none"


class DecisionHome(str, Enum):
    today = "today"
    eat = "eat"
    progress = "progress"
    settings = "settings"
    none = "none"


class DeliveryAction(str, Enum):
    line_message = "line_message"
    line_teaser_to_liff = "line_teaser_to_liff"
    liff_inbox_only = "liff_inbox_only"
    suppress = "suppress"


class GuardrailPolicy(str, Enum):
    allow_without_confirmation = "allow_without_confirmation"
    require_confirmation = "require_confirmation"
    forbid = "forbid"


class AgentActionKind(str, Enum):
    mutate_meal_log = "mutate_meal_log"
    mutate_preference = "mutate_preference"
    mutate_future_event = "mutate_future_event"
    complete_onboarding = "complete_onboarding"
    record_weight = "record_weight"
    record_activity = "record_activity"
    recommend_food = "recommend_food"
    answer_grounded_qa = "answer_grounded_qa"
    propose_recovery = "propose_recovery"
    apply_suggested_update = "apply_suggested_update"
    dismiss_suggested_update = "dismiss_suggested_update"


class ToneProfile(str, Enum):
    calm_coach_partner = "calm_coach_partner"


class SubtextCategory(str, Enum):
    guilt = "guilt"
    uncertainty = "uncertainty"
    craving = "craving"
    convenience_seeking = "convenience_seeking"
    social_pressure = "social_pressure"
    goal_conflict = "goal_conflict"
    fatigue = "fatigue"
    desire_for_control = "desire_for_control"


class AttachmentRef(BaseModel):
    modality: Literal["image", "audio", "video"]
    url: str | None = None
    media_id: str | None = None
    mime_type: str | None = None
    storage_provider: str | None = None
    storage_path: str | None = None
    local_path: str | None = None
    description: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class LocationRef(BaseModel):
    lat: float
    lng: float
    label: str | None = None


class PostbackPayload(BaseModel):
    action: str
    entity_ref: str | None = None
    option_key: str | None = None
    decision_context_ref: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class SourceMetadata(BaseModel):
    user_id: str = "demo-user"
    line_user_id: str | None = None
    trace_id: str | None = None
    locale: str = "zh-TW"
    cohort: str | None = None
    core_version: str | None = None
    auth_mode: str | None = None


class AgentInput(BaseModel):
    source: AgentInputSource
    modalities: list[InputModality] = Field(default_factory=lambda: [InputModality.text])
    text: str | None = None
    attachments: list[AttachmentRef] = Field(default_factory=list)
    location: LocationRef | None = None
    postback_payload: PostbackPayload | None = None
    source_metadata: SourceMetadata = Field(default_factory=SourceMetadata)


class AgentIdentity(BaseModel):
    user_id: str
    line_user_id: str | None = None
    timezone: str = "Asia/Taipei"
    created_at: datetime = Field(default_factory=utc_now)


class OnboardingState(BaseModel):
    completed: bool = False
    skipped: bool = False
    version: str = "v1"
    missing_fields: list[str] = Field(default_factory=list)


class GoalState(BaseModel):
    primary_goal: PrimaryGoal | None = PrimaryGoal.consistency
    goal_target: dict[str, Any] = Field(default_factory=dict)
    goal_horizon: str = "90d"
    constraints: list[str] = Field(default_factory=list)
    strategic_context: list[str] = Field(default_factory=list)
    priority_signals: list[str] = Field(default_factory=list)


class ConversationTurn(BaseModel):
    role: Literal["user", "assistant"]
    text: str
    created_at: datetime = Field(default_factory=utc_now)


class ConversationState(BaseModel):
    active_turns: list[ConversationTurn] = Field(default_factory=list)
    rolling_summary: str = ""
    open_threads: list[str] = Field(default_factory=list)
    last_unresolved_topic: str | None = None


class TodayState(BaseModel):
    target_kcal: int = 0
    consumed_kcal: int = 0
    remaining_kcal: int = 0
    activity_burn_kcal: int = 0
    open_drafts: int = 0
    pending_updates: int = 0
    last_log_at: datetime | None = None
    activity_notes: list[str] = Field(default_factory=list)


class WeeklyState(BaseModel):
    drift_pct: float = 0.0
    drift_kcal: int = 0
    overlay_kcal: int = 0
    future_events: list[dict[str, Any]] = Field(default_factory=list)


class MemoryFact(BaseModel):
    key: str
    source: Literal["user_stated", "user_corrected", "behavior_inferred", "model_hypothesis"]
    value: str
    weight: float = 1.0
    status: Literal["candidate", "stable", "decaying", "archived", "tentative", "stale"] = "stable"
    counter_evidence_count: int = 0
    evidence_at: datetime | None = None


class MemoryState(BaseModel):
    facts: list[MemoryFact] = Field(default_factory=list)


class RecommendationItem(BaseModel):
    key: str
    title: str
    reason: str
    kcal: int
    distance_m: int | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class RecommendationState(BaseModel):
    favorites: list[str] = Field(default_factory=list)
    golden_orders: list[str] = Field(default_factory=list)
    saved_places: list[str] = Field(default_factory=list)
    shortlist: list[RecommendationItem] = Field(default_factory=list)
    nearby_items: list[RecommendationItem] = Field(default_factory=list)


class DeliveryState(BaseModel):
    proactive_sent_today: int = 0
    last_interrupt_at: datetime | None = None
    cooldown_topics: dict[str, str] = Field(default_factory=dict)


class AgentState(BaseModel):
    identity: AgentIdentity
    onboarding_state: OnboardingState = Field(default_factory=OnboardingState)
    goal_state: GoalState = Field(default_factory=GoalState)
    today_state: TodayState = Field(default_factory=TodayState)
    weekly_state: WeeklyState = Field(default_factory=WeeklyState)
    memory_state: MemoryState = Field(default_factory=MemoryState)
    conversation_state: ConversationState = Field(default_factory=ConversationState)
    recommendation_state: RecommendationState = Field(default_factory=RecommendationState)
    delivery_state: DeliveryState = Field(default_factory=DeliveryState)


class AgentAction(BaseModel):
    kind: AgentActionKind
    op: str | None = None
    entity_ref: str | None = None
    payload: dict[str, Any] = Field(default_factory=dict)


class AgentIntent(BaseModel):
    primary_intent: str
    secondary_intents: list[str] = Field(default_factory=list)
    subtext: list[SubtextCategory] = Field(default_factory=list)
    entities: dict[str, Any] = Field(default_factory=dict)
    urgency: float = 0.5
    confidence: float = 0.7
    needs_followup: bool = False
    suggested_surface: DeliverySurface = DeliverySurface.line


class AgentPlan(BaseModel):
    actions: list[AgentAction] = Field(default_factory=list)
    requires_confirmation: bool = False
    decision_home: DecisionHome = DecisionHome.today
    delivery_surface: DeliverySurface = DeliverySurface.line
    context_used: list[str] = Field(default_factory=list)
    goal_alignment: dict[str, float] = Field(default_factory=dict)
    policy_reasons: list[str] = Field(default_factory=list)


class HeroCard(BaseModel):
    title: str
    body: str
    cta_label: str | None = None


class AgentResponse(BaseModel):
    message_text: str
    followup_question: str | None = None
    hero_card: HeroCard | None = None
    quick_replies: list[str] = Field(default_factory=list)
    deep_link: str | None = None
    tone_profile: ToneProfile = ToneProfile.calm_coach_partner


class ImportanceFactor(BaseModel):
    factor: str
    weight: float
    reason: str


class ProactiveOpportunity(BaseModel):
    opportunity_type: str
    state_snapshot_ref: str
    importance_factors: list[ImportanceFactor] = Field(default_factory=list)
    recommended_business_action: AgentAction | None = None
    eligible_surfaces: list[DeliverySurface] = Field(default_factory=lambda: [DeliverySurface.line, DeliverySurface.liff])


class DeliveryDecision(BaseModel):
    importance: float
    urgency: float
    why_now: str
    should_send: bool
    suppress_reason: str | None = None
    delivery_surface: DeliverySurface = DeliverySurface.none
    decision_home: DecisionHome = DecisionHome.none
    delivery_action: DeliveryAction = DeliveryAction.suppress
    hero_candidate_key: str | None = None


class PersistedEffect(BaseModel):
    entity_type: str
    entity_id: str
    op: str
    guardrail_source: GuardrailPolicy
    source_action: AgentActionKind
    before_ref: str | None = None
    after_ref: str | None = None
    confirmed_by_user: bool = False
    payload: dict[str, Any] = Field(default_factory=dict)


class ExecutionRecord(BaseModel):
    action: AgentAction
    guardrail_policy: GuardrailPolicy
    status: Literal["executed", "pending_confirmation", "blocked"]
    summary: str
    artifact: dict[str, Any] = Field(default_factory=dict)


class InteractionTurn(BaseModel):
    input: AgentInput
    understanding: AgentIntent
    plan: AgentPlan
    executed_actions: list[ExecutionRecord]
    response: AgentResponse
    persisted_effects: list[PersistedEffect]


class AgentTurnResult(BaseModel):
    state: AgentState
    turn: InteractionTurn
    opportunities: list[ProactiveOpportunity] = Field(default_factory=list)
    delivery: DeliveryDecision | None = None
    telemetry: dict[str, Any] = Field(default_factory=dict)


class DecisionMutation(BaseModel):
    action: Literal["apply", "dismiss"]
    entity_ref: str
    option_key: str | None = None
    decision_context_ref: str | None = None
    confirmed: bool = True


class PreferencesMutation(BaseModel):
    updates: dict[str, Any] = Field(default_factory=dict)
    confirmed: bool = True


class OnboardingMutation(BaseModel):
    primary_goal: PrimaryGoal
    constraints: list[str] = Field(default_factory=list)
    confirmed: bool = True


class HomePayload(BaseModel):
    persona: ToneProfile = ToneProfile.calm_coach_partner
    title: str
    state: AgentState
    highlights: list[str] = Field(default_factory=list)
    opportunities: list[ProactiveOpportunity] = Field(default_factory=list)
    delivery_preview: DeliveryDecision | None = None
    cohort: str = "canary"
    core_version: str = "agentic"
    metadata: dict[str, Any] = Field(default_factory=dict)
