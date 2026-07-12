"""MCP transport adapter for a scenario profile.

网络与工具调用集中在这里；场景语义只存在于 ScenarioProfile。
"""

from __future__ import annotations

from typing import Any

from apps.agent.scenarios.profile import ScenarioProfile, UnifiedAction, UnifiedGameState
from apps.ai.mcp.client import MCPClient
from apps.ai.memory.game_memory import GameMemoryAPI, GameMemoryPolicy


class MCPScenarioAdapter:
    def __init__(self, client: MCPClient, profile: ScenarioProfile):
        self._client = client
        self._profile = profile

    @property
    def game_id(self) -> str:
        return self._profile.game_id

    @property
    def game_type(self) -> str:
        return self._profile.game_type

    @property
    def display_name(self) -> str:
        return self._profile.display_name

    @property
    def prompt_guidance(self) -> str:
        return self._profile.prompt_guidance

    @property
    def prompt_examples(self) -> str:
        return self._profile.prompt_examples

    @property
    def memory_policy(self) -> GameMemoryPolicy:
        return self._profile.memory_policy

    async def get_state(self) -> UnifiedGameState:
        return await self._profile.get_state(self._client)

    async def execute_action(self, action: UnifiedAction) -> tuple[bool, str]:
        return await self._profile.execute_action(self._client, action)

    async def get_available_actions(self) -> list[UnifiedAction]:
        return await self._profile.get_available_actions(self._client)

    def is_my_turn(self, state: UnifiedGameState) -> bool:
        return self._profile.is_my_turn(state)

    def is_session_finished(self, state: UnifiedGameState) -> bool:
        return self._profile.is_session_finished(state)

    def session_end_event(self, state: UnifiedGameState) -> dict[str, Any]:
        return self._profile.session_end_event(state)

    def session_restart_actions(self, state: UnifiedGameState) -> list[UnifiedAction]:
        return self._profile.session_restart_actions(state)

    def is_readonly_tool(self, name: str) -> bool:
        return self._profile.is_readonly_tool(name)

    def expand_action(self, action: UnifiedAction) -> list[UnifiedAction]:
        return self._profile.expand_action(action)

    def is_session_start_action(self, action: UnifiedAction) -> bool:
        return self._profile.is_session_start_action(action)

    def format_state_for_prompt(self, raw: dict, fallback: str) -> str:
        return self._profile.format_state_for_prompt(raw, fallback)

    async def get_tools_definition(self) -> list[dict]:
        return await self._profile.get_tools_definition(self._client)

    async def query_tool(self, name: str, params: dict | None = None) -> Any:
        return await self._profile.query_tool(self._client, name, params)

    async def health_check(self) -> bool:
        return await self._profile.health_check(self._client)

    async def on_game_session_opened(self, memory: GameMemoryAPI) -> None:
        await self._profile.on_game_session_opened(self._client, memory)

    async def close(self) -> None:
        await self._client.close()
