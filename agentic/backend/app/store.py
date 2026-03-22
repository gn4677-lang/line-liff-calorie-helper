from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from sqlalchemy import desc, select
from sqlalchemy.orm import Session

from .contracts import AgentState, AgentTurnResult, DeliveryDecision, ProactiveOpportunity
from .models import (
    AgentDeliveryRecord,
    AgentEvalLabelRecord,
    AgentMemoryEvidenceRecord,
    AgentMemoryFamilyRecord,
    AgentOpportunityRecord,
    AgentStateSnapshotRecord,
    AgentTurnRecord,
    ShadowEffectRecord,
)


@dataclass(slots=True)
class AgenticStore:
    def persist_turn(
        self,
        db: Session,
        result: AgentTurnResult,
        *,
        cohort: str,
        core_version: str,
    ) -> str:
        telemetry = result.telemetry or {}
        trace_id = str(
            result.turn.input.source_metadata.trace_id
            or telemetry.get("trace_id")
            or f"agentic-{datetime.now(timezone.utc).timestamp()}"
        )
        user_id = self._coerce_user_id(result.state.identity.user_id)
        record = AgentTurnRecord(
            trace_id=trace_id,
            user_id=user_id,
            line_user_id=result.state.identity.line_user_id,
            source=result.turn.input.source.value,
            cohort=cohort,
            core_version=core_version,
            provider_fallback_chain=list(telemetry.get("provider_fallback_chain", [])),
            prompt_version=str(telemetry.get("prompt_version") or ""),
            payload=result.model_dump(mode="json"),
        )
        db.add(record)
        db.flush()
        self.persist_snapshot(
            db,
            user_id=user_id,
            snapshot_type="post_turn",
            payload=result.state.model_dump(mode="json"),
            trace_id=trace_id,
        )
        for effect in result.turn.persisted_effects:
            self.persist_shadow_effect(
                db,
                user_id=user_id,
                entity_type=effect.entity_type,
                entity_id=effect.entity_id,
                op=effect.op,
                payload=effect.model_dump(mode="json"),
                trace_id=trace_id,
            )
        for opportunity in result.opportunities:
            self.record_opportunity(db, opportunity, user_id=user_id, trace_id=trace_id)
        if result.delivery is not None:
            topic = ""
            if result.opportunities:
                topic = result.opportunities[0].opportunity_type
            self.record_delivery(db, result.delivery, user_id=user_id, trace_id=trace_id, topic=topic)
        db.commit()
        return trace_id

    def persist_snapshot(
        self,
        db: Session,
        *,
        user_id: int | None,
        snapshot_type: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> None:
        db.add(
            AgentStateSnapshotRecord(
                trace_id=trace_id,
                user_id=user_id,
                snapshot_type=snapshot_type,
                payload=payload,
            )
        )

    def persist_shadow_effect(
        self,
        db: Session,
        *,
        user_id: int | None,
        entity_type: str,
        entity_id: str,
        op: str,
        payload: dict,
        trace_id: str | None = None,
    ) -> None:
        db.add(
            ShadowEffectRecord(
                trace_id=trace_id,
                user_id=user_id,
                entity_type=entity_type,
                entity_id=entity_id,
                op=op,
                payload=payload,
            )
        )

    def record_opportunity(
        self,
        db: Session,
        opportunity: ProactiveOpportunity,
        *,
        user_id: int | None,
        trace_id: str | None,
    ) -> None:
        db.add(
            AgentOpportunityRecord(
                trace_id=trace_id,
                user_id=user_id,
                opportunity_type=opportunity.opportunity_type,
                payload=opportunity.model_dump(mode="json"),
            )
        )

    def record_delivery(
        self,
        db: Session,
        delivery: DeliveryDecision,
        *,
        user_id: int | None,
        trace_id: str | None,
        topic: str = "",
    ) -> None:
        db.add(
            AgentDeliveryRecord(
                trace_id=trace_id,
                user_id=user_id,
                topic=topic,
                delivery_surface=delivery.delivery_surface.value,
                delivery_action=delivery.delivery_action.value,
                should_send=delivery.should_send,
                importance=delivery.importance,
                urgency=delivery.urgency,
                payload=delivery.model_dump(mode="json"),
            )
        )

    def latest_goal_state(self, db: Session, user_id: int) -> dict | None:
        row = db.scalar(
            select(AgentStateSnapshotRecord)
            .where(
                AgentStateSnapshotRecord.user_id == user_id,
                AgentStateSnapshotRecord.snapshot_type.in_(("goal_state", "bootstrap")),
            )
            .order_by(desc(AgentStateSnapshotRecord.id))
        )
        if row is None or not isinstance(row.payload, dict):
            return None
        payload = row.payload
        if isinstance(payload.get("goal_state"), dict):
            return payload["goal_state"]
        return payload

    def latest_state_snapshot(self, db: Session, user_id: int) -> dict | None:
        row = db.scalar(
            select(AgentStateSnapshotRecord)
            .where(AgentStateSnapshotRecord.user_id == user_id)
            .order_by(desc(AgentStateSnapshotRecord.id))
        )
        if row is None or not isinstance(row.payload, dict):
            return None
        return row.payload

    def has_bootstrap(self, db: Session, user_id: int) -> bool:
        row = db.scalar(
            select(AgentStateSnapshotRecord.id)
            .where(
                AgentStateSnapshotRecord.user_id == user_id,
                AgentStateSnapshotRecord.snapshot_type == "bootstrap",
            )
            .limit(1)
        )
        return row is not None

    def list_turns(self, db: Session, *, user_id: int | None = None, limit: int = 20) -> list[dict]:
        query = select(AgentTurnRecord).order_by(desc(AgentTurnRecord.id)).limit(limit)
        if user_id is not None:
            query = query.where(AgentTurnRecord.user_id == user_id)
        rows = db.execute(query).scalars().all()
        return [row.payload for row in rows]

    def latest_delivery_metrics(self, db: Session, user_id: int) -> dict:
        start_of_day = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
        today_rows = db.execute(
            select(AgentDeliveryRecord)
            .where(
                AgentDeliveryRecord.user_id == user_id,
                AgentDeliveryRecord.should_send.is_(True),
                AgentDeliveryRecord.created_at >= start_of_day,
            )
            .order_by(desc(AgentDeliveryRecord.created_at))
        ).scalars().all()
        latest = today_rows[0] if today_rows else db.scalar(
            select(AgentDeliveryRecord)
            .where(AgentDeliveryRecord.user_id == user_id)
            .order_by(desc(AgentDeliveryRecord.created_at))
        )
        cooldown_topics: dict[str, str] = {}
        for row in db.execute(
            select(AgentDeliveryRecord)
            .where(AgentDeliveryRecord.user_id == user_id)
            .order_by(desc(AgentDeliveryRecord.created_at))
            .limit(20)
        ).scalars():
            if row.topic and row.topic not in cooldown_topics:
                cooldown_topics[row.topic] = row.created_at.isoformat()
        return {
            "proactive_sent_today": len(today_rows),
            "last_interrupt_at": latest.created_at if latest and latest.should_send else None,
            "cooldown_topics": cooldown_topics,
        }

    def replace_memory_families(
        self,
        db: Session,
        *,
        user_id: int,
        families: list[dict],
        evidences: list[dict],
    ) -> None:
        for row in db.execute(select(AgentMemoryFamilyRecord).where(AgentMemoryFamilyRecord.user_id == user_id)).scalars().all():
            db.delete(row)
        for row in db.execute(select(AgentMemoryEvidenceRecord).where(AgentMemoryEvidenceRecord.user_id == user_id)).scalars().all():
            db.delete(row)
        db.flush()

        family_id_by_key: dict[str, int] = {}
        for family in families:
            family_key = str(family.pop("family_key"))
            row = AgentMemoryFamilyRecord(user_id=user_id, **family)
            db.add(row)
            db.flush()
            family_id_by_key[family_key] = row.id

        for evidence in evidences:
            family_key = str(evidence.pop("family_key"))
            family_id = family_id_by_key.get(family_key)
            if family_id is None:
                continue
            db.add(AgentMemoryEvidenceRecord(user_id=user_id, family_id=family_id, **evidence))

    def record_eval_label(
        self,
        db: Session,
        *,
        trace_id: str | None,
        user_id: int | None,
        label_type: str,
        label: str,
        notes: str = "",
        payload: dict | None = None,
    ) -> None:
        db.add(
            AgentEvalLabelRecord(
                trace_id=trace_id,
                user_id=user_id,
                label_type=label_type,
                label=label,
                notes=notes,
                payload=payload or {},
            )
        )

    def _coerce_user_id(self, value: str | int | None) -> int | None:
        if value is None:
            return None
        try:
            return int(value)
        except (TypeError, ValueError):
            return None


def goal_state_from_snapshot(snapshot: dict | None, fallback: AgentState) -> dict:
    if isinstance(snapshot, dict):
        goal_state = snapshot.get("goal_state")
        if isinstance(goal_state, dict):
            return goal_state
    return fallback.goal_state.model_dump(mode="json")
