from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from pydantic import ValidationError

from apps.agent.capabilities.mcp_adapter import MCPScenarioAdapter
from apps.agent.definition import ScenarioSpec
from apps.agent.scenarios.generic import build_generic_scenario
from apps.agent.scenarios.generic_profile import GenericMCPScenarioProfile
from apps.agent.scenarios.profile import ScenarioProfile
from apps.agent.scenarios.slay_the_spire import build_slay_the_spire_scenario
from apps.agent.scenarios.slay_the_spire_profile import SlayTheSpireScenarioProfile
from apps.ai.mcp.client import MCPClient
from apps.ai.memory.game_memory import GameMemoryPolicy
from apps.config import config


@dataclass(frozen=True, slots=True)
class ScenarioRuntimeDefinition:
    spec: ScenarioSpec
    capability_resources: dict[str, Any]
    memory_policy: GameMemoryPolicy | None
    startup_config: dict[str, Any]


_SCENARIO_PROFILES: dict[str, type[ScenarioProfile]] = {
    GenericMCPScenarioProfile.profile_id: GenericMCPScenarioProfile,
    SlayTheSpireScenarioProfile.profile_id: SlayTheSpireScenarioProfile,
}


def validate_scenario_config(
    scenario_id: str,
    values: dict[str, Any] | None = None,
) -> dict[str, Any]:
    profile_type = _SCENARIO_PROFILES.get(scenario_id)
    if scenario_id == "event_assistant":
        if values:
            raise ValueError("场景配置无效: event_assistant 不接受配置字段")
        return {}
    if profile_type is None:
        raise ValueError(f"未注册的场景: {scenario_id}")
    try:
        return profile_type.config_model.model_validate(values or {}).model_dump()
    except ValidationError as exc:
        raise ValueError(f"场景配置无效: {exc}") from exc


def create_scenario(
    scenario_id: str,
    *,
    mcp_url: str,
    scenario_config: dict[str, Any] | None = None,
) -> ScenarioRuntimeDefinition:
    if scenario_id == "event_assistant":
        spec = ScenarioSpec(
            id="event_assistant",
            display_name="事件驱动助手",
            instructions="等待外部事件或目标；只根据事件内容规划，信息不足时继续等待。",
            capabilities=("events", "memory", "host_speech"),
            memory_scope="event_assistant",
            sandbox_policy="none",
            metadata={"source": "events"},
        )
        return ScenarioRuntimeDefinition(
            spec=spec,
            capability_resources={},
            memory_policy=GameMemoryPolicy(
                session_mode="continuous",
                summary_threshold=config.agent_memory_threshold,
                idle_summary_seconds=config.agent_memory_idle_seconds,
                context_max_chars=config.agent_memory_context_max_chars,
            ),
            startup_config={
                "scenario_id": scenario_id,
                "mcp_url": mcp_url,
                "scenario_config": {},
            },
        )
    profile_type = _SCENARIO_PROFILES.get(scenario_id)
    if profile_type is None:
        raise ValueError(f"未注册的场景: {scenario_id}")
    profile = profile_type(validate_scenario_config(scenario_id, scenario_config))
    adapter = MCPScenarioAdapter(MCPClient(base_url=mcp_url), profile)
    spec = (
        build_slay_the_spire_scenario(adapter)
        if scenario_id == "slay_the_spire"
        else build_generic_scenario(adapter)
    )
    return ScenarioRuntimeDefinition(
        spec=spec,
        capability_resources={"mcp_adapter": adapter},
        memory_policy=adapter.memory_policy,
        startup_config={
            "scenario_id": scenario_id,
            "mcp_url": mcp_url,
            "scenario_config": dict(scenario_config or {}),
        },
    )


def list_scenarios() -> list[dict[str, Any]]:
    scenarios = [
        {
            **profile.catalog_entry(),
            "capability_sources": ["events", "mcp", "memory", "host_speech"],
            "restart_required": True,
        }
        for profile in _SCENARIO_PROFILES.values()
    ]
    scenarios.append(
        {
            "scenario_id": "event_assistant",
            "display_name": "事件驱动助手",
            "description": "无 MCP；由外部事件或目标主动唤醒。",
            "category": "generic_agent",
            "config_fields": [],
            "capability_sources": ["events", "memory", "host_speech"],
            "restart_required": True,
        }
    )
    return scenarios
