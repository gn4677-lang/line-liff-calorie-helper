from __future__ import annotations

from datetime import date
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Food, MealDraft, MealLog, ReportingBias, User, utcnow
from ..providers.base import EstimateResult
from ..schemas import DraftResponse, IntakeRequest, MealLogResponse
from .memory import update_memory_after_log
from .storage import attachment_for_persistence


def create_or_update_draft(db: Session, user: User, request: IntakeRequest, estimate: EstimateResult) -> MealDraft:
    event_at = request.event_at or utcnow()
    draft_context = {
        "mode": request.mode,
        "event_context": request.event_context,
        "location_context": request.location_context,
        "meal_type_confidence": request.meal_type_confidence,
        "uncertainty_factors": estimate.missing_slots,
        "clarification_questions": [estimate.followup_question] if estimate.followup_question else [],
        "clarification_answers": [],
        "source_metadata": request.metadata,
    }
    draft = MealDraft(
        id=str(uuid.uuid4()),
        user_id=user.id,
        meal_session_id=str(uuid.uuid4()),
        date=event_at.date(),
        event_at=event_at,
        meal_type=request.meal_type or infer_meal_type(request.text),
        status=estimate.status,
        raw_input_text=request.text,
        source_mode=request.source_mode,
        mode=request.mode,
        attachments=[attachment_for_persistence(item) for item in request.attachments],
        parsed_items=estimate.parsed_items,
        missing_slots=estimate.missing_slots,
        followup_question=estimate.followup_question,
        draft_context=draft_context,
        estimate_kcal=estimate.estimate_kcal,
        kcal_low=estimate.kcal_low,
        kcal_high=estimate.kcal_high,
        confidence=estimate.confidence,
        uncertainty_note=estimate.uncertainty_note,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def update_draft_with_clarification(db: Session, draft: MealDraft, answer: str, estimate: EstimateResult) -> MealDraft:
    draft.raw_input_text = f"{draft.raw_input_text}\n補充：{answer}"
    draft.parsed_items = estimate.parsed_items
    draft.missing_slots = estimate.missing_slots
    draft.followup_question = estimate.followup_question
    draft.estimate_kcal = estimate.estimate_kcal
    draft.kcal_low = estimate.kcal_low
    draft.kcal_high = estimate.kcal_high
    draft.confidence = estimate.confidence
    draft.uncertainty_note = estimate.uncertainty_note
    draft.status = estimate.status
    draft.clarification_count += 1

    context = draft.draft_context or {}
    questions = list(context.get("clarification_questions", []))
    answers = list(context.get("clarification_answers", []))
    if estimate.followup_question:
        questions.append(estimate.followup_question)
    answers.append(answer)
    context["clarification_questions"] = questions
    context["clarification_answers"] = answers
    context["uncertainty_factors"] = estimate.missing_slots
    draft.draft_context = context

    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def confirm_draft(db: Session, user: User, draft: MealDraft) -> MealLog:
    draft_context = draft.draft_context or {}
    log = MealLog(
        user_id=user.id,
        meal_session_id=draft.meal_session_id,
        date=draft.date,
        event_at=draft.event_at,
        meal_type=draft.meal_type,
        description_raw=draft.raw_input_text,
        kcal_estimate=draft.estimate_kcal,
        kcal_low=draft.kcal_low,
        kcal_high=draft.kcal_high,
        confidence=draft.confidence,
        source_mode=draft.source_mode,
        parsed_items=draft.parsed_items,
        uncertainty_note=draft.uncertainty_note,
        memory_metadata={
            "event_context": draft_context.get("event_context", "normal"),
            "location_context": draft_context.get("location_context"),
            "uncertainty_factors": draft_context.get("uncertainty_factors", draft.missing_slots),
            "clarification_questions": draft_context.get("clarification_questions", []),
            "clarification_answers": draft_context.get("clarification_answers", []),
            "force_confirmed": draft.status == "awaiting_clarification",
            "edited_after_confirm": False,
        },
    )
    db.add(log)
    draft.status = "confirmed"
    db.add(draft)
    db.flush()
    _upsert_food_memory(db, user, draft.parsed_items)
    _update_reporting_bias(db, user, draft)
    db.commit()
    db.refresh(log)
    update_memory_after_log(db, user, log)
    return log


def edit_log(db: Session, log: MealLog, estimate: EstimateResult, description_raw: str) -> MealLog:
    log.description_raw = description_raw
    log.kcal_estimate = estimate.estimate_kcal
    log.kcal_low = estimate.kcal_low
    log.kcal_high = estimate.kcal_high
    log.confidence = estimate.confidence
    log.parsed_items = estimate.parsed_items
    log.uncertainty_note = estimate.uncertainty_note
    metadata = dict(log.memory_metadata or {})
    metadata["edited_after_confirm"] = True
    metadata["uncertainty_factors"] = estimate.missing_slots
    log.memory_metadata = metadata
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def infer_meal_type(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["breakfast", "早餐", "早上", "豆漿", "蛋餅"]):
        return "breakfast"
    if any(token in lowered for token in ["dinner", "晚餐", "晚上", "宵夜"]):
        return "dinner"
    if any(token in lowered for token in ["snack", "點心", "零食", "下午茶"]):
        return "snack"
    return "lunch"


def draft_to_response(draft: MealDraft) -> DraftResponse:
    return DraftResponse(
        id=draft.id,
        meal_session_id=draft.meal_session_id,
        date=draft.date,
        event_at=draft.event_at,
        meal_type=draft.meal_type,
        status=draft.status,
        source_mode=draft.source_mode,
        mode=draft.mode,
        parsed_items=draft.parsed_items,
        missing_slots=draft.missing_slots,
        followup_question=draft.followup_question,
        estimate_kcal=draft.estimate_kcal,
        kcal_low=draft.kcal_low,
        kcal_high=draft.kcal_high,
        confidence=draft.confidence,
        uncertainty_note=draft.uncertainty_note,
        metadata=draft.draft_context or {},
    )


def log_to_response(log: MealLog) -> MealLogResponse:
    return MealLogResponse(
        id=log.id,
        meal_session_id=log.meal_session_id,
        date=log.date,
        event_at=log.event_at,
        meal_type=log.meal_type,
        description_raw=log.description_raw,
        kcal_estimate=log.kcal_estimate,
        kcal_low=log.kcal_low,
        kcal_high=log.kcal_high,
        confidence=log.confidence,
        source_mode=log.source_mode,
        parsed_items=log.parsed_items,
        uncertainty_note=log.uncertainty_note,
        metadata=log.memory_metadata or {},
    )


def _upsert_food_memory(db: Session, user: User, parsed_items: list[dict]) -> None:
    now = utcnow()
    for item in parsed_items:
        name = item.get("name")
        if not name:
            continue
        food = db.scalar(select(Food).where(Food.user_id == user.id, Food.name == name))
        kcal = int(item.get("kcal", 0))
        if not food:
            food = Food(
                user_id=user.id,
                name=name,
                meal_types=item.get("meal_types", []),
                kcal_low=round(kcal * 0.9),
                kcal_high=round(kcal * 1.1),
                usage_count=0,
            )
            db.add(food)
        food.usage_count = (food.usage_count or 0) + 1
        food.last_used_at = now


def _update_reporting_bias(db: Session, user: User, draft: MealDraft) -> None:
    bias = db.scalar(select(ReportingBias).where(ReportingBias.user_id == user.id))
    if not bias:
        return

    if any(token in draft.raw_input_text for token in ["一點點", "隨便吃", "有吃一些", "吃不多", "大概"]):
        bias.vagueness_score += 0.15
    if draft.clarification_count > 0:
        bias.missing_detail_score += 0.1
    bias.log_confidence_score = max(0.1, min(1.0, draft.confidence))
    db.add(bias)
