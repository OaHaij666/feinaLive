from __future__ import annotations

import asyncio
import json
import logging
import re
from typing import Any

from apps.agent.capabilities.base import CapabilityRouter
from apps.agent.capabilities.host_speech import HostSpeechCapability
from apps.agent.commentary import CommentaryComposer
from apps.agent.definition import ScenarioSpec
from apps.agent.mutual_context import MutualContext
from apps.agent.state import (
    AgentPlan,
    AgentRoute,
    AgentRuntimeState,
    AgentStep,
    AgentTurnOutcome,
    CapabilityCall,
    CommentaryRequest,
    CommentarySync,
)
from apps.ai.client import ChatMessage, ChatRequest, get_agent_ai_client
from apps.ai.memory.engine import get_memory_engine
from apps.config import config

logger = logging.getLogger(__name__)


COMMENTARY_TOOL = {
    "type": "function",
    "function": {
        "name": "request_commentary",
        "description": "请求主播对当前决策或已确认结果进行解说；只给事件摘要和简短原因，不写最终台词。",
        "parameters": {
            "type": "object",
            "properties": {
                "event_summary": {"type": "string"},
                "reason": {"type": "string"},
                "evidence_refs": {"type": "array", "items": {"type": "string"}},
                "action_ref": {"type": "string"},
                "sync": {
                    "type": "string",
                    "enum": [item.value for item in CommentarySync],
                },
                "urgency": {"type": "integer", "minimum": 1, "maximum": 5},
            },
            "required": ["event_summary", "reason"],
        },
    },
}


AGENT_SYSTEM_PROMPT = """你是一个持续运行的通用执行 Agent，而不是某个固定游戏的脚本。

【当前场景】
{scenario_name}
{scenario_instructions}
Sandbox 策略：{sandbox_policy}

【可用能力】
{capability_names}

【当前观察】
{observations}

【场景记忆】
{memory}

【Host 与 Agent 的近期共享动态】
{mutual_context}

规则：
1. 只调用上面实际注册的能力，不猜测不存在的工具。
2. 查询类能力的结果会回到下一次 reason；信息不足时先查询，不要边猜边操作。
3. 一轮最多选择一个有副作用的动作；可以同时提出一个 request_commentary。
4. request_commentary 只包含事件摘要、简短原因、证据引用和同步方式，不要在这里写主播最终台词。
5. after_result 只用于已经确认的结果。尚未执行的动作不得写成功话术。
6. 没有动作时返回 JSON：{{"route":"sleep"}} 或 {{"route":"wait_event"}}。不要返回 end。
7. goal_completed 只表示当前目标完成，Runtime 仍会继续等待新事件。
"""


class AgentGraph:
    """One reusable graph whose path is selected by plan and capabilities."""

    node_names = (
        "observe",
        "assemble_context",
        "reason",
        "validate",
        "compose_commentary",
        "execute_plan",
        "observe_result",
        "commit",
        "route",
    )

    def __init__(
        self,
        scenario: ScenarioSpec,
        capability_router: CapabilityRouter,
        mutual_context: MutualContext,
        commentary: CommentaryComposer | None,
        host_speech: HostSpeechCapability | None,
    ) -> None:
        self._scenario = scenario
        self._router = capability_router
        self._mutual_context = mutual_context
        self._commentary = commentary
        self._host_speech = host_speech
        self._background_tasks: set[asyncio.Task[Any]] = set()

    async def run_turn(self) -> AgentTurnOutcome:
        state = AgentRuntimeState(scenario_id=self._scenario.id)
        try:
            await self._observe(state)
            if not state.observations:
                return AgentTurnOutcome(route=AgentRoute.WAIT_EVENT)
            terminals = [item for item in state.observations if item.terminal]
            if terminals:
                restarted = False
                for item in terminals:
                    restarted = await self._router.handle_terminal(item) or restarted
                return AgentTurnOutcome(
                    route=AgentRoute.CONTINUE if restarted else AgentRoute.GOAL_COMPLETED,
                    observations=state.observations,
                )
            if not any(item.actionable for item in state.observations):
                return AgentTurnOutcome(route=AgentRoute.WAIT_EVENT, observations=state.observations)

            await self._assemble_context(state)
            await self._reason(state)
            self._validate(state)

            # Read-only results are observations, never a dead-end side effect.
            for _ in range(3):
                readonly = [step for step in state.plan.steps if step.call.readonly]
                if not readonly:
                    break
                for step in readonly:
                    result = await self._router.execute(step.call)
                    state.results.append(result)
                    if result.observation:
                        state.observations.append(result.observation)
                state.plan = AgentPlan()
                await self._assemble_context(state)
                await self._reason(state)
                self._validate(state)
            if any(step.call.readonly for step in state.plan.steps):
                logger.warning("Agent exceeded the per-turn read-only reasoning budget")
                state.plan.steps.clear()
                state.plan.route = AgentRoute.RETRY

            commentary_text = await self._execute_plan(state)
            await self._observe_result(state)
            await self._commit(state, commentary_text)
            route = self._route(state)
            return AgentTurnOutcome(
                route=route,
                observations=state.observations,
                results=state.results,
                commentary_text=commentary_text,
            )
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            logger.exception("AgentGraph turn failed")
            return AgentTurnOutcome(
                route=AgentRoute.FAILED,
                observations=state.observations,
                results=state.results,
                error=str(exc),
            )

    async def close(self) -> None:
        tasks = list(self._background_tasks)
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)

    async def _observe(self, state: AgentRuntimeState) -> None:
        state.observations.extend(await self._router.observations())

    async def _assemble_context(self, state: AgentRuntimeState) -> None:
        try:
            memory = await get_memory_engine().inject_for_game(self._scenario.memory_scope)
        except Exception as exc:
            logger.warning("Agent memory injection failed: %s", exc)
            memory = "（记忆暂不可用）"
        definitions = await self._router.definitions()
        names = [item.get("function", {}).get("name", "") for item in definitions]
        if self._commentary is not None and self._host_speech is not None:
            names.append("request_commentary")
        display_names = [name.replace("mcp__", "mcp.").replace("memory__", "memory.") for name in names]
        state.context = AGENT_SYSTEM_PROMPT.format(
            scenario_name=self._scenario.display_name,
            scenario_instructions=self._scenario.instructions,
            sandbox_policy=self._scenario.sandbox_policy,
            capability_names="\n".join(f"- {name}" for name in display_names if name),
            observations="\n\n".join(item.summary for item in state.observations[-6:]),
            memory=memory or "（暂无）",
            mutual_context=await self._mutual_context.to_prompt_text(),
        )

    async def _reason(self, state: AgentRuntimeState) -> None:
        state.reasoning_passes += 1
        ai = get_agent_ai_client()
        if not ai.available:
            state.plan = AgentPlan(route=AgentRoute.SLEEP)
            return
        tools = await self._router.definitions()
        if self._commentary is not None and self._host_speech is not None:
            tools.append(COMMENTARY_TOOL)
        response = await ai.chat(
            ChatRequest(
                messages=[
                    ChatMessage(role="system", content=state.context),
                    ChatMessage(
                        role="user",
                        content="根据当前观察选择能力调用，或返回 sleep/wait_event JSON。",
                    ),
                ],
                model=config.agent_model,
                temperature=config.agent_temperature,
                max_tokens=config.agent_max_tokens,
                disable_thinking=config.agent_disable_thinking,
                tools=tools,
            )
        )
        state.plan = self._parse_plan(response.tool_calls if response else [], response.content if response else "")

    def _validate(self, state: AgentRuntimeState) -> None:
        valid_steps: list[AgentStep] = []
        mutating_seen = False
        for step in state.plan.steps:
            call = self._router.validate(step.call)
            if call is None:
                continue
            if not call.readonly:
                if mutating_seen:
                    continue
                mutating_seen = True
            valid_steps.append(step)
        state.plan.steps = valid_steps
        if not valid_steps and state.plan.commentary is None and state.plan.route is AgentRoute.CONTINUE:
            state.plan.route = AgentRoute.SLEEP

    async def _execute_plan(self, state: AgentRuntimeState) -> str:
        mutating_steps = [step for step in state.plan.steps if not step.call.readonly]
        request = state.plan.commentary
        if self._commentary is None or self._host_speech is None:
            request = None
        if request and request.sync is CommentarySync.AFTER_RESULT and mutating_steps:
            # The result is not known yet. Keep the reason in the mutual window;
            # a subsequent reason pass may request a truthful result commentary.
            await self._mutual_context.record(
                "agent",
                "commentary_deferred",
                f"{request.event_summary}；等待动作结果后再判断是否解说",
                {"reason": request.reason},
            )
            request = None

        if not mutating_steps:
            if request:
                return await self._compose_and_speak(request, state)
            return ""

        step = mutating_steps[0]
        if not request:
            state.results.append(await self._router.execute(step.call))
            return ""

        if request.sync is CommentarySync.BEFORE_ACTION:
            text = await self._compose_and_speak(request, state)
            state.results.append(await self._router.execute(step.call))
            return text

        if request.sync is CommentarySync.ON_SPEECH_START:
            text = await self._commentary.compose(request, state.observations, state.results)
            if not text:
                state.results.append(await self._router.execute(step.call))
                return ""
            started = asyncio.Event()
            speech_task = asyncio.create_task(self._host_speech.speak(text, started=started))
            try:
                await asyncio.wait_for(
                    started.wait(),
                    timeout=min(config.agent_commentary_hold_timeout, config.host_playback_timeout_seconds),
                )
            except asyncio.TimeoutError:
                logger.warning("Commentary playback did not start before action timeout")
            state.results.append(await self._router.execute(step.call))
            await speech_task
            return text

        if request.sync is CommentarySync.PARALLEL:
            text = await self._commentary.compose(request, state.observations, state.results)
            speech_result, action_result = await asyncio.gather(
                self._host_speech.speak(text) if text else asyncio.sleep(0, result=None),
                self._router.execute(step.call),
            )
            state.results.append(action_result)
            return text if speech_result else ""

        if request.sync is CommentarySync.BACKGROUND:
            text = await self._commentary.compose(request, state.observations, state.results)
            if text:
                task = asyncio.create_task(self._host_speech.speak(text))
                self._background_tasks.add(task)
                task.add_done_callback(self._background_tasks.discard)
            state.results.append(await self._router.execute(step.call))
            return text

        state.results.append(await self._router.execute(step.call))
        return ""

    async def _compose_and_speak(
        self,
        request: CommentaryRequest,
        state: AgentRuntimeState,
    ) -> str:
        if self._commentary is None or self._host_speech is None:
            return ""
        text = await self._commentary.compose(request, state.observations, state.results)
        if not text:
            return ""
        result = await self._host_speech.speak(text)
        return text if result and result.played else ""

    async def _observe_result(self, state: AgentRuntimeState) -> None:
        for result in state.results:
            if result.observation and result.observation not in state.observations:
                state.observations.append(result.observation)
        if state.results:
            state.observations.extend(
                await self._router.observations(exclude_sources={"events"})
            )

    async def _commit(self, state: AgentRuntimeState, commentary_text: str) -> None:
        if commentary_text:
            await self._mutual_context.record(
                "agent",
                "commentary_reason",
                state.plan.commentary.reason if state.plan.commentary else "场景解说",
            )

    @staticmethod
    def _route(state: AgentRuntimeState) -> AgentRoute:
        if state.plan.route is not AgentRoute.CONTINUE:
            return state.plan.route
        if any(not item.success for item in state.results):
            return AgentRoute.RETRY
        return AgentRoute.CONTINUE if state.results else AgentRoute.SLEEP

    @classmethod
    def _parse_plan(cls, tool_calls: list[dict[str, Any]], content: str) -> AgentPlan:
        plan = AgentPlan()
        normalized = cls._normalize_tool_calls(tool_calls)
        if not normalized and content:
            extracted = content
            if match := re.search(r"```(?:json)?\s*(.*?)```", content, re.DOTALL):
                extracted = match.group(1).strip()
            try:
                payload = json.loads(extracted)
            except json.JSONDecodeError:
                payload = {}
            route = str(payload.get("route", "")) if isinstance(payload, dict) else ""
            if route in {item.value for item in AgentRoute}:
                plan.route = AgentRoute(route)
            normalized = cls._normalize_tool_calls(payload.get("tool_calls", []) if isinstance(payload, dict) else [])

        for name, arguments in normalized:
            if name == "request_commentary":
                try:
                    sync = CommentarySync(str(arguments.get("sync", CommentarySync.ON_SPEECH_START.value)))
                except ValueError:
                    sync = CommentarySync.ON_SPEECH_START
                plan.commentary = CommentaryRequest(
                    event_summary=str(arguments.get("event_summary", ""))[:500],
                    reason=str(arguments.get("reason", ""))[:500],
                    evidence_refs=[str(item)[:200] for item in arguments.get("evidence_refs", [])[:8]],
                    action_ref=str(arguments.get("action_ref", ""))[:200],
                    sync=sync,
                    urgency=max(1, min(5, int(arguments.get("urgency", 1)))),
                )
            else:
                plan.steps.append(AgentStep(call=CapabilityCall(name=name, arguments=arguments)))
        return plan

    @staticmethod
    def _normalize_tool_calls(tool_calls: Any) -> list[tuple[str, dict[str, Any]]]:
        if not isinstance(tool_calls, list):
            return []
        result: list[tuple[str, dict[str, Any]]] = []
        for item in tool_calls:
            if not isinstance(item, dict):
                continue
            function = item.get("function", item)
            name = str(function.get("name", ""))
            arguments = function.get("arguments", function.get("params", {}))
            if isinstance(arguments, str):
                try:
                    arguments = json.loads(arguments)
                except json.JSONDecodeError:
                    arguments = {}
            if name and isinstance(arguments, dict):
                result.append((name, arguments))
        return result
