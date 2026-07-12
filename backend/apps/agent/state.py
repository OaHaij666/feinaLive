from __future__ import annotations

import time
import uuid
from dataclasses import dataclass, field
from enum import Enum
from typing import Any


class AgentRoute(str, Enum):
    CONTINUE = "continue"
    SLEEP = "sleep"
    WAIT_EVENT = "wait_event"
    GOAL_COMPLETED = "goal_completed"
    RETRY = "retry"
    FAILED = "failed"
    CANCELLED = "cancelled"


class CommentarySync(str, Enum):
    BEFORE_ACTION = "before_action"
    ON_SPEECH_START = "on_speech_start"
    PARALLEL = "parallel"
    AFTER_RESULT = "after_result"
    BACKGROUND = "background"


@dataclass(slots=True)
class Observation:
    source: str
    summary: str
    data: Any = None
    ref: str = field(default_factory=lambda: f"observation:{uuid.uuid4().hex[:12]}")
    actionable: bool = True
    terminal: bool = False
    created_at: float = field(default_factory=time.time)


@dataclass(slots=True)
class CapabilityCall:
    name: str
    arguments: dict[str, Any] = field(default_factory=dict)
    call_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    readonly: bool = False


@dataclass(slots=True)
class CapabilityResult:
    call: CapabilityCall
    success: bool
    output: Any = None
    error: str = ""
    observation: Observation | None = None


@dataclass(slots=True)
class CommentaryRequest:
    event_summary: str
    reason: str
    evidence_refs: list[str] = field(default_factory=list)
    action_ref: str = ""
    sync: CommentarySync = CommentarySync.ON_SPEECH_START
    urgency: int = 1


@dataclass(slots=True)
class AgentStep:
    call: CapabilityCall
    step_id: str = field(default_factory=lambda: f"step:{uuid.uuid4().hex[:12]}")
    commentary: CommentaryRequest | None = None


@dataclass(slots=True)
class AgentPlan:
    steps: list[AgentStep] = field(default_factory=list)
    commentary: CommentaryRequest | None = None
    route: AgentRoute = AgentRoute.CONTINUE
    rationale: str = ""


@dataclass(slots=True)
class AgentTurnOutcome:
    route: AgentRoute
    observations: list[Observation] = field(default_factory=list)
    results: list[CapabilityResult] = field(default_factory=list)
    commentary_text: str = ""
    error: str = ""


@dataclass(slots=True)
class AgentRuntimeState:
    scenario_id: str
    turn_id: str = field(default_factory=lambda: uuid.uuid4().hex)
    observations: list[Observation] = field(default_factory=list)
    context: str = ""
    plan: AgentPlan = field(default_factory=AgentPlan)
    results: list[CapabilityResult] = field(default_factory=list)
    reasoning_passes: int = 0
