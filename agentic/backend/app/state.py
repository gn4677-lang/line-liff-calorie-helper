from __future__ import annotations

from datetime import date, datetime, timedelta, timezone
from types import SimpleNamespace
from typing import Any
from zoneinfo import ZoneInfo

from sqlalchemy import desc, func, select
from sqlalchemy.orm import Session

from backend.app.models import (
    ActivityAdjustment,
    ConversationTrace,
    MealDraft,
    MealLog,
    MemoryHypothesis,
    MemorySignal,
    Notification,
    SearchJob,
    User,
)
from backend.app.services.body_metrics import get_or_create_body_goal, latest_weight_value
from backend.app.services.meal_events import list_meal_events
from backend.app.services.memory import build_onboarding_state, get_or_create_preferences
from backend.app.services.planning import build_compensation_plan
from backend.app.services.proactive import (
    build_nearby_heuristics,
    count_unread_notifications,
    list_favorite_stores,
    list_golden_orders,
    list_saved_places,
)
from backend.app.services.recommendations import get_recommendations
from backend.app.services.summary import build_day_summary

from .contracts import (
    AgentIdentity,
    AgentInput,
    AgentAction,
    AgentActionKind,
    AgentState,
    ConversationState,
    ConversationTurn,
    DecisionHome,
    DeliveryAction,
    DeliveryDecision,
    DeliverySurface,
    GoalState,
    ImportanceFactor,
    MemoryFact,
    OnboardingState,
    PrimaryGoal,
    ProactiveOpportunity,
    RecommendationItem,
    RecommendationState,
    TodayState,
    WeeklyState,
)
from .config import get_settings
from .models import AgentMemoryFamilyRecord
from .store import AgenticStore


class AgentStateAssembler:
    def __init__(self, store: AgenticStore) -> None:
        self.store = store
        self.settings = get_settings()

    def build(self, db: Session, user: User, agent_input: AgentInput | None = None) -> AgentState:
        self.bootstrap_if_needed(db, user)

        preference = get_or_create_preferences(db, user)
        onboarding = build_onboarding_state(user, preference)
        goal_state = self._build_goal_state(db, user, preference)
        summary = self._safe_day_summary(db, user)
        weekly = self._build_weekly_state(db, user, summary)
        state = AgentState(
            identity=AgentIdentity(
                user_id=str(user.id),
                line_user_id=user.line_user_id,
                timezone=self.settings.timezone,
                created_at=user.created_at,
            ),
            onboarding_state=OnboardingState(
                completed=bool(onboarding.completed or user.onboarding_completed_at),
                skipped=bool(onboarding.skipped or user.onboarding_skipped_at),
                version=str(onboarding.version or user.onboarding_version or "legacy_bootstrap_v1"),
                missing_fields=self._missing_goal_fields(goal_state),
            ),
            goal_state=goal_state,
            today_state=self._build_today_state(db, user, summary),
            weekly_state=weekly,
            memory_state=self._build_memory_state(db, user, preference),
            conversation_state=self._build_conversation_state(db, user, agent_input),
            recommendation_state=self._build_recommendation_state(db, user, summary.remaining_kcal),
            delivery_state=self._build_delivery_state(db, user),
        )
        if agent_input and agent_input.text:
            state.conversation_state.active_turns.append(
                ConversationTurn(role="user", text=agent_input.text, created_at=datetime.now(timezone.utc))
            )
            state.conversation_state.active_turns = state.conversation_state.active_turns[-20:]
            state.conversation_state.last_unresolved_topic = agent_input.text[:120]
        return state

    def bootstrap_if_needed(self, db: Session, user: User) -> None:
        if self.store.has_bootstrap(db, user.id):
            return

        preference = get_or_create_preferences(db, user)
        goal_state = self._build_goal_state(db, user, preference)
        onboarding_state = OnboardingState(
            completed=True,
            skipped=False,
            version="legacy_bootstrap_v1",
            missing_fields=self._missing_goal_fields(goal_state),
        )
        memory_state = self._build_memory_state(db, user, preference)

        self.store.persist_snapshot(
            db,
            user_id=user.id,
            snapshot_type="bootstrap",
            payload={
                "goal_state": goal_state.model_dump(mode="json"),
                "onboarding_state": onboarding_state.model_dump(mode="json"),
                "memory_state": memory_state.model_dump(mode="json"),
                "bootstrap_started_at": datetime.now(timezone.utc).isoformat(),
                "bootstrap_completed_at": datetime.now(timezone.utc).isoformat(),
            },
        )
        families, evidences = self._bootstrap_memory_records(db, user, memory_state)
        self.store.replace_memory_families(db, user_id=user.id, families=families, evidences=evidences)
        db.commit()

    def refresh_memory_records(self, db: Session, user: User) -> None:
        preference = get_or_create_preferences(db, user)
        families, evidences = self._materialize_memory_records(db, user, preference)
        self.store.replace_memory_families(db, user_id=user.id, families=families, evidences=evidences)
        db.flush()

    def prune_for_context(self, state: AgentState, domain: str) -> dict[str, Any]:
        facts = sorted(
            state.memory_state.facts,
            key=lambda item: (self._source_priority(item.source), -(item.weight or 0.0)),
        )
        base: dict[str, Any] = {
            "goal_state": state.goal_state.model_dump(mode="json"),
            "conversation_state": {
                "active_turns": [turn.model_dump(mode="json") for turn in state.conversation_state.active_turns[-4:]],
                "rolling_summary": state.conversation_state.rolling_summary,
                "last_unresolved_topic": state.conversation_state.last_unresolved_topic,
                "open_threads": state.conversation_state.open_threads[:3],
            },
            "memory_state": [item.model_dump(mode="json") for item in facts[:6]],
        }
        if domain == "eat":
            base["today_state"] = {
                "remaining_kcal": state.today_state.remaining_kcal,
                "consumed_kcal": state.today_state.consumed_kcal,
            }
            base["recommendation_state"] = {
                "favorites": state.recommendation_state.favorites[:6],
                "golden_orders": state.recommendation_state.golden_orders[:6],
                "saved_places": state.recommendation_state.saved_places[:4],
                "shortlist": [item.model_dump(mode="json") for item in state.recommendation_state.shortlist[:4]],
            }
        elif domain == "progress":
            base["today_state"] = state.today_state.model_dump(mode="json")
            base["weekly_state"] = state.weekly_state.model_dump(mode="json")
        elif domain == "proactive":
            base["today_state"] = state.today_state.model_dump(mode="json")
            base["weekly_state"] = state.weekly_state.model_dump(mode="json")
            base["delivery_state"] = state.delivery_state.model_dump(mode="json")
        else:
            base["today_state"] = state.today_state.model_dump(mode="json")
            base["onboarding_state"] = state.onboarding_state.model_dump(mode="json")
        return base

    def prune_for_understanding(self, state: AgentState) -> dict[str, Any]:
        facts = sorted(
            state.memory_state.facts,
            key=lambda item: (self._source_priority(item.source), -(item.weight or 0.0)),
        )
        recent_turns = [
            {"role": turn.role, "text": turn.text[:120]}
            for turn in state.conversation_state.active_turns[-3:]
        ]
        return {
            "goal_state": {
                "primary_goal": state.goal_state.primary_goal.value if state.goal_state.primary_goal else None,
                "constraints": state.goal_state.constraints[:4],
                "strategic_context": state.goal_state.strategic_context[:3],
            },
            "today_state": {
                "remaining_kcal": state.today_state.remaining_kcal,
                "open_drafts": state.today_state.open_drafts,
                "pending_updates": state.today_state.pending_updates,
                "last_log_at": state.today_state.last_log_at.isoformat() if state.today_state.last_log_at else None,
            },
            "conversation_state": {
                "recent_turns": recent_turns,
                "last_unresolved_topic": state.conversation_state.last_unresolved_topic,
                "open_threads": state.conversation_state.open_threads[:3],
            },
            "memory_hints": [
                {
                    "key": fact.key,
                    "value": fact.value,
                    "source": fact.source,
                    "weight": round(fact.weight, 2),
                }
                for fact in facts[:4]
            ],
        }

    def opportunities_for(self, db: Session, state: AgentState) -> list[ProactiveOpportunity]:
        opportunities: list[ProactiveOpportunity] = []
        user_id = int(state.identity.user_id)
        now_local = self._local_now()
        last_log_at = self._as_local(state.today_state.last_log_at)
        has_log_today = bool(last_log_at and last_log_at.date() == now_local.date())
        if not has_log_today:
            opportunities.append(
                ProactiveOpportunity(
                    opportunity_type="no_log_day",
                    state_snapshot_ref=f"state:{state.identity.user_id}:today",
                    importance_factors=[
                        ImportanceFactor(
                            factor="friction_reduction",
                            weight=0.7,
                            reason="A quick nudge can make meal logging easier before the day gets away.",
                        ),
                        ImportanceFactor(
                            factor="time_sensitivity",
                            weight=0.66,
                            reason="The current meal window is active and the user has not logged yet today.",
                        ),
                    ],
                    eligible_surfaces=[DeliverySurface.line, DeliverySurface.liff],
                )
            )
        if state.today_state.open_drafts:
            opportunities.append(
                ProactiveOpportunity(
                    opportunity_type="open_draft_stuck",
                    state_snapshot_ref=f"state:{state.identity.user_id}:today",
                    importance_factors=[
                        ImportanceFactor(
                            factor="friction_reduction",
                            weight=0.82,
                            reason="There is an unfinished meal draft that can be closed with one confirmation.",
                        ),
                        ImportanceFactor(
                            factor="actionability",
                            weight=0.76,
                            reason="The next step is a single confirm or clarify action.",
                        ),
                    ],
                    eligible_surfaces=[DeliverySurface.line, DeliverySurface.liff],
                )
            )
        if state.weekly_state.future_events:
            opportunities.append(
                ProactiveOpportunity(
                    opportunity_type="future_meal_event",
                    state_snapshot_ref=f"state:{state.identity.user_id}:weekly",
                    importance_factors=[
                        ImportanceFactor(
                            factor="goal_impact",
                            weight=0.78,
                            reason="Upcoming meals can change the current weekly trajectory.",
                        ),
                        ImportanceFactor(
                            factor="time_sensitivity",
                            weight=0.72,
                            reason="The event is close enough to plan around now.",
                        ),
                    ],
                    eligible_surfaces=[DeliverySurface.line, DeliverySurface.liff],
                )
            )
        if state.weekly_state.drift_pct >= 0.1:
            opportunities.append(
                ProactiveOpportunity(
                    opportunity_type="weekly_drift",
                    state_snapshot_ref=f"state:{state.identity.user_id}:progress",
                    importance_factors=[
                        ImportanceFactor(
                            factor="goal_impact",
                            weight=0.8,
                            reason="Current weekly drift is materially above steady-state.",
                        ),
                        ImportanceFactor(
                            factor="actionability",
                            weight=0.74,
                            reason="A bounded recovery proposal is available.",
                        ),
                    ],
                    recommended_business_action=AgentAction(kind=AgentActionKind.propose_recovery),
                    eligible_surfaces=[DeliverySurface.line, DeliverySurface.liff],
                )
            )
        if 250 <= state.today_state.remaining_kcal <= max(state.today_state.target_kcal, 900):
            opportunities.append(
                ProactiveOpportunity(
                    opportunity_type="remaining_kcal_decision_window",
                    state_snapshot_ref=f"state:{state.identity.user_id}:eat",
                    importance_factors=[
                        ImportanceFactor(
                            factor="goal_impact",
                            weight=0.72,
                            reason="There is still enough budget to steer the next meal in the right direction.",
                        ),
                        ImportanceFactor(
                            factor="actionability",
                            weight=0.76,
                            reason="A bounded shortlist is available right now.",
                        ),
                    ],
                    recommended_business_action=AgentAction(
                        kind=AgentActionKind.recommend_food,
                        payload={"meal_type": "dinner" if now_local.hour >= 15 else "meal"},
                    ),
                    eligible_surfaces=[DeliverySurface.line, DeliverySurface.liff],
                )
            )
        if state.goal_state.primary_goal is None or not state.goal_state.constraints:
            opportunities.append(
                ProactiveOpportunity(
                    opportunity_type="goal_capture",
                    state_snapshot_ref=f"state:{state.identity.user_id}:settings",
                    importance_factors=[
                        ImportanceFactor(
                            factor="goal_impact",
                            weight=0.76,
                            reason="The assistant is missing core goal or constraint context.",
                        ),
                        ImportanceFactor(
                            factor="friction_reduction",
                            weight=0.7,
                            reason="Completing the missing goal fields improves later recommendations.",
                        ),
                    ],
                    eligible_surfaces=[DeliverySurface.liff, DeliverySurface.line],
                )
            )
        unread_async = db.scalar(
            select(func.count(Notification.id)).where(
                Notification.user_id == user_id,
                Notification.status == "unread",
            )
        )
        if unread_async:
            opportunities.append(
                ProactiveOpportunity(
                    opportunity_type="async_refinement_ready",
                    state_snapshot_ref=f"state:{state.identity.user_id}:today",
                    importance_factors=[
                        ImportanceFactor(
                            factor="actionability",
                            weight=0.73,
                            reason="There is an unread async update ready to review.",
                        ),
                        ImportanceFactor(
                            factor="novelty",
                            weight=0.68,
                            reason="This update has not been reviewed yet.",
                        ),
                    ],
                    eligible_surfaces=[DeliverySurface.liff, DeliverySurface.line],
                )
            )
        opportunities.sort(key=self._opportunity_score, reverse=True)
        return opportunities

    def default_delivery_preview(self, state: AgentState) -> DeliveryDecision:
        if state.today_state.open_drafts:
            return DeliveryDecision(
                importance=0.71,
                urgency=0.64,
                why_now="An unfinished draft can be resolved quickly right now.",
                should_send=True,
                delivery_surface=DeliverySurface.line,
                decision_home=DecisionHome.today,
                delivery_action=DeliveryAction.line_message,
            )
        return DeliveryDecision(
            importance=0.2,
            urgency=0.1,
            why_now="No interruption is necessary right now.",
            should_send=False,
            suppress_reason="no_high_value_interrupt",
            delivery_surface=DeliverySurface.none,
            decision_home=DecisionHome.none,
            delivery_action=DeliveryAction.suppress,
        )

    def _build_goal_state(self, db: Session, user: User, preference) -> GoalState:
        goal = get_or_create_body_goal(db, user)
        latest_weight, _ = latest_weight_value(db, user)
        primary_goal = PrimaryGoal.consistency
        target = {"target_weight_kg": goal.target_weight_kg}
        if goal.target_weight_kg is not None and latest_weight is not None:
            if goal.target_weight_kg < latest_weight:
                primary_goal = PrimaryGoal.weight_loss
            elif goal.target_weight_kg > latest_weight:
                primary_goal = PrimaryGoal.muscle_gain
            else:
                primary_goal = PrimaryGoal.maintenance
        constraints = list(dict.fromkeys([*(preference.hard_dislikes or []), *(preference.dislikes or [])]))
        strategic_context: list[str] = []
        summary = self._safe_day_summary(db, user)
        if summary.weekly_drift_status != "on_track":
            strategic_context.append(f"weekly_drift:{summary.weekly_drift_status}")
        if summary.remaining_kcal <= 400:
            strategic_context.append("tight_budget_window")
        goal_state = GoalState(
            primary_goal=primary_goal,
            goal_target=target,
            goal_horizon="90d",
            constraints=constraints,
            strategic_context=strategic_context,
            priority_signals=["goal_impact", "time_sensitivity", "friction_reduction"],
        )
        latest_goal_snapshot = self.store.latest_goal_state(db, user.id)
        if isinstance(latest_goal_snapshot, dict):
            if latest_goal_snapshot.get("primary_goal"):
                try:
                    goal_state.primary_goal = PrimaryGoal(str(latest_goal_snapshot["primary_goal"]))
                except ValueError:
                    pass
            if isinstance(latest_goal_snapshot.get("goal_target"), dict):
                goal_state.goal_target = latest_goal_snapshot["goal_target"]
            if latest_goal_snapshot.get("goal_horizon"):
                goal_state.goal_horizon = str(latest_goal_snapshot["goal_horizon"])
            if isinstance(latest_goal_snapshot.get("constraints"), list):
                goal_state.constraints = [str(item) for item in latest_goal_snapshot["constraints"] if str(item).strip()]
            if isinstance(latest_goal_snapshot.get("strategic_context"), list):
                goal_state.strategic_context = [str(item) for item in latest_goal_snapshot["strategic_context"] if str(item).strip()]
            if isinstance(latest_goal_snapshot.get("priority_signals"), list):
                goal_state.priority_signals = [str(item) for item in latest_goal_snapshot["priority_signals"] if str(item).strip()]
        return goal_state

    def _build_today_state(self, db: Session, user: User, summary) -> TodayState:
        open_drafts = db.scalar(
            select(func.count(MealDraft.id)).where(
                MealDraft.user_id == user.id,
                MealDraft.status.in_(("awaiting_clarification", "ready_to_confirm")),
            )
        )
        last_log = db.scalar(
            select(MealLog)
            .where(MealLog.user_id == user.id)
            .order_by(desc(MealLog.event_at), desc(MealLog.created_at))
        )
        activities = db.execute(
            select(ActivityAdjustment)
            .where(ActivityAdjustment.user_id == user.id, ActivityAdjustment.date == date.today())
            .order_by(desc(ActivityAdjustment.updated_at))
            .limit(3)
        ).scalars().all()
        return TodayState(
            target_kcal=summary.effective_target_kcal,
            consumed_kcal=summary.consumed_kcal,
            remaining_kcal=summary.remaining_kcal,
            activity_burn_kcal=summary.today_activity_burn_kcal,
            open_drafts=int(open_drafts or 0),
            pending_updates=count_unread_notifications(db, user),
            last_log_at=(last_log.event_at or last_log.created_at) if last_log else None,
            activity_notes=[item.label for item in activities],
        )

    def _build_weekly_state(self, db: Session, user: User, summary) -> WeeklyState:
        events = list_meal_events(db, user, start_date=date.today(), days=14)
        overlay_kcal = 0
        overlay = summary.recovery_overlay or {}
        today_target = ((overlay.get("overlay_allocations") or {}).get("today_target")) if isinstance(overlay, dict) else None
        if isinstance(today_target, int):
            overlay_kcal = max(summary.base_target_kcal - today_target, 0)
        drift_pct = 0.0
        if summary.weekly_target_kcal:
            drift_pct = round(summary.weekly_drift_kcal / summary.weekly_target_kcal, 4)
        return WeeklyState(
            drift_pct=drift_pct,
            drift_kcal=summary.weekly_drift_kcal,
            overlay_kcal=overlay_kcal,
            future_events=[item.model_dump(mode="json") for item in events],
        )

    def _build_memory_state(self, db: Session, user: User, preference) -> Any:
        facts: list[MemoryFact] = []
        family_rows = db.execute(
            select(AgentMemoryFamilyRecord)
            .where(AgentMemoryFamilyRecord.user_id == user.id)
            .order_by(
                AgentMemoryFamilyRecord.source,
                desc(AgentMemoryFamilyRecord.weight),
                desc(AgentMemoryFamilyRecord.updated_at),
            )
        ).scalars().all()
        if family_rows:
            for row in family_rows:
                if row.status == "archived":
                    continue
                facts.append(
                    MemoryFact(
                        key=row.dimension,
                        source=self._normalize_memory_source(row.source),
                        value=row.label,
                        weight=float(row.weight or 0.0),
                        status=self._normalize_memory_status(row.status),
                        counter_evidence_count=int(row.counter_evidence_count or 0),
                        evidence_at=row.last_evidence_at,
                    )
                )
        else:
            for value in preference.hard_dislikes or []:
                facts.append(MemoryFact(key="hard_dislike", source="user_corrected", value=value, status="stable"))
            for value in preference.dislikes or []:
                facts.append(MemoryFact(key="dislike", source="user_stated", value=value, status="stable"))
            if preference.breakfast_habit and preference.breakfast_habit != "unknown":
                facts.append(MemoryFact(key="breakfast_habit", source="user_stated", value=preference.breakfast_habit))
            if preference.carb_need:
                facts.append(MemoryFact(key="carb_need", source="user_stated", value=preference.carb_need))
            if preference.dinner_style:
                facts.append(MemoryFact(key="dinner_style", source="user_stated", value=preference.dinner_style))
            if preference.compensation_style:
                facts.append(
                    MemoryFact(key="compensation_style", source="user_stated", value=preference.compensation_style)
                )

            signals = db.execute(
                select(MemorySignal)
                .where(MemorySignal.user_id == user.id)
                .order_by(desc(MemorySignal.evidence_score), desc(MemorySignal.last_seen_at))
                .limit(12)
            ).scalars().all()
            for signal in signals:
                facts.append(
                    MemoryFact(
                        key=signal.dimension,
                        source=self._normalize_memory_source(signal.source),
                        value=signal.canonical_label or signal.value or signal.pattern_type,
                        weight=float(signal.evidence_score or signal.confidence or 0.0),
                        status=self._normalize_memory_status(signal.status),
                        counter_evidence_count=int(signal.counter_evidence_count or 0),
                        evidence_at=signal.last_seen_at,
                    )
                )

        hypotheses = db.execute(
            select(MemoryHypothesis)
            .where(MemoryHypothesis.user_id == user.id)
            .order_by(desc(MemoryHypothesis.confidence), desc(MemoryHypothesis.last_confirmed_at))
            .limit(8)
        ).scalars().all()
        for hypothesis in hypotheses:
            facts.append(
                MemoryFact(
                    key=hypothesis.dimension,
                    source="model_hypothesis",
                    value=hypothesis.label or hypothesis.statement,
                    weight=float(hypothesis.confidence or 0.0),
                    status=self._normalize_hypothesis_status(hypothesis.status),
                    counter_evidence_count=int(hypothesis.counter_evidence_count or 0),
                    evidence_at=hypothesis.last_confirmed_at,
                )
            )
        from .contracts import MemoryState

        return MemoryState(facts=facts[:20])

    def _build_conversation_state(self, db: Session, user: User, agent_input: AgentInput | None) -> ConversationState:
        window_start = datetime.now(timezone.utc) - timedelta(days=7)
        trace_rows = db.execute(
            select(ConversationTrace)
            .where(ConversationTrace.user_id == user.id, ConversationTrace.created_at >= window_start)
            .order_by(desc(ConversationTrace.created_at))
            .limit(20)
        ).scalars().all()
        active_turns: list[ConversationTurn] = []
        for row in reversed(trace_rows[:20]):
            text = (row.input_text or "").strip()
            if text:
                active_turns.append(ConversationTurn(role="user", text=text[:300], created_at=row.created_at))

        rolling_rows = db.execute(
            select(ConversationTrace)
            .where(ConversationTrace.user_id == user.id, ConversationTrace.created_at >= datetime.now(timezone.utc) - timedelta(days=30))
            .order_by(desc(ConversationTrace.created_at))
            .limit(12)
        ).scalars().all()
        rolling_summary = " | ".join(
            item.input_text.strip()[:80] for item in reversed(rolling_rows) if (item.input_text or "").strip()
        )
        latest_draft = db.scalar(
            select(MealDraft)
            .where(
                MealDraft.user_id == user.id,
                MealDraft.status.in_(("awaiting_clarification", "ready_to_confirm")),
            )
            .order_by(desc(MealDraft.updated_at))
        )
        open_threads: list[str] = []
        if latest_draft:
            open_threads.append("draft_confirmation")
        if agent_input and agent_input.postback_payload:
            open_threads.append(f"postback:{agent_input.postback_payload.action}")
        latest_notification = db.scalar(
            select(Notification)
            .where(Notification.user_id == user.id, Notification.status == "unread")
            .order_by(desc(Notification.created_at))
        )
        if latest_notification:
            open_threads.append(f"notification:{latest_notification.type}")
        last_unresolved_topic = None
        if latest_draft and latest_draft.followup_question:
            last_unresolved_topic = latest_draft.followup_question
        elif trace_rows:
            last_unresolved_topic = (trace_rows[0].input_text or "")[:120] or None
        return ConversationState(
            active_turns=active_turns[-20:],
            rolling_summary=rolling_summary[:500],
            open_threads=open_threads[:6],
            last_unresolved_topic=last_unresolved_topic,
        )

    def _build_recommendation_state(self, db: Session, user: User, remaining_kcal: int) -> RecommendationState:
        shortlist = self._safe_shortlist(db, user, remaining_kcal)
        nearby_items = self._safe_nearby_items(db, user, remaining_kcal)
        return RecommendationState(
            favorites=[item.name for item in list_favorite_stores(db, user)[:8]],
            golden_orders=[item.title for item in list_golden_orders(db, user)[:8]],
            saved_places=[item.label for item in list_saved_places(db, user)[:8]],
            shortlist=shortlist,
            nearby_items=nearby_items,
        )

    def _build_delivery_state(self, db: Session, user: User):
        from .contracts import DeliveryState

        metrics = self.store.latest_delivery_metrics(db, user.id)
        return DeliveryState(
            proactive_sent_today=int(metrics.get("proactive_sent_today") or 0),
            last_interrupt_at=metrics.get("last_interrupt_at"),
            cooldown_topics=metrics.get("cooldown_topics") or {},
        )

    def _bootstrap_memory_records(self, db: Session, user: User, memory_state) -> tuple[list[dict], list[dict]]:
        preference = get_or_create_preferences(db, user)
        return self._materialize_memory_records(db, user, preference)

    def _materialize_memory_records(self, db: Session, user: User, preference) -> tuple[list[dict], list[dict]]:
        now = datetime.now(timezone.utc)
        families: list[dict] = []
        evidences: list[dict] = []

        for fact in self._preference_memory_facts(preference):
            family_key = f"{fact.key}:{fact.value}"
            families.append(
                {
                    "family_key": family_key,
                    "dimension": fact.key,
                    "label": fact.value,
                    "source": fact.source,
                    "status": "stable",
                    "weight": 1.0,
                    "promotion_score": 1.0,
                    "evidence_count": 0,
                    "counter_evidence_count": 0,
                    "first_evidence_at": None,
                    "last_evidence_at": None,
                    "payload": {"kind": "declared_preference"},
                }
            )

        corrected_terms = {self._memory_key(value) for value in (preference.hard_dislikes or []) if self._memory_key(value)}
        existing_behavior_rows = {
            self._memory_key(f"{row.dimension}:{row.label}"): row
            for row in db.execute(
                select(AgentMemoryFamilyRecord)
                .where(
                    AgentMemoryFamilyRecord.user_id == user.id,
                    AgentMemoryFamilyRecord.source == "behavior_inferred",
                )
            ).scalars()
        }
        grouped_logs: dict[str, dict[str, Any]] = {}
        recent_logs = db.execute(
            select(MealLog)
            .where(MealLog.user_id == user.id, MealLog.date >= date.today() - timedelta(days=30))
            .order_by(desc(MealLog.created_at))
            .limit(90)
        ).scalars().all()
        for log in recent_logs:
            for item in log.parsed_items or []:
                name = str(item.get("name") or "").strip()
                if not name:
                    continue
                bucket_key = self._memory_key(f"meal_history:{name}")
                evidence_at = self._ensure_utc(log.event_at or log.created_at or now)
                grouped = grouped_logs.setdefault(
                    bucket_key,
                    {
                        "family_key": f"meal_history:{name}",
                        "dimension": "meal_history",
                        "label": name,
                        "dates": set(),
                        "sessions": set(),
                        "log_ids": set(),
                        "first_evidence_at": evidence_at,
                        "last_evidence_at": evidence_at,
                    },
                )
                grouped["dates"].add((log.event_at.date() if log.event_at else log.date).isoformat())
                grouped["sessions"].add(log.meal_session_id or f"log:{log.id}")
                grouped["log_ids"].add(str(log.id))
                grouped["first_evidence_at"] = min(grouped["first_evidence_at"], evidence_at)
                grouped["last_evidence_at"] = max(grouped["last_evidence_at"], evidence_at)
                evidences.append(
                    {
                        "family_key": grouped["family_key"],
                        "evidence_type": "meal_log",
                        "source_ref": str(log.id),
                        "payload": {
                            "meal_type": log.meal_type,
                            "date": log.date.isoformat(),
                            "kcal_estimate": log.kcal_estimate,
                        },
                        "evidence_at": evidence_at,
                    }
                )

        for bucket_key, grouped in grouped_logs.items():
            supporting_logs = len(grouped["log_ids"])
            distinct_dates = len(grouped["dates"])
            distinct_sessions = len(grouped["sessions"])
            promotion_score = self._promotion_score(
                supporting_logs=supporting_logs,
                distinct_dates=distinct_dates,
                distinct_sessions=distinct_sessions,
            )
            span_days = max(
                (grouped["last_evidence_at"].date() - grouped["first_evidence_at"].date()).days,
                0,
            )
            status = "stable" if promotion_score >= 0.9 and span_days >= 7 else "candidate"
            weight = round(max(promotion_score, 0.15), 2)
            existing = existing_behavior_rows.get(bucket_key)
            counter_evidence_count = int(existing.counter_evidence_count or 0) if existing else 0
            if self._memory_key(grouped["label"]) in corrected_terms:
                counter_evidence_count += 1
                weight = round(max(weight - 0.35, 0.05), 2)
                if weight < 0.3:
                    status = "decaying"
            families.append(
                {
                    "family_key": grouped["family_key"],
                    "dimension": grouped["dimension"],
                    "label": grouped["label"],
                    "source": "behavior_inferred",
                    "status": status,
                    "weight": weight,
                    "promotion_score": round(promotion_score, 2),
                    "evidence_count": supporting_logs,
                    "counter_evidence_count": counter_evidence_count,
                    "first_evidence_at": grouped["first_evidence_at"],
                    "last_evidence_at": grouped["last_evidence_at"],
                    "payload": {
                        "supporting_logs": supporting_logs,
                        "distinct_dates": distinct_dates,
                        "distinct_sessions": distinct_sessions,
                        "span_days": span_days,
                    },
                }
            )

        for bucket_key, row in existing_behavior_rows.items():
            if bucket_key in grouped_logs:
                continue
            last_evidence_at = self._ensure_utc(row.last_evidence_at or row.updated_at or row.created_at)
            if last_evidence_at is None:
                continue
            aged_days = max((now - last_evidence_at).days, 0)
            decay_windows = max(((aged_days - 30) // 7) + 1, 0) if aged_days >= 30 else 0
            decayed_weight = float(row.weight or 0.0) * (0.9 ** decay_windows)
            status = row.status
            if aged_days >= 30 or decayed_weight < 0.3:
                status = "decaying"
            if aged_days >= 90 and decayed_weight < 0.1:
                status = "archived"
            families.append(
                {
                    "family_key": f"{row.dimension}:{row.label}",
                    "dimension": row.dimension,
                    "label": row.label,
                    "source": row.source,
                    "status": status,
                    "weight": round(decayed_weight, 3),
                    "promotion_score": float(row.promotion_score or 0.0),
                    "evidence_count": int(row.evidence_count or 0),
                    "counter_evidence_count": int(row.counter_evidence_count or 0),
                    "first_evidence_at": row.first_evidence_at,
                    "last_evidence_at": last_evidence_at,
                    "payload": {
                        **(row.payload or {}),
                        "aged_days": aged_days,
                        "decay_windows": decay_windows,
                    },
                }
            )
        return families, evidences

    def _preference_memory_facts(self, preference) -> list[MemoryFact]:
        facts: list[MemoryFact] = []
        for value in preference.hard_dislikes or []:
            facts.append(MemoryFact(key="hard_dislike", source="user_corrected", value=value, status="stable"))
        for value in preference.dislikes or []:
            facts.append(MemoryFact(key="dislike", source="user_stated", value=value, status="stable"))
        if preference.breakfast_habit and preference.breakfast_habit != "unknown":
            facts.append(MemoryFact(key="breakfast_habit", source="user_stated", value=preference.breakfast_habit))
        if preference.carb_need:
            facts.append(MemoryFact(key="carb_need", source="user_stated", value=preference.carb_need))
        if preference.dinner_style:
            facts.append(MemoryFact(key="dinner_style", source="user_stated", value=preference.dinner_style))
        if preference.compensation_style:
            facts.append(MemoryFact(key="compensation_style", source="user_stated", value=preference.compensation_style))
        return facts

    def _promotion_score(self, *, supporting_logs: int, distinct_dates: int, distinct_sessions: int) -> float:
        score = 0.0
        if supporting_logs >= 3:
            score += 0.30
        if distinct_dates >= 2:
            score += 0.40
        if distinct_sessions >= 2:
            score += 0.20
        if supporting_logs >= 5:
            score += 0.10
        return round(score, 2)

    def _memory_key(self, value: str) -> str:
        return str(value or "").strip().lower()

    def _missing_goal_fields(self, goal_state: GoalState) -> list[str]:
        missing: list[str] = []
        if goal_state.primary_goal is None:
            missing.append("primary_goal")
        if not goal_state.constraints:
            missing.append("constraints")
        return missing

    def _source_priority(self, source: str) -> int:
        return {
            "user_corrected": 0,
            "user_stated": 1,
            "behavior_inferred": 2,
            "model_hypothesis": 3,
        }.get(source, 4)

    def _opportunity_score(self, opportunity: ProactiveOpportunity) -> float:
        if not opportunity.importance_factors:
            return 0.0
        return sum(item.weight for item in opportunity.importance_factors) / len(opportunity.importance_factors)

    def _local_now(self) -> datetime:
        return datetime.now(ZoneInfo(self.settings.timezone))

    def _as_local(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            value = value.replace(tzinfo=timezone.utc)
        return value.astimezone(ZoneInfo(self.settings.timezone))

    def _ensure_utc(self, value: datetime | None) -> datetime | None:
        if value is None:
            return None
        if value.tzinfo is None:
            return value.replace(tzinfo=timezone.utc)
        return value.astimezone(timezone.utc)

    def _normalize_memory_source(self, raw: str) -> str:
        if raw in {"user_corrected", "user_stated", "behavior_inferred", "model_hypothesis"}:
            return raw
        return "behavior_inferred"

    def _normalize_memory_status(self, raw: str) -> str:
        if raw in {"candidate", "stable", "decaying", "archived"}:
            return raw
        return "candidate"

    def _normalize_hypothesis_status(self, raw: str) -> str:
        if raw == "stale":
            return "stale"
        return "tentative"

    def _safe_day_summary(self, db: Session, user: User):
        try:
            return build_day_summary(db, user, date.today())
        except Exception:
            db.rollback()
            goal = get_or_create_body_goal(db, user)
            consumed_kcal = int(
                db.scalar(
                    select(func.coalesce(func.sum(MealLog.kcal_estimate), 0)).where(
                        MealLog.user_id == user.id,
                        MealLog.date == date.today(),
                    )
                )
                or 0
            )
            activity_burn = int(
                db.scalar(
                    select(func.coalesce(func.sum(ActivityAdjustment.estimated_burn_kcal), 0)).where(
                        ActivityAdjustment.user_id == user.id,
                        ActivityAdjustment.date == date.today(),
                    )
                )
                or 0
            )
            effective_target = int(goal.effective_target_kcal or max((goal.estimated_tdee_kcal or 2000) - (goal.default_daily_deficit_kcal or 0), 1200))
            return SimpleNamespace(
                effective_target_kcal=effective_target,
                consumed_kcal=consumed_kcal,
                remaining_kcal=max(effective_target - consumed_kcal, 0),
                today_activity_burn_kcal=activity_burn,
                weekly_drift_status="on_track",
                recovery_overlay={},
                weekly_target_kcal=effective_target * 7,
                weekly_drift_kcal=0,
                base_target_kcal=effective_target,
            )

    def _safe_shortlist(self, db: Session, user: User, remaining_kcal: int) -> list[RecommendationItem]:
        try:
            recommendations = get_recommendations(
                db,
                user,
                meal_type="dinner",
                remaining_kcal=max(remaining_kcal, 0),
                provider=None,
                memory_packet=None,
                communication_profile=None,
            )
            return [
                RecommendationItem(
                    key=item.name,
                    title=item.name,
                    reason=item.reason or "Fits the current bounded shortlist.",
                    kcal=int((item.kcal_low + item.kcal_high) / 2),
                    metadata={
                        "kcal_low": item.kcal_low,
                        "kcal_high": item.kcal_high,
                        "reason_factors": item.reason_factors,
                        "strategy_label": recommendations.strategy_label,
                    },
                )
                for item in recommendations.items[:6]
            ]
        except Exception:
            db.rollback()
            budget = max(remaining_kcal, 0)
            return [
                RecommendationItem(
                    key="bounded-light-dinner",
                    title="Light Dinner",
                    reason="Fallback shortlist based on the remaining budget.",
                    kcal=min(max(budget, 450), 650),
                    metadata={"fallback": True},
                )
            ]

    def _safe_nearby_items(self, db: Session, user: User, remaining_kcal: int) -> list[RecommendationItem]:
        try:
            nearby_payload = build_nearby_heuristics(
                db,
                user,
                location_context={"location_context": "default"},
                meal_type="dinner",
                remaining_kcal=max(remaining_kcal, 0),
            )
            return [
                RecommendationItem(
                    key=item.place_id or item.name,
                    title=item.name,
                    reason=item.reason or "Nearby bounded heuristic candidate.",
                    kcal=int((item.kcal_low + item.kcal_high) / 2),
                    distance_m=item.distance_meters,
                    metadata={
                        "kcal_low": item.kcal_low,
                        "kcal_high": item.kcal_high,
                        "source": item.source,
                        "reason_factors": item.reason_factors,
                        "external_link": item.external_link,
                    },
                )
                for item in nearby_payload.heuristic_items[:6]
            ]
        except Exception:
            db.rollback()
            return [
                RecommendationItem(
                    key="nearby-safe-default",
                    title="Nearby Balanced Option",
                    reason="Fallback nearby candidate while richer place context is unavailable.",
                    kcal=min(max(remaining_kcal, 450), 650),
                    distance_m=500,
                    metadata={"fallback": True},
                )
            ]
