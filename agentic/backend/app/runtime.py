from __future__ import annotations

from sqlalchemy.orm import Session

from .contracts import DecisionHome, HomePayload
from .guardrails import DeterministicGuardrails
from .loop import AgentLoop
from .providers import StructuredOutputProvider
from .state import AgentStateAssembler
from .store import AgenticStore


store = AgenticStore()
state_assembler = AgentStateAssembler(store)
guardrails = DeterministicGuardrails()
provider = StructuredOutputProvider()
agent_loop = AgentLoop(
    state_assembler=state_assembler,
    guardrails=guardrails,
    provider=provider,
)


def build_home_payload(
    db: Session,
    user,
    *,
    title: str,
    home: DecisionHome,
    cohort: str,
    core_version: str,
) -> HomePayload:
    state = state_assembler.build(db, user)
    opportunities = state_assembler.opportunities_for(db, state)
    delivery = agent_loop.delivery_decision(state, opportunities, telemetry={}, deadline=float("inf"))
    highlights = [
        "Goal state participates in ranking, coaching, and proactive importance.",
        "Conversation continuity is shared across LINE and LIFF.",
        "Deterministic guardrails still own writes, math, and bounded filters.",
    ]
    if home is DecisionHome.eat:
        highlights[0] = "Eat is bounded by goal-aware shortlist and nearby comparison."
    elif home is DecisionHome.progress:
        highlights[0] = "Progress uses the same goal state for drift, recovery, and future events."
    elif home is DecisionHome.settings:
        highlights[0] = "Settings and onboarding update the same state the agent uses everywhere."
    return HomePayload(
        title=title,
        state=state,
        highlights=highlights,
        opportunities=opportunities,
        delivery_preview=delivery,
        cohort=cohort,
        core_version=core_version,
        metadata={"decision_home": home.value},
    )
