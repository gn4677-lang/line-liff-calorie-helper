from __future__ import annotations

from datetime import date, datetime, timezone
import re

from fastapi import APIRouter, Depends, File, Header, HTTPException, Request, UploadFile
from sqlalchemy import select
from sqlalchemy.orm import Session

from ..config import settings
from ..database import get_db
from ..models import MealDraft, MealLog, Preference, WeightLog
from ..providers.factory import get_ai_provider
from ..schemas import (
    ClarifyRequest,
    ClientConfigResponse,
    ConfirmRequest,
    IntakeRequest,
    MeResponse,
    MealEditRequest,
    PlanRequest,
    PreferencesUpdateRequest,
    StandardResponse,
    WeightLogRequest,
)
from ..services.auth import get_or_create_user, verify_liff_id_token
from ..services.intake import confirm_draft, create_or_update_draft, draft_to_response, edit_log, infer_meal_type, log_to_response, update_draft_with_clarification
from ..services.line import fetch_line_content, reply_line_message, verify_line_signature
from ..services.planning import build_compensation_plan, build_day_plan
from ..services.recommendations import get_recommendations
from ..services.storage import attachment_for_persistence, store_attachment_bytes
from ..services.summary import build_day_summary


router = APIRouter()


async def current_user(
    db: Session = Depends(get_db),
    x_line_user_id: str | None = Header(default=None),
    x_display_name: str | None = Header(default=None),
    x_line_id_token: str | None = Header(default=None),
):
    if x_line_id_token:
        identity = await verify_liff_id_token(x_line_id_token)
        line_user_id = identity.line_user_id
        display_name = identity.display_name
    elif x_line_user_id:
        line_user_id = x_line_user_id
        display_name = x_display_name or "Demo User"
    elif settings.environment != "production":
        line_user_id = settings.default_user_id
        display_name = x_display_name or "Demo User"
    else:
        raise HTTPException(status_code=401, detail="LINE authentication is required")

    if settings.allowlist_line_user_id and line_user_id != settings.allowlist_line_user_id:
        raise HTTPException(status_code=403, detail="User is not allowlisted")
    return get_or_create_user(db, line_user_id=line_user_id, display_name=display_name)


@router.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


@router.get(f"{settings.api_prefix}/client-config", response_model=ClientConfigResponse)
def client_config() -> ClientConfigResponse:
    return ClientConfigResponse(
        liff_id=settings.liff_channel_id,
        auth_required=settings.environment == "production" and bool(settings.liff_channel_id),
    )


@router.get(f"{settings.api_prefix}/me", response_model=MeResponse)
def me(user=Depends(current_user)) -> MeResponse:
    return MeResponse(
        line_user_id=user.line_user_id,
        display_name=user.display_name,
        daily_calorie_target=user.daily_calorie_target,
        provider=settings.ai_provider,
        now=datetime.now(timezone.utc),
    )


@router.post(f"{settings.api_prefix}/intake", response_model=StandardResponse)
async def intake(request: IntakeRequest, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    provider = get_ai_provider()
    estimate = await provider.estimate_meal(
        text=request.text,
        meal_type=request.meal_type or infer_meal_type(request.text),
        mode=request.mode,
        source_mode=request.source_mode,
        clarification_count=0,
        attachments=request.attachments,
    )
    draft = create_or_update_draft(db, user, request, estimate)
    message = "先幫你抓到這樣。" if draft.status == "ready_to_confirm" else (draft.followup_question or "我還需要補一點資訊。")
    return StandardResponse(coach_message=message, draft=draft_to_response(draft))


@router.post(f"{settings.api_prefix}/intake/{{draft_id}}/clarify", response_model=StandardResponse)
async def clarify(draft_id: str, request: ClarifyRequest, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    draft = db.get(MealDraft, draft_id)
    if not draft or draft.user_id != user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    provider = get_ai_provider()
    estimate = await provider.estimate_meal(
        text=f"{draft.raw_input_text}\n補充：{request.answer}",
        meal_type=draft.meal_type,
        mode=draft.mode,
        source_mode=draft.source_mode,
        clarification_count=draft.clarification_count + 1,
        attachments=draft.attachments,
    )
    draft = update_draft_with_clarification(db, draft, request.answer, estimate)
    message = "補充後這樣比較可信。" if draft.status == "ready_to_confirm" else (draft.followup_question or "我還差一點資訊。")
    return StandardResponse(coach_message=message, draft=draft_to_response(draft))


@router.post(f"{settings.api_prefix}/intake/{{draft_id}}/confirm", response_model=StandardResponse)
def confirm(draft_id: str, request: ConfirmRequest, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    draft = db.get(MealDraft, draft_id)
    if not draft or draft.user_id != user.id:
        raise HTTPException(status_code=404, detail="Draft not found")
    if draft.status == "awaiting_clarification" and not request.force_confirm:
        raise HTTPException(status_code=409, detail="Draft still needs clarification")
    log = confirm_draft(db, user, draft)
    summary = build_day_summary(db, user, log.date)
    return StandardResponse(coach_message="已記錄這餐，今天剩餘熱量也更新了。", log=log_to_response(log), summary=summary)


@router.patch(f"{settings.api_prefix}/meal-logs/{{log_id}}", response_model=StandardResponse)
async def patch_log(log_id: int, request: MealEditRequest, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    log = db.get(MealLog, log_id)
    if not log or log.user_id != user.id:
        raise HTTPException(status_code=404, detail="Meal log not found")
    provider = get_ai_provider()
    estimate = await provider.estimate_meal(
        text=request.description_raw,
        meal_type=log.meal_type,
        mode=request.mode,
        source_mode=log.source_mode,
        clarification_count=0,
        attachments=[],
    )
    log = edit_log(db, log, estimate, request.description_raw)
    summary = build_day_summary(db, user, log.date)
    return StandardResponse(coach_message="這筆紀錄已更新。", log=log_to_response(log), summary=summary)


@router.get(f"{settings.api_prefix}/day-summary", response_model=StandardResponse)
def day_summary(target_date: date | None = None, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    summary = build_day_summary(db, user, target_date or date.today())
    return StandardResponse(coach_message="這是今天的熱量總覽。", summary=summary)


@router.post(f"{settings.api_prefix}/weights", response_model=StandardResponse)
def add_weight(request: WeightLogRequest, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    log = WeightLog(user_id=user.id, date=request.date or date.today(), weight=request.weight)
    db.add(log)
    db.commit()
    summary = build_day_summary(db, user, request.date or date.today())
    return StandardResponse(coach_message="體重已記錄。", summary=summary)


@router.get(f"{settings.api_prefix}/recommendations", response_model=StandardResponse)
def recommendations(meal_type: str | None = None, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    summary = build_day_summary(db, user, date.today())
    recs = get_recommendations(db, user, meal_type, summary.remaining_kcal)
    return StandardResponse(coach_message="先給你少量可行選項。", recommendations=recs, summary=summary)


@router.post(f"{settings.api_prefix}/plans/day", response_model=StandardResponse)
def plan_day(request: PlanRequest, user=Depends(current_user)) -> StandardResponse:
    plan = build_day_plan(user.daily_calorie_target)
    return StandardResponse(coach_message=plan.coach_message, plan=plan)


@router.post(f"{settings.api_prefix}/plans/compensation", response_model=StandardResponse)
def plan_compensation(request: PlanRequest) -> StandardResponse:
    compensation = build_compensation_plan(request.expected_extra_kcal)
    return StandardResponse(coach_message=compensation.coach_message, compensation=compensation)


@router.post(f"{settings.api_prefix}/preferences", response_model=StandardResponse)
def update_preferences(request: PreferencesUpdateRequest, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    preference = db.scalar(select(Preference).where(Preference.user_id == user.id))
    if not preference:
        preference = Preference(user_id=user.id)
    for field, value in request.model_dump(exclude_none=True).items():
        setattr(preference, field, value)
    db.add(preference)
    db.commit()
    return StandardResponse(coach_message="偏好已更新。", payload={"preferences": request.model_dump(exclude_none=True)})


@router.post(f"{settings.api_prefix}/foods/{{food_id}}/favorite", response_model=StandardResponse)
def toggle_favorite(food_id: int, db: Session = Depends(get_db), user=Depends(current_user)) -> StandardResponse:
    from ..models import Food

    food = db.get(Food, food_id)
    if not food or food.user_id != user.id:
        raise HTTPException(status_code=404, detail="Food not found")
    food.is_favorite = not food.is_favorite
    if food.usage_count >= 3 and food.is_favorite:
        food.is_golden = True
    db.add(food)
    db.commit()
    return StandardResponse(
        coach_message="已更新常用 / 黃金選項狀態。",
        payload={"food_id": food.id, "is_favorite": food.is_favorite, "is_golden": food.is_golden},
    )


@router.post(f"{settings.api_prefix}/attachments", response_model=StandardResponse)
async def upload_attachment(
    file: UploadFile = File(...),
    user=Depends(current_user),
) -> StandardResponse:
    content = await file.read()
    source_type = "image" if (file.content_type or "").startswith("image/") else "audio" if (file.content_type or "").startswith("audio/") else "file"
    attachment = store_attachment_bytes(
        content=content,
        mime_type=file.content_type,
        source_type=source_type,
        source_id=file.filename or "upload",
        user_scope=user.line_user_id,
    )
    return StandardResponse(
        coach_message="附件已上傳到 Supabase Storage",
        payload={"attachment": attachment_for_persistence(attachment), "signed_url": attachment.get("signed_url")},
    )


@router.post("/webhooks/line")
async def line_webhook(request: Request, db: Session = Depends(get_db)) -> dict[str, bool]:
    body = await request.body()
    if not verify_line_signature(body, request.headers.get("x-line-signature")):
        raise HTTPException(status_code=401, detail="Invalid LINE signature")

    payload = await request.json()
    provider = get_ai_provider()

    for event in payload.get("events", []):
        source = event.get("source", {})
        user = get_or_create_user(db, line_user_id=source.get("userId") or settings.default_user_id, display_name="LINE User")
        reply_token = event.get("replyToken")
        message = event.get("message", {})
        message_type = message.get("type")
        reply_text = "收到。"

        if message_type == "text":
            text = message.get("text", "")
            weight_match = re.search(r"(體重|weight)\s*([0-9]+(?:\.[0-9]+)?)", text, re.IGNORECASE)
            if weight_match:
                db.add(WeightLog(user_id=user.id, date=date.today(), weight=float(weight_match.group(2))))
                db.commit()
                reply_text = "體重已記錄。"
            elif "推薦" in text:
                summary = build_day_summary(db, user, date.today())
                recs = get_recommendations(db, user, None, summary.remaining_kcal)
                reply_text = "現在可行選項：\n" + "\n".join([f"- {item.name} ({item.kcal_low}-{item.kcal_high} kcal)" for item in recs.items[:3]])
            elif "剩" in text and "熱量" in text:
                summary = build_day_summary(db, user, date.today())
                reply_text = f"今天已吃 {summary.consumed_kcal} kcal，還剩 {summary.remaining_kcal} kcal。"
            else:
                estimate = await provider.estimate_meal(
                    text=text,
                    meal_type=infer_meal_type(text),
                    mode="standard",
                    source_mode="text",
                    clarification_count=0,
                    attachments=[],
                )
                draft = create_or_update_draft(db, user, IntakeRequest(text=text, meal_type=infer_meal_type(text)), estimate)
                reply_text = draft.followup_question or f"先估 {draft.estimate_kcal} kcal，可用 LIFF 或 API 確認這筆紀錄。"

        elif message_type in {"image", "audio"}:
            content, attachment = await fetch_line_content(message["id"], line_user_id=user.line_user_id)
            transcript = ""
            source_mode = "image" if message_type == "image" else "voice"
            if message_type == "audio":
                transcript = await provider.transcribe_audio(content=content, mime_type=attachment.get("mime_type"))
                attachment["transcript"] = transcript
            estimate = await provider.estimate_meal(
                text=transcript,
                meal_type="meal",
                mode="standard",
                source_mode=source_mode,
                clarification_count=0,
                attachments=[attachment],
            )
            draft = create_or_update_draft(
                db,
                user,
                IntakeRequest(text=transcript, meal_type="meal", source_mode=source_mode, attachments=[attachment]),
                estimate,
            )
            reply_text = draft.followup_question or f"先幫你粗估 {draft.estimate_kcal} kcal，請打開 LIFF 或呼叫 confirm API 確認。"

        if reply_token:
            await reply_line_message(reply_token, reply_text)

    return {"ok": True}
