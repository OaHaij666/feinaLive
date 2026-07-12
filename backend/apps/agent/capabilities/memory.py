from __future__ import annotations

from typing import Any

from apps.agent.capabilities.base import Capability
from apps.agent.state import CapabilityCall, CapabilityResult, Observation
from apps.ai.memory.tools import get_memory_tools, handle_memory_tool_call


class MemoryCapability(Capability):
    source = "memory"

    def __init__(self, game_id: str) -> None:
        self._game_id = game_id

    async def definitions(self) -> list[dict[str, Any]]:
        tools = get_memory_tools(read_only=True)
        for tool in tools:
            tool["function"]["name"] = "memory__recall"
        return tools

    def owns(self, name: str) -> bool:
        return name == "memory__recall"

    def is_readonly(self, name: str) -> bool:
        return True

    async def execute(self, call: CapabilityCall) -> CapabilityResult:
        output = await handle_memory_tool_call("recall", call.arguments, game_id=self._game_id)
        observation = Observation(
            source=self.source,
            summary=f"记忆召回 {call.arguments.get('query', '')}: {output}",
            data=output,
        )
        return CapabilityResult(call=call, success=True, output=output, observation=observation)
