from __future__ import annotations

import asyncio

from apps.agent.capabilities.base import Capability, CapabilityRouter
from apps.agent.events import AgentEvent, EventInboxCapability
from apps.agent.graph import AgentGraph
from apps.agent.mutual_context import MutualContext
from apps.agent.runtime import AgentRuntime
from apps.agent.state import (
    AgentRoute,
    AgentTurnOutcome,
    CapabilityCall,
    CapabilityResult,
    CommentarySync,
)


class FakeCapability(Capability):
    source = "fake"

    async def definitions(self):
        return [
            {
                "type": "function",
                "function": {
                    "name": "fake__inspect",
                    "description": "inspect",
                    "parameters": {"type": "object", "properties": {}},
                },
            }
        ]

    def owns(self, name: str) -> bool:
        return name == "fake__inspect"

    def is_readonly(self, name: str) -> bool:
        return True

    async def execute(self, call: CapabilityCall) -> CapabilityResult:
        return CapabilityResult(call=call, success=True, output="ok")


async def test_mutual_context_is_small_ttl_window(monkeypatch):
    context = MutualContext(maxlen=2, ttl_seconds=5)
    now = 100.0
    monkeypatch.setattr("apps.agent.mutual_context.time.time", lambda: now)
    await context.record("host", "spoken", "one")
    await context.record("agent", "action", "two")
    await context.record("host", "spoken", "three")
    assert [item.summary for item in await context.recent()] == ["two", "three"]

    now = 106.0
    assert await context.recent() == []


def test_agent_plan_parses_commentary_contract_and_capability_call():
    plan = AgentGraph._parse_plan(
        [
            {
                "function": {
                    "name": "request_commentary",
                    "arguments": {
                        "event_summary": "准备处理威胁最大的敌人",
                        "reason": "关键决策",
                        "evidence_refs": ["observation:enemy_1"],
                        "action_ref": "step_1",
                        "sync": "on_speech_start",
                        "urgency": 3,
                    },
                }
            },
            {"function": {"name": "mcp__play_card", "arguments": {"index": 1}}},
        ],
        "",
    )
    assert plan.commentary is not None
    assert plan.commentary.sync is CommentarySync.ON_SPEECH_START
    assert plan.commentary.reason == "关键决策"
    assert plan.steps[0].call.name == "mcp__play_card"


async def test_capability_router_marks_readonly_and_returns_observation():
    router = CapabilityRouter([FakeCapability()])
    call = CapabilityCall(name="fake__inspect")
    assert router.validate(call) is call
    assert call.readonly is True
    assert await router.observations() == []
    assert (await router.execute(call)).output == "ok"


async def test_mutual_context_does_not_store_empty_entries():
    context = MutualContext()
    await context.record("host", "spoken", "   ")
    await asyncio.sleep(0)
    assert await context.snapshot() == []


async def test_event_inbox_turns_external_event_into_observation():
    inbox = EventInboxCapability()
    await inbox.publish(AgentEvent("goal", "http", {"task": "inspect"}))

    observation = await inbox.observe()

    assert observation is not None and observation.actionable
    assert "http/goal" in observation.summary
    assert observation.data[0]["payload"] == {"task": "inspect"}


async def test_runtime_event_publish_wakes_waiting_scheduler(monkeypatch):
    from apps.config import config

    calls = 0
    first = asyncio.Event()
    second = asyncio.Event()

    class Graph:
        async def run_turn(self):
            nonlocal calls
            calls += 1
            (first if calls == 1 else second).set()
            return AgentTurnOutcome(route=AgentRoute.WAIT_EVENT)

        async def close(self):
            return None

    inbox = EventInboxCapability()
    runtime = AgentRuntime(
        "event-test",
        Graph(),
        CapabilityRouter([inbox]),
        inbox,
    )
    monkeypatch.setattr(type(config), "agent_poll_interval", property(lambda self: 60.0))

    await runtime.start()
    await asyncio.wait_for(first.wait(), timeout=1)
    await runtime.publish(AgentEvent("goal", "test", {"value": 1}))
    await asyncio.wait_for(second.wait(), timeout=1)
    await runtime.stop()

    assert calls >= 2
