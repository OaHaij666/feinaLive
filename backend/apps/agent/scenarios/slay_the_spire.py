from __future__ import annotations

from apps.agent.capabilities.mcp_adapter import MCPScenarioAdapter
from apps.agent.definition import ScenarioSpec


def build_slay_the_spire_scenario(adapter: MCPScenarioAdapter) -> ScenarioSpec:
    return ScenarioSpec(
        id=adapter.game_id,
        display_name=adapter.display_name,
        instructions=adapter.prompt_guidance,
        capabilities=("events", "mcp", "memory", "host_speech"),
        memory_scope=adapter.game_id,
        sandbox_policy="none",
        metadata={"profile_id": "slay_the_spire", "source": "mcp"},
    )
