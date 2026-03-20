from __future__ import annotations

from datetime import date
import uuid

from sqlalchemy import select
from sqlalchemy.orm import Session

from ..models import Food, MealDraft, MealLog, ReportingBias, User, utcnow
from ..providers.base import EstimateResult
from ..schemas import DraftResponse, IntakeRequest, MealLogResponse
from .body_metrics import refresh_body_goal_calibration
from .confirmation import decide_confirmation, get_question_budget
from .memory import update_memory_after_log
from .storage import attachment_for_persistence
from .video_intake import video_context_from_request, video_metadata_from_context


def create_or_update_draft(db: Session, user: User, request: IntakeRequest, estimate: EstimateResult) -> MealDraft:
    event_at = request.event_at or utcnow()
    decision = decide_confirmation(
        db,
        user,
        estimate=estimate,
        mode=request.mode,
        target_date=event_at.date(),
        clarification_used=0,
    )

    draft_context = {
        "mode": request.mode,
        "event_context": request.event_context,
        "location_context": request.location_context,
        "meal_type_confidence": request.meal_type_confidence,
        "uncertainty_factors": estimate.missing_slots,
        "clarification_questions": [decision.followup_question] if decision.followup_question else [],
        "clarification_answers": [],
        "source_metadata": request.metadata,
        "clarification_budget": get_question_budget(request.mode),
        "clarification_used": 0,
        "asked_slots": [decision.clarification_kind] if decision.clarification_kind else [],
        "last_question_type": decision.clarification_kind,
        "comparison_mode_used": decision.answer_mode == "chips_first_with_text_fallback",
        "stop_reason": decision.stop_reason,
        "confirmation_mode": decision.confirmation_mode,
        "estimation_confidence": decision.estimation_confidence,
        "confirmation_calibration": decision.confirmation_calibration,
        "primary_uncertainties": decision.primary_uncertainties,
        "clarification_kind": decision.clarification_kind,
        "answer_mode": decision.answer_mode,
        "answer_options": decision.answer_options,
        "evidence_slots": estimate.evidence_slots,
        "comparison_candidates": estimate.comparison_candidates,
        "ambiguity_flags": estimate.ambiguity_flags,
        "knowledge_packet_version": estimate.knowledge_packet_version,
        "matched_knowledge_packs": estimate.matched_knowledge_packs,
    }
    draft_context.update(video_context_from_request(request))

    draft = MealDraft(
        id=str(uuid.uuid4()),
        user_id=user.id,
        meal_session_id=str(uuid.uuid4()),
        date=event_at.date(),
        event_at=event_at,
        meal_type=request.meal_type or infer_meal_type(request.text),
        status=_draft_status_from_confirmation_mode(decision.confirmation_mode),
        raw_input_text=request.text,
        source_mode=request.source_mode,
        mode=request.mode,
        attachments=[attachment_for_persistence(item) for item in request.attachments],
        parsed_items=estimate.parsed_items,
        missing_slots=estimate.missing_slots,
        followup_question=decision.followup_question,
        draft_context=draft_context,
        estimate_kcal=estimate.estimate_kcal,
        kcal_low=estimate.kcal_low,
        kcal_high=estimate.kcal_high,
        confidence=decision.estimation_confidence,
        uncertainty_note=estimate.uncertainty_note,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def update_draft_with_clarification(db: Session, draft: MealDraft, answer: str, estimate: EstimateResult) -> MealDraft:
    draft.raw_input_text = f"{draft.raw_input_text}\n補充：{answer}"
    clarification_used = draft.clarification_count + 1
    user = db.get(User, draft.user_id)
    decision = decide_confirmation(
        db,
        user,
        estimate=estimate,
        mode=draft.mode,
        target_date=draft.date,
        clarification_used=clarification_used,
    )

    draft.parsed_items = estimate.parsed_items
    draft.missing_slots = estimate.missing_slots
    draft.followup_question = decision.followup_question
    draft.estimate_kcal = estimate.estimate_kcal
    draft.kcal_low = estimate.kcal_low
    draft.kcal_high = estimate.kcal_high
    draft.confidence = decision.estimation_confidence
    draft.uncertainty_note = estimate.uncertainty_note
    draft.status = _draft_status_from_confirmation_mode(decision.confirmation_mode)
    draft.clarification_count = clarification_used

    context = draft.draft_context or {}
    questions = list(context.get("clarification_questions", []))
    answers = list(context.get("clarification_answers", []))
    if decision.followup_question:
        questions.append(decision.followup_question)
    answers.append(answer)
    context["clarification_questions"] = questions
    context["clarification_answers"] = answers
    context["uncertainty_factors"] = estimate.missing_slots
    context["clarification_used"] = clarification_used
    context["asked_slots"] = list(dict.fromkeys([*context.get("asked_slots", []), *([decision.clarification_kind] if decision.clarification_kind else [])]))
    context["last_question_type"] = decision.clarification_kind
    context["comparison_mode_used"] = context.get("comparison_mode_used", False) or decision.answer_mode == "chips_first_with_text_fallback"
    context["stop_reason"] = decision.stop_reason
    context["confirmation_mode"] = decision.confirmation_mode
    context["estimation_confidence"] = decision.estimation_confidence
    context["confirmation_calibration"] = decision.confirmation_calibration
    context["primary_uncertainties"] = decision.primary_uncertainties
    context["clarification_kind"] = decision.clarification_kind
    context["answer_mode"] = decision.answer_mode
    context["answer_options"] = decision.answer_options
    context["evidence_slots"] = estimate.evidence_slots
    context["comparison_candidates"] = estimate.comparison_candidates
    context["ambiguity_flags"] = estimate.ambiguity_flags
    context["knowledge_packet_version"] = estimate.knowledge_packet_version
    context["matched_knowledge_packs"] = estimate.matched_knowledge_packs
    draft.draft_context = context

    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def create_correction_preview(
    db: Session,
    user: User,
    target_log: MealLog,
    *,
    correction_text: str,
    estimate: EstimateResult,
    mode: str = "standard",
) -> MealDraft:
    decision = decide_confirmation(
        db,
        user,
        estimate=estimate,
        mode=mode,
        target_date=target_log.date,
        clarification_used=0,
        requested_force_confirm=True,
    )
    draft_context = {
        "mode": mode,
        "event_context": (target_log.memory_metadata or {}).get("event_context", "correction"),
        "uncertainty_factors": estimate.missing_slots,
        "clarification_questions": [],
        "clarification_answers": [correction_text],
        "clarification_budget": get_question_budget(mode),
        "clarification_used": 0,
        "asked_slots": [],
        "last_question_type": None,
        "comparison_mode_used": False,
        "stop_reason": decision.stop_reason,
        "confirmation_mode": "correction_preview",
        "estimation_confidence": decision.estimation_confidence,
        "confirmation_calibration": decision.confirmation_calibration,
        "primary_uncertainties": decision.primary_uncertainties,
        "clarification_kind": None,
        "answer_mode": None,
        "answer_options": [],
        "evidence_slots": estimate.evidence_slots,
        "comparison_candidates": estimate.comparison_candidates,
        "ambiguity_flags": estimate.ambiguity_flags,
        "knowledge_packet_version": estimate.knowledge_packet_version,
        "matched_knowledge_packs": estimate.matched_knowledge_packs,
        "correction_target_log_id": target_log.id,
        "original_kcal": target_log.kcal_estimate,
        "difference_kcal": estimate.estimate_kcal - target_log.kcal_estimate,
    }
    draft_context.update(video_metadata_from_context(target_log.memory_metadata or {}))
    draft = MealDraft(
        id=str(uuid.uuid4()),
        user_id=user.id,
        meal_session_id=target_log.meal_session_id or str(uuid.uuid4()),
        date=target_log.date,
        event_at=target_log.event_at or utcnow(),
        meal_type=target_log.meal_type,
        status="ready_to_confirm",
        raw_input_text=f"{target_log.description_raw}\n修正：{correction_text}",
        source_mode=target_log.source_mode,
        mode=mode,
        attachments=[],
        parsed_items=estimate.parsed_items,
        missing_slots=estimate.missing_slots,
        followup_question=None,
        draft_context=draft_context,
        estimate_kcal=estimate.estimate_kcal,
        kcal_low=estimate.kcal_low,
        kcal_high=estimate.kcal_high,
        confidence=decision.estimation_confidence,
        uncertainty_note=estimate.uncertainty_note,
    )
    db.add(draft)
    db.commit()
    db.refresh(draft)
    return draft


def confirm_draft(db: Session, user: User, draft: MealDraft) -> MealLog:
    draft_context = draft.draft_context or {}
    correction_target_log_id = draft_context.get("correction_target_log_id")
    if correction_target_log_id:
        target_log = db.get(MealLog, correction_target_log_id)
        if not target_log or target_log.user_id != user.id:
            raise ValueError("Correction target log not found")
        metadata = dict(target_log.memory_metadata or {})
        metadata.update(
            {
                "edited_after_confirm": True,
                "store_name": draft_context.get("store_name", metadata.get("store_name")),
                "place_id": draft_context.get("place_id", metadata.get("place_id")),
                "uncertainty_factors": draft_context.get("uncertainty_factors", draft.missing_slots),
                "clarification_questions": draft_context.get("clarification_questions", []),
                "clarification_answers": draft_context.get("clarification_answers", []),
                "confirmation_mode": "correction_preview",
                "estimation_confidence": draft_context.get("estimation_confidence", draft.confidence),
                "confirmation_calibration": draft_context.get("confirmation_calibration", 1.0),
                "primary_uncertainties": draft_context.get("primary_uncertainties", []),
                "comparison_mode_used": draft_context.get("comparison_mode_used", False),
                "stop_reason": draft_context.get("stop_reason"),
                "original_kcal": draft_context.get("original_kcal"),
                "difference_kcal": draft_context.get("difference_kcal"),
            }
        )
        metadata.update(video_metadata_from_context(draft_context))
        target_log.description_raw = draft.raw_input_text
        target_log.kcal_estimate = draft.estimate_kcal
        target_log.kcal_low = draft.kcal_low
        target_log.kcal_high = draft.kcal_high
        target_log.confidence = draft.confidence
        target_log.parsed_items = draft.parsed_items
        target_log.uncertainty_note = draft.uncertainty_note
        target_log.memory_metadata = metadata
        db.add(target_log)
        draft.status = "confirmed"
        db.add(draft)
        _upsert_food_memory(
            db,
            user,
            target_log.parsed_items,
            context=target_log.memory_metadata,
            meal_type=target_log.meal_type,
            event_at=target_log.event_at or target_log.date,
        )
        db.commit()
        db.refresh(target_log)
        update_memory_after_log(db, user, target_log)
        refresh_body_goal_calibration(db, user)
        return target_log

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
            "store_name": draft_context.get("store_name"),
            "place_id": draft_context.get("place_id"),
            "uncertainty_factors": draft_context.get("uncertainty_factors", draft.missing_slots),
            "clarification_questions": draft_context.get("clarification_questions", []),
            "clarification_answers": draft_context.get("clarification_answers", []),
            "force_confirmed": draft_context.get("confirmation_mode") == "needs_confirmation",
            "edited_after_confirm": False,
            "confirmation_mode": draft_context.get("confirmation_mode"),
            "estimation_confidence": draft_context.get("estimation_confidence", draft.confidence),
            "confirmation_calibration": draft_context.get("confirmation_calibration", 1.0),
            "primary_uncertainties": draft_context.get("primary_uncertainties", []),
            "comparison_mode_used": draft_context.get("comparison_mode_used", False),
            "stop_reason": draft_context.get("stop_reason"),
        },
    )
    log.memory_metadata.update(video_metadata_from_context(draft_context))
    db.add(log)
    draft.status = "confirmed"
    db.add(draft)
    db.flush()
    _upsert_food_memory(
        db,
        user,
        draft.parsed_items,
        context=log.memory_metadata,
        meal_type=log.meal_type,
        event_at=log.event_at or log.date,
    )
    _update_reporting_bias(db, user, draft)
    db.commit()
    db.refresh(log)
    update_memory_after_log(db, user, log)
    refresh_body_goal_calibration(db, user)
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
    metadata["knowledge_packet_version"] = estimate.knowledge_packet_version
    metadata["matched_knowledge_packs"] = estimate.matched_knowledge_packs
    log.memory_metadata = metadata
    db.add(log)
    db.commit()
    db.refresh(log)
    return log


def create_manual_log(
    db: Session,
    user: User,
    *,
    target_date: date,
    meal_type: str,
    description_raw: str,
    kcal_estimate: int,
    event_at=None,
) -> MealLog:
    log = MealLog(
        user_id=user.id,
        meal_session_id=str(uuid.uuid4()),
        date=target_date,
        event_at=event_at,
        meal_type=meal_type,
        description_raw=description_raw,
        kcal_estimate=kcal_estimate,
        kcal_low=max(round(kcal_estimate * 0.9), 0),
        kcal_high=max(round(kcal_estimate * 1.1), kcal_estimate),
        confidence=1.0,
        source_mode="manual",
        parsed_items=[{"name": description_raw, "kcal": kcal_estimate}],
        uncertainty_note="Manual journal entry.",
        memory_metadata={"manual_entry": True, "edited_after_confirm": False},
    )
    db.add(log)
    db.commit()
    db.refresh(log)
    _upsert_food_memory(
        db,
        user,
        log.parsed_items,
        context=log.memory_metadata,
        meal_type=log.meal_type,
        event_at=log.event_at or log.date,
    )
    db.commit()
    update_memory_after_log(db, user, log)
    refresh_body_goal_calibration(db, user)
    return log


def edit_log_manual(
    db: Session,
    user: User,
    log: MealLog,
    *,
    description_raw: str | None = None,
    kcal_estimate: int | None = None,
    meal_type: str | None = None,
    event_at=None,
) -> MealLog:
    if description_raw is not None:
        log.description_raw = description_raw
        if not log.parsed_items:
            log.parsed_items = [{"name": description_raw, "kcal": kcal_estimate or log.kcal_estimate}]
        else:
            parsed = list(log.parsed_items)
            first = dict(parsed[0]) if parsed and isinstance(parsed[0], dict) else {}
            first["name"] = description_raw
            if parsed:
                parsed[0] = first
            else:
                parsed = [first]
            log.parsed_items = parsed
    if kcal_estimate is not None:
        log.kcal_estimate = kcal_estimate
        log.kcal_low = max(round(kcal_estimate * 0.9), 0)
        log.kcal_high = max(round(kcal_estimate * 1.1), kcal_estimate)
        if log.parsed_items:
            parsed = list(log.parsed_items)
            first = dict(parsed[0]) if parsed and isinstance(parsed[0], dict) else {}
            first["kcal"] = kcal_estimate
            parsed[0] = first
            log.parsed_items = parsed
    if meal_type is not None:
        log.meal_type = meal_type
    if event_at is not None:
        log.event_at = event_at
        log.date = event_at.date()
    metadata = dict(log.memory_metadata or {})
    metadata["edited_after_confirm"] = True
    metadata["manual_edit"] = True
    log.memory_metadata = metadata
    log.confidence = 1.0 if log.source_mode == "manual" else log.confidence
    db.add(log)
    _upsert_food_memory(
        db,
        user,
        log.parsed_items,
        context=log.memory_metadata,
        meal_type=log.meal_type,
        event_at=log.event_at or log.date,
    )
    db.commit()
    db.refresh(log)
    update_memory_after_log(db, user, log)
    refresh_body_goal_calibration(db, user)
    return log


def delete_log(db: Session, log: MealLog) -> None:
    user = db.get(User, log.user_id)
    db.delete(log)
    db.commit()
    if user is not None:
        refresh_body_goal_calibration(db, user)


def infer_meal_type(text: str) -> str:
    lowered = text.lower()
    if any(token in lowered for token in ["breakfast", "早餐", "蛋餅", "豆漿"]):
        return "breakfast"
    if any(token in lowered for token in ["dinner", "晚餐", "宵夜"]):
        return "dinner"
    if any(token in lowered for token in ["snack", "點心", "零食", "飲料"]):
        return "snack"
    return "lunch"


def draft_to_response(draft: MealDraft) -> DraftResponse:
    metadata = draft.draft_context or {}
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
        metadata=metadata,
        confirmation_mode=metadata.get("confirmation_mode", "needs_confirmation"),
        estimation_confidence=metadata.get("estimation_confidence", draft.confidence),
        confirmation_calibration=metadata.get("confirmation_calibration", 1.0),
        primary_uncertainties=metadata.get("primary_uncertainties", []),
        clarification_kind=metadata.get("clarification_kind"),
        answer_mode=metadata.get("answer_mode"),
        answer_options=metadata.get("answer_options", []),
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


def _draft_status_from_confirmation_mode(confirmation_mode: str) -> str:
    if confirmation_mode == "needs_clarification":
        return "awaiting_clarification"
    return "ready_to_confirm"


def _upsert_food_memory(
    db: Session,
    user: User,
    parsed_items: list[dict],
    *,
    context: dict | None = None,
    meal_type: str | None = None,
    event_at=None,
) -> None:
    now = utcnow()
    store_payload = _extract_store_payload(context)
    for item in parsed_items:
        name = item.get("name")
        if not name:
            continue
        food = db.scalar(select(Food).where(Food.user_id == user.id, Food.name == name))
        kcal = int(item.get("kcal", 0))
        observed_low = max(round(kcal * 0.9), 0)
        observed_high = max(round(kcal * 1.1), kcal)
        if not food:
            food = Food(
                user_id=user.id,
                name=name,
                meal_types=item.get("meal_types", []),
                kcal_low=observed_low,
                kcal_high=observed_high,
                usage_count=0,
            )
            db.add(food)
        previous_count = int(food.usage_count or 0)
        food.usage_count = previous_count + 1
        food.last_used_at = now
        food.meal_types = sorted({*(food.meal_types or []), *(item.get("meal_types", []) or []), *([meal_type] if meal_type else [])})
        if previous_count == 0:
            food.kcal_low = observed_low
            food.kcal_high = observed_high
        else:
            weight = min(previous_count, 6)
            food.kcal_low = round(((food.kcal_low or observed_low) * weight + observed_low) / (weight + 1))
            food.kcal_high = round(((food.kcal_high or observed_high) * weight + observed_high) / (weight + 1))
        if store_payload:
            food.store_context = _merge_store_context(
                food.store_context or {},
                store_payload,
                observed_kcal=kcal,
                observed_low=observed_low,
                observed_high=observed_high,
                meal_type=meal_type,
                event_at=event_at,
            )


def _update_reporting_bias(db: Session, user: User, draft: MealDraft) -> None:
    bias = db.scalar(select(ReportingBias).where(ReportingBias.user_id == user.id))
    if not bias:
        return

    if any(token in draft.raw_input_text for token in ["隨便", "一些", "差不多", "有吃", "不多"]):
        bias.vagueness_score += 0.15
    if draft.clarification_count > 0:
        bias.missing_detail_score += 0.1
    bias.log_confidence_score = max(0.1, min(1.0, draft.confidence))
    db.add(bias)


def _extract_store_payload(context: dict | None) -> dict | None:
    if not context:
        return None
    store_name = str(context.get("store_name") or "").strip()
    place_id = str(context.get("place_id") or "").strip()
    location_context = str(context.get("location_context") or "").strip()
    if not store_name and not place_id:
        return None
    return {
        "store_name": store_name or location_context,
        "place_id": place_id or None,
        "location_context": location_context or store_name,
    }


def _merge_store_context(
    existing: dict,
    payload: dict,
    *,
    observed_kcal: int,
    observed_low: int,
    observed_high: int,
    meal_type: str | None,
    event_at=None,
) -> dict:
    key = payload.get("place_id") or payload.get("store_name") or payload.get("location_context")
    if not key:
        return existing
    store_map = dict(existing.get("by_store", {}))
    entry = dict(store_map.get(key, {}))
    previous_count = int(entry.get("count", 0))
    entry["store_name"] = payload.get("store_name") or entry.get("store_name", "")
    entry["place_id"] = payload.get("place_id") or entry.get("place_id")
    entry["location_context"] = payload.get("location_context") or entry.get("location_context", "")
    entry["count"] = previous_count + 1
    entry["last_used_at"] = utcnow().isoformat()
    entry["avg_kcal"] = round(((float(entry.get("avg_kcal", observed_kcal)) * previous_count) + observed_kcal) / max(entry["count"], 1))
    entry["kcal_low"] = observed_low
    entry["kcal_high"] = observed_high
    entry["min_kcal"] = min(int(entry.get("min_kcal", observed_kcal)), observed_kcal)
    entry["max_kcal"] = max(int(entry.get("max_kcal", observed_kcal)), observed_kcal)
    baseline = max((observed_low + observed_high) / 2, 1)
    entry["portion_ratio"] = round(observed_kcal / baseline, 3)
    meal_counts = dict(entry.get("meal_type_counts", {}))
    if meal_type:
        meal_counts[meal_type] = int(meal_counts.get(meal_type, 0)) + 1
    entry["meal_type_counts"] = meal_counts
    weekday = event_at.weekday() if event_at is not None and hasattr(event_at, "weekday") else None
    if weekday is not None:
        entry["weekday_count"] = int(entry.get("weekday_count", 0)) + (1 if weekday < 5 else 0)
        entry["weekend_count"] = int(entry.get("weekend_count", 0)) + (1 if weekday >= 5 else 0)
    store_map[str(key)] = entry
    top_key, top_entry = max(store_map.items(), key=lambda item: int(item[1].get("count", 0)))
    return {
        "by_store": store_map,
        "top_store_key": top_key,
        "top_store_name": top_entry.get("store_name", ""),
        "top_place_id": top_entry.get("place_id"),
        "top_location_context": top_entry.get("location_context", ""),
        "top_avg_kcal": top_entry.get("avg_kcal"),
        "top_portion_ratio": top_entry.get("portion_ratio"),
        "distinct_store_count": len(store_map),
        "updated_at": utcnow().isoformat(),
    }
