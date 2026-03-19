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
    notes: Mapped[str] = mapped_column(Text, default="")


class Preference(Base):
    __tablename__ = "preferences"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), unique=True)
    likes: Mapped[list[str]] = mapped_column(JSON, default=list)
    dislikes: Mapped[list[str]] = mapped_column(JSON, default=list)
    must_have_carbs: Mapped[bool] = mapped_column(Boolean, default=False)
    meal_style: Mapped[str] = mapped_column(String(50), default="balanced")
    dinner_style: Mapped[str] = mapped_column(String(50), default="normal")
    compensation_style: Mapped[str] = mapped_column(String(50), default="gentle")
    easy_to_get_bored_with: Mapped[list[str]] = mapped_column(JSON, default=list)
    quirks: Mapped[list[str]] = mapped_column(JSON, default=list)
    common_pairings: Mapped[list[str]] = mapped_column(JSON, default=list)
    stress_eating_tendency: Mapped[str] = mapped_column(String(50), default="moderate")
    social_meal_tendency: Mapped[str] = mapped_column(String(50), default="moderate")
    notes: Mapped[str] = mapped_column(Text, default="")

    user: Mapped[User] = relationship(back_populates="preferences")


class MealDraft(Base):
    __tablename__ = "meal_drafts"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
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
    date: Mapped[date] = mapped_column(Date, index=True)
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
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, onupdate=utcnow)


class WeightLog(Base):
    __tablename__ = "weight_logs"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    weight: Mapped[float] = mapped_column(Float)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class PlanEvent(Base):
    __tablename__ = "plan_events"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    user_id: Mapped[int] = mapped_column(ForeignKey("users.id"), index=True)
    date: Mapped[date] = mapped_column(Date, index=True)
    event_type: Mapped[str] = mapped_column(String(30))
    expected_extra_kcal: Mapped[int] = mapped_column(Integer, default=0)
    notes: Mapped[str] = mapped_column(Text, default="")
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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
