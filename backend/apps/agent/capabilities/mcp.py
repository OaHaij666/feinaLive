from __future__ import annotations

import json
from typing import Any

from apps.agent.capabilities.base import Capability
from apps.agent.capabilities.mcp_adapter import MCPScenarioAdapter
from apps.agent.mutual_context import MutualContext
from apps.agent.scenarios.profile import UnifiedAction
from apps.agent.state import CapabilityCall, CapabilityResult, Observation
from apps.ai.memory.engine import get_memory_engine
from apps.ai.memory.game_memory import GameMemoryAPI


class MCPCapability(Capability):
    """MCP transport capability; scenario meaning remains in the bound adapter."""

    source = "mcp"
    _prefix = "mcp__"

    def __init__(self, adapter: MCPScenarioAdapter, mutual_context: MutualContext) -> None:
        self.adapter = adapter
        self._mutual_context = mutual_context
        self._known_tools: set[str] = set()
        self._terminal_handled = False

    @property
    def game_id(self) -> str:
        return self.adapter.game_id

    async def definitions(self) -> list[dict[str, Any]]:
        definitions = await self.adapter.get_tools_definition()
        result: list[dict[str, Any]] = []
        self._known_tools.clear()
        for item in definitions:
            copied = {
                "type": item.get("type", "function"),
                "function": dict(item.get("function", {})),
            }
            raw_name = str(copied["function"].get("name", ""))
            if not raw_name:
                continue
            self._known_tools.add(raw_name)
            copied["function"]["name"] = self._prefix + raw_name
            result.append(copied)
        return result

    def owns(self, name: str) -> bool:
        return name.startswith(self._prefix) and self._raw_name(name) in self._known_tools

    def is_readonly(self, name: str) -> bool:
        return self.adapter.is_readonly_tool(self._raw_name(name))

    async def health_check(self) -> bool:
        return await self.adapter.health_check()

    async def observe(self) -> Observation:
        state = await self.adapter.get_state()
        if not self.adapter.is_session_finished(state):
            self._terminal_handled = False
        prompt_text = self.adapter.format_state_for_prompt(state.raw_state, state.to_prompt_text())
        return Observation(
            source=self.source,
            summary=prompt_text or "MCP 当前没有返回可用状态",
            data=state,
            actionable=self.adapter.is_my_turn(state),
            terminal=self.adapter.is_session_finished(state),
            ref=f"observation:mcp:{self.game_id}",
        )

    async def handle_terminal(self, observation: Observation) -> bool:
        if self._terminal_handled:
            return False
        self._terminal_handled = True
        state = observation.data
        engine = get_memory_engine()
        await engine.close_game_session(
            self.game_id,
            reason="scenario_goal_completed",
            final_event=self.adapter.session_end_event(state),
        )
        restart_actions = self.adapter.session_restart_actions(state)
        for action in restart_actions:
            if self.adapter.is_session_start_action(action):
                result = await self.execute(
                    CapabilityCall(
                        name=self._prefix + action.action_type,
                        arguments=action.params,
                    )
                )
                success = result.success
            else:
                success, message = await self.adapter.execute_action(action)
                await self._mutual_context.record(
                    "agent",
                    "lifecycle_action",
                    f"{action.action_type} -> {'成功' if success else '失败'}: {message}",
                )
            if not success:
                return False
        return bool(restart_actions)

    async def execute(self, call: CapabilityCall) -> CapabilityResult:
        raw_name = self._raw_name(call.name)
        action = UnifiedAction(action_type=raw_name, params=call.arguments)
        if self.adapter.is_readonly_tool(raw_name):
            try:
                output = await self.adapter.query_tool(raw_name, call.arguments)
                success = not (isinstance(output, dict) and output.get("success") is False)
                result = CapabilityResult(
                    call=call,
                    success=success,
                    output=output,
                    observation=Observation(
                        source=self.source,
                        summary=f"{raw_name} 查询结果: {self._preview(output)}",
                        data=output,
                    ),
                )
                if self.adapter.memory_policy.capture_query_results:
                    await get_memory_engine().record_mcp_event(
                        self.game_id,
                        event_type="mcp_query_result",
                        tool_name=raw_name,
                        arguments=call.arguments,
                        result=output,
                        success=success,
                    )
                return result
            except Exception as exc:
                return CapabilityResult(call=call, success=False, error=str(exc))

        engine = get_memory_engine()
        starts_session = self.adapter.is_session_start_action(action)
        if starts_session:
            await engine.close_game_session(self.game_id, reason="session_start_action_requested")
        try:
            success, message = await self.adapter.execute_action(action)
        except Exception as exc:
            success, message = False, str(exc)

        if starts_session and success:
            await engine.open_game_session(self.game_id, policy=self.adapter.memory_policy)
            await self.adapter.on_game_session_opened(GameMemoryAPI(engine, self.game_id))
        else:
            await engine.ensure_game_session(self.game_id)
        if self.adapter.memory_policy.capture_action_results:
            await engine.record_mcp_event(
                self.game_id,
                event_type="mcp_action_result",
                tool_name=raw_name,
                arguments=call.arguments,
                result={"message": message},
                success=success,
            )
        await self._mutual_context.record(
            "agent",
            "action_result",
            f"{raw_name}({call.arguments}) -> {'成功' if success else '失败'}: {message}",
            {"capability": call.name, "success": success},
        )
        return CapabilityResult(
            call=call,
            success=success,
            output=message,
            error="" if success else message,
            observation=Observation(
                source=self.source,
                summary=f"{raw_name} 执行{'成功' if success else '失败'}: {message}",
                data={"success": success, "message": message},
            ),
        )

    async def close(self) -> None:
        await self.adapter.close()

    @classmethod
    def _raw_name(cls, name: str) -> str:
        return name[len(cls._prefix) :] if name.startswith(cls._prefix) else name

    @staticmethod
    def _preview(value: Any) -> str:
        try:
            return json.dumps(value, ensure_ascii=False, default=str)[:1000]
        except TypeError:
            return str(value)[:1000]
