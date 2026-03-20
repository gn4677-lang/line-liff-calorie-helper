from __future__ import annotations

from datetime import date, datetime, timezone
from typing import Any, Optional

from sqlalchemy import JSON, Boolean, Date, DateTime, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from .database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class User(Base):
    __tablename__ = "users"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    line_user_id: Mapped[str] = mapped_column(String(128), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(128), default="Demo User")
    daily_calorie_target: Mapped[int] = mapped_column(Integer, default=1800)
    onboarding_completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_skipped_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    onboarding_version: Mapped[str] = mapped_column(String(20), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)

    preferences: Mapped[Optional["Preference"]] = relationship(back_populates="user", uselist=False)


class Food(Base):
    __tablename__ = "foods"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_food_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(120))
    aliases: Mapped[list[str]] = mapped_column(JSON, default=list)
    category: Mapped[str] = mapped_column(String(50), default="meal")
    meal_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    kcal_low: Mapped[int] = mapped_column(Integer, default=0)
    kcal_high: Mapped[int] = mapped_column(Integer, default=0)
    satiety_level: Mapped[int] = mapped_column(Integer, default=3)
    comfort_level: Mapped[int] = mapped_column(Integer, default=3)
    convenience_level: Mapped[int] = mapped_column(Integer, default=3)
    availability_context: Mapped[list[str]] = mapped_column(JSON, default=list)
    external_links: Mapped[list[str]] = mapped_column(JSON, default=list)
    common_variants: Mapped[list[str]] = mapped_column(JSON, default=list)
    is_favorite: Mapped[bool] = mapped_column(Boolean, default=False)
    is_golden: Mapped[bool] = mapped_column(Boolean, default=False)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    store_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")


class Preference(Base):
    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    likes: Mapped[list[str]] = mapped_column(JSON, default=list)
    dislikes: Mapped[list[str]] = mapped_column(JSON, default=list)
    hard_dislikes: Mapped[list[str]] = mapped_column(JSON, default=list)
    must_have_carbs: Mapped[bool] = mapped_column(Boolean, default=False)
    breakfast_habit: Mapped[str] = mapped_column(String(50), default="unknown")
    carb_need: Mapped[str] = mapped_column(String(50), default="flexible")
    meal_style: Mapped[str] = mapped_column(String(50), default="balanced")
    dinner_style: Mapped[str] = mapped_column(String(50), default="normal")
    compensation_style: Mapped[str] = mapped_column(String(50), default="gentle")
    easy_to_get_bored_with: Mapped[list[str]] = mapped_column(JSON, default=list)
    quirks: Mapped[list[str]] = mapped_column(JSON, default=list)
    common_pairings: Mapped[list[str]] = mapped_column(JSON, default=list)
    stress_eating_tendency: Mapped[str] = mapped_column(String(50), default="moderate")
    social_meal_tendency: Mapped[str] = mapped_column(String(50), default="moderate")
    notes: Mapped[str] = mapped_column(Text, default="")
    communication_profile: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)

    user: Mapped[User] = relationship(back_populates="preferences")


class MealDraft(Base):
    __tablename__ = "meal_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    meal_session_id: Mapped[str] = mapped_column(String(36), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    event_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    meal_type: Mapped[str] = mapped_column(String(30), default="meal")
    status: Mapped[str] = mapped_column(String(40), default="draft")
    raw_input_text: Mapped[str] = mapped_column(Text, default="")
    source_mode: Mapped[str] = mapped_column(String(40), default="text")
    mode: Mapped[str] = mapped_column(String(20), default="standard")
    attachments: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    parsed_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    missing_slots: Mapped[list[str]] = mapped_column(JSON, default=list)
    followup_question: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    draft_context: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    estimate_kcal: Mapped[int] = mapped_column(Integer, default=0)
    kcal_low: Mapped[int] = mapped_column(Integer, default=0)
    kcal_high: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    uncertainty_note: Mapped[str] = mapped_column(Text, default="")
    clarification_count: Mapped[int] = mapped_column(Integer, default=0)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MealLog(Base):
    __tablename__ = "meal_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    meal_session_id: Mapped[Optional[str]] = mapped_column(String(36), index=True, nullable=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    event_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    meal_type: Mapped[str] = mapped_column(String(30), default="meal")
    description_raw: Mapped[str] = mapped_column(Text, default="")
    kcal_estimate: Mapped[int] = mapped_column(Integer, default=0)
    kcal_low: Mapped[int] = mapped_column(Integer, default=0)
    kcal_high: Mapped[int] = mapped_column(Integer, default=0)
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    source_mode: Mapped[str] = mapped_column(String(40), default="text")
    confirmed: Mapped[bool] = mapped_column(Boolean, default=True)
    parsed_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    uncertainty_note: Mapped[str] = mapped_column(Text, default="")
    memory_metadata: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WeightLog(Base):
    __tablename__ = "weight_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    weight: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class BodyGoal(Base):
    __tablename__ = "body_goals"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    target_weight_kg: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    estimated_tdee_kcal: Mapped[int] = mapped_column(Integer, default=2100)
    default_daily_deficit_kcal: Mapped[int] = mapped_column(Integer, default=300)
    calibration_confidence: Mapped[float] = mapped_column(Float, default=0.1)
    last_calibrated_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ActivityAdjustment(Base):
    __tablename__ = "activity_adjustments"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    label: Mapped[str] = mapped_column(String(160))
    estimated_burn_kcal: Mapped[int] = mapped_column(Integer, default=0)
    duration_minutes: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    raw_input_text: Mapped[str] = mapped_column(Text, default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PlanEvent(Base):
    __tablename__ = "plan_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    title: Mapped[str] = mapped_column(String(160), default="")
    expected_extra_kcal: Mapped[int] = mapped_column(Integer, default=0)
    planning_status: Mapped[str] = mapped_column(String(40), default="unplanned")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class MealEvent(Base):
    __tablename__ = "meal_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    plan_event_id: Mapped[Optional[int]] = mapped_column(ForeignKey("plan_events.id"), nullable=True, index=True)
    event_date: Mapped[date] = mapped_column(Date, index=True)
    meal_type: Mapped[str] = mapped_column(String(30), default="dinner")
    title: Mapped[str] = mapped_column(String(160), default="")
    expected_kcal: Mapped[int] = mapped_column(Integer, default=0)
    status: Mapped[str] = mapped_column(String(40), default="planned")
    source: Mapped[str] = mapped_column(String(40), default="manual")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RecommendationProfile(Base):
    __tablename__ = "recommendation_profiles"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    repeat_tolerance: Mapped[float] = mapped_column(Float, default=0.5)
    nearby_exploration_preference: Mapped[float] = mapped_column(Float, default=0.35)
    favorite_bias_strength: Mapped[float] = mapped_column(Float, default=0.6)
    distance_sensitivity: Mapped[float] = mapped_column(Float, default=0.55)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    version: Mapped[str] = mapped_column(String(20), default="v1")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class RecommendationSession(Base):
    __tablename__ = "recommendation_sessions"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    surface: Mapped[str] = mapped_column(String(40), default="eat")
    meal_type: Mapped[str] = mapped_column(String(30), default="meal")
    time_context: Mapped[str] = mapped_column(String(30), default="now")
    style_context: Mapped[str] = mapped_column(String(40), default="")
    location_context: Mapped[str] = mapped_column(String(120), default="")
    status: Mapped[str] = mapped_column(String(30), default="shown", index=True)
    shown_top_pick: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    shown_backup_picks: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    shown_scores: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    accepted_candidate: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    accepted_event_type: Mapped[str] = mapped_column(String(60), default="")
    accepted_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class ReportingBias(Base):
    __tablename__ = "reporting_bias"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True, index=True)
    underreport_score: Mapped[float] = mapped_column(Float, default=0.0)
    overreport_score: Mapped[float] = mapped_column(Float, default=0.0)
    vagueness_score: Mapped[float] = mapped_column(Float, default=0.0)
    missing_detail_score: Mapped[float] = mapped_column(Float, default=0.0)
    log_confidence_score: Mapped[float] = mapped_column(Float, default=1.0)
    notes: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class MemorySignal(Base):
    __tablename__ = "memory_signals"
    __table_args__ = (UniqueConstraint("user_id", "pattern_type", "canonical_label", name="uq_user_signal_key"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    pattern_type: Mapped[str] = mapped_column(String(60), index=True)
    dimension: Mapped[str] = mapped_column(String(60), index=True)
    canonical_label: Mapped[str] = mapped_column(String(120), index=True)
    raw_labels: Mapped[list[str]] = mapped_column(JSON, default=list)
    value: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(40), default="behavior_inferred")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    counter_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    counter_evidence_score: Mapped[float] = mapped_column(Float, default=0.0)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    sample_log_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    status: Mapped[str] = mapped_column(String(40), default="candidate")
    extra: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class MemoryHypothesis(Base):
    __tablename__ = "memory_hypotheses"
    __table_args__ = (UniqueConstraint("user_id", "label", name="uq_user_hypothesis_label"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    dimension: Mapped[str] = mapped_column(String(60), index=True)
    label: Mapped[str] = mapped_column(String(120), index=True)
    statement: Mapped[str] = mapped_column(Text, default="")
    source: Mapped[str] = mapped_column(String(40), default="behavior_inferred")
    confidence: Mapped[float] = mapped_column(Float, default=0.0)
    supporting_signal_ids: Mapped[list[int]] = mapped_column(JSON, default=list)
    evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    counter_evidence_count: Mapped[int] = mapped_column(Integer, default=0)
    last_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    status: Mapped[str] = mapped_column(String(40), default="tentative")
    extra: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class SavedPlace(Base):
    __tablename__ = "saved_places"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    label: Mapped[str] = mapped_column(String(80), index=True)
    provider: Mapped[str] = mapped_column(String(40), default="manual")
    place_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    address: Mapped[str] = mapped_column(Text, default="")
    is_default: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class PlaceCache(Base):
    __tablename__ = "place_cache"
    __table_args__ = (UniqueConstraint("provider", "place_id", name="uq_place_cache_provider_place"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    provider: Mapped[str] = mapped_column(String(40), default="google_places", index=True)
    place_id: Mapped[str] = mapped_column(String(120), index=True)
    name: Mapped[str] = mapped_column(String(160))
    lat: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    lng: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    address: Mapped[str] = mapped_column(Text, default="")
    rating: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    price_level: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    open_now: Mapped[Optional[bool]] = mapped_column(Boolean, nullable=True)
    primary_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    external_link: Mapped[str] = mapped_column(Text, default="")
    fetched_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FavoriteStore(Base):
    __tablename__ = "favorite_stores"
    __table_args__ = (UniqueConstraint("user_id", "name", name="uq_user_favorite_store_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    name: Mapped[str] = mapped_column(String(160), index=True)
    label: Mapped[str] = mapped_column(String(80), default="")
    place_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    address: Mapped[str] = mapped_column(Text, default="")
    external_link: Mapped[str] = mapped_column(Text, default="")
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    source: Mapped[str] = mapped_column(String(40), default="manual")
    extra: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class GoldenOrder(Base):
    __tablename__ = "golden_orders"
    __table_args__ = (UniqueConstraint("user_id", "title", name="uq_user_golden_order_title"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    title: Mapped[str] = mapped_column(String(160), index=True)
    store_name: Mapped[str] = mapped_column(String(160), default="")
    place_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    kcal_low: Mapped[int] = mapped_column(Integer, default=0)
    kcal_high: Mapped[int] = mapped_column(Integer, default=0)
    meal_types: Mapped[list[str]] = mapped_column(JSON, default=list)
    usage_count: Mapped[int] = mapped_column(Integer, default=0)
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    extra: Mapped[dict[str, Any]] = mapped_column("metadata", JSON, default=dict)


class SearchJob(Base):
    __tablename__ = "search_jobs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    job_type: Mapped[str] = mapped_column(String(60), index=True)
    status: Mapped[str] = mapped_column(String(40), default="pending", index=True)
    job_retry_count: Mapped[int] = mapped_column(Integer, default=0)
    last_error: Mapped[str] = mapped_column(Text, default="")
    request_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    result_payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    suggested_update: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notification_sent_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class Notification(Base):
    __tablename__ = "notifications"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    type: Mapped[str] = mapped_column(String(60), index=True)
    title: Mapped[str] = mapped_column(String(160))
    body: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(30), default="unread", index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    related_job_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    read_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class ConversationTrace(Base):
    __tablename__ = "conversation_traces"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    line_user_id: Mapped[Optional[str]] = mapped_column(String(128), nullable=True, index=True)
    surface: Mapped[str] = mapped_column(String(40), default="chat", index=True)
    thread_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    message_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    reply_to_trace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    is_system_initiated: Mapped[bool] = mapped_column(Boolean, default=False)
    task_family: Mapped[str] = mapped_column(String(60), default="unknown", index=True)
    task_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    source_mode: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    input_text: Mapped[str] = mapped_column(Text, default="")
    input_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class TaskRun(Base):
    __tablename__ = "task_runs"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    task_family: Mapped[str] = mapped_column(String(60), index=True)
    route_layer_1: Mapped[Optional[str]] = mapped_column(String(40), nullable=True)
    route_layer_2: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    provider_name: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    model_name: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    prompt_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    knowledge_packet_version: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    started_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    completed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    latency_ms: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="success", index=True)
    error_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    fallback_reason: Mapped[Optional[str]] = mapped_column(Text, nullable=True)
    result_summary: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)


class UncertaintyEvent(Base):
    __tablename__ = "uncertainty_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    task_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    task_family: Mapped[str] = mapped_column(String(60), index=True)
    estimation_confidence: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    confirmation_calibration: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    primary_uncertainties: Mapped[list[str]] = mapped_column(JSON, default=list)
    missing_slots: Mapped[list[str]] = mapped_column(JSON, default=list)
    ambiguity_flags: Mapped[list[str]] = mapped_column(JSON, default=list)
    answer_mode: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    clarification_budget: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    clarification_used: Mapped[Optional[int]] = mapped_column(Integer, nullable=True)
    stop_reason: Mapped[Optional[str]] = mapped_column(String(80), nullable=True)
    used_generic_portion_estimate: Mapped[bool] = mapped_column(Boolean, default=False)
    used_comparison_mode: Mapped[bool] = mapped_column(Boolean, default=False)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class KnowledgeEvent(Base):
    __tablename__ = "knowledge_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    task_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    question_or_query: Mapped[str] = mapped_column(Text, default="")
    knowledge_mode: Mapped[str] = mapped_column(String(40), default="local_structured", index=True)
    matched_items: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    matched_docs: Mapped[list[str]] = mapped_column(JSON, default=list)
    used_search: Mapped[bool] = mapped_column(Boolean, default=False)
    search_sources: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    grounding_type: Mapped[Optional[str]] = mapped_column(String(60), nullable=True)
    knowledge_gap_type: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ErrorEvent(Base):
    __tablename__ = "error_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    task_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    component: Mapped[str] = mapped_column(String(60), index=True)
    operation: Mapped[str] = mapped_column(String(80), index=True)
    severity: Mapped[str] = mapped_column(String(20), default="error", index=True)
    error_code: Mapped[Optional[str]] = mapped_column(String(80), nullable=True, index=True)
    exception_type: Mapped[Optional[str]] = mapped_column(String(120), nullable=True)
    message: Mapped[str] = mapped_column(Text, default="")
    retry_count: Mapped[int] = mapped_column(Integer, default=0)
    fallback_used: Mapped[bool] = mapped_column(Boolean, default=False)
    user_visible_impact: Mapped[str] = mapped_column(String(40), default="degraded")
    request_metadata: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class FeedbackEvent(Base):
    __tablename__ = "feedback_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    target_trace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    feedback_type: Mapped[str] = mapped_column(String(40), index=True)
    feedback_label: Mapped[str] = mapped_column(String(80), index=True)
    free_text: Mapped[str] = mapped_column(Text, default="")
    severity: Mapped[str] = mapped_column(String(20), default="medium", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class UnknownCaseEvent(Base):
    __tablename__ = "unknown_case_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    task_run_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    task_family: Mapped[str] = mapped_column(String(60), index=True)
    unknown_type: Mapped[str] = mapped_column(String(80), index=True)
    raw_query: Mapped[str] = mapped_column(Text, default="")
    source_hint: Mapped[str] = mapped_column(Text, default="")
    ocr_hits: Mapped[list[dict[str, Any]]] = mapped_column(JSON, default=list)
    transcript: Mapped[str] = mapped_column(Text, default="")
    current_answer: Mapped[str] = mapped_column(Text, default="")
    suggested_research_area: Mapped[str] = mapped_column(Text, default="")
    review_status: Mapped[str] = mapped_column(String(40), default="new", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutcomeEvent(Base):
    __tablename__ = "outcome_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    trace_id: Mapped[str] = mapped_column(String(36), index=True)
    user_id: Mapped[Optional[int]] = mapped_column(ForeignKey("users.id"), nullable=True, index=True)
    task_family: Mapped[str] = mapped_column(String(60), index=True)
    outcome_type: Mapped[str] = mapped_column(String(80), index=True)
    target_id: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class ObservabilityMetricSnapshot(Base):
    __tablename__ = "observability_metric_snapshots"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    metric_key: Mapped[str] = mapped_column(String(80), index=True)
    task_family: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    window_hours: Mapped[int] = mapped_column(Integer, default=168)
    value: Mapped[float] = mapped_column(Float, default=0.0)
    numerator: Mapped[float] = mapped_column(Float, default=0.0)
    denominator: Mapped[float] = mapped_column(Float, default=0.0)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    captured_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)


class AlertRule(Base):
    __tablename__ = "alert_rules"
    __table_args__ = (UniqueConstraint("name", name="uq_alert_rule_name"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    name: Mapped[str] = mapped_column(String(120), index=True)
    metric_key: Mapped[str] = mapped_column(String(80), index=True)
    comparator: Mapped[str] = mapped_column(String(10), default="gt")
    threshold: Mapped[float] = mapped_column(Float, default=0.0)
    window_hours: Mapped[int] = mapped_column(Integer, default=168)
    task_family: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning")
    min_sample_size: Mapped[int] = mapped_column(Integer, default=1)
    cooldown_minutes: Mapped[int] = mapped_column(Integer, default=360)
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    dimensions: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    notes: Mapped[str] = mapped_column(Text, default="")
    last_triggered_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class AlertEvent(Base):
    __tablename__ = "alert_events"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    rule_id: Mapped[Optional[int]] = mapped_column(ForeignKey("alert_rules.id"), nullable=True, index=True)
    metric_key: Mapped[str] = mapped_column(String(80), index=True)
    task_family: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    severity: Mapped[str] = mapped_column(String(20), default="warning", index=True)
    status: Mapped[str] = mapped_column(String(20), default="open", index=True)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text, default="")
    metric_value: Mapped[float] = mapped_column(Float, default=0.0)
    threshold: Mapped[Optional[float]] = mapped_column(Float, nullable=True)
    sample_size: Mapped[int] = mapped_column(Integer, default=0)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    first_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    occurrence_count: Mapped[int] = mapped_column(Integer, default=1)


class ReviewQueueItem(Base):
    __tablename__ = "review_queue_items"
    __table_args__ = (UniqueConstraint("source_table", "source_id", name="uq_review_queue_source"),)

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    queue_type: Mapped[str] = mapped_column(String(40), index=True)
    status: Mapped[str] = mapped_column(String(20), default="new", index=True)
    priority: Mapped[int] = mapped_column(Integer, default=2, index=True)
    task_family: Mapped[Optional[str]] = mapped_column(String(60), nullable=True, index=True)
    trace_id: Mapped[Optional[str]] = mapped_column(String(36), nullable=True, index=True)
    source_table: Mapped[str] = mapped_column(String(60), index=True)
    source_id: Mapped[str] = mapped_column(String(64), index=True)
    title: Mapped[str] = mapped_column(String(160))
    summary: Mapped[str] = mapped_column(Text, default="")
    normalized_label: Mapped[Optional[str]] = mapped_column(String(120), nullable=True, index=True)
    payload: Mapped[dict[str, Any]] = mapped_column(JSON, default=dict)
    assigned_to: Mapped[str] = mapped_column(String(120), default="")
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)
    reviewed_at: Mapped[Optional[datetime]] = mapped_column(DateTime(timezone=True), nullable=True)


class AdminSession(Base):
    __tablename__ = "admin_sessions"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True, index=True)
    label: Mapped[str] = mapped_column(String(120), default="observability-admin")
    status: Mapped[str] = mapped_column(String(20), default="active", index=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    last_seen_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), index=True)
