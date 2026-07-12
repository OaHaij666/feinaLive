from __future__ import annotations

import pytest

from apps.agent.capabilities.mcp_adapter import MCPScenarioAdapter
from apps.agent.manager import AgentManager
from apps.agent.scenarios.profile import UnifiedAction, UnifiedGameState
from apps.agent.scenarios.registry import (
    create_scenario,
    list_scenarios,
    validate_scenario_config,
)


def test_registry_is_the_public_source_for_builtin_scenarios():
    definitions = {item["scenario_id"]: item for item in list_scenarios()}

    assert set(definitions) == {"event_assistant", "generic_mcp", "slay_the_spire"}
    assert definitions["generic_mcp"]["config_fields"]
    assert definitions["slay_the_spire"]["config_fields"][0]["key"] == "default_character"


def test_factory_applies_scenario_configuration():
    definition = create_scenario(
        "slay_the_spire",
        mcp_url="http://mcp.invalid",
        scenario_config={"default_character": "WATCHER"},
    )
    adapter = definition.capability_resources["mcp_adapter"]

    assert isinstance(adapter, MCPScenarioAdapter)
    actions = adapter.session_restart_actions(UnifiedGameState())
    assert [item.action_type for item in actions] == ["proceed", "start_game"]
    assert actions[-1].params == {"character": "WATCHER"}
    assert adapter.is_readonly_tool("get_card_info")
    assert adapter.is_session_start_action(UnifiedAction(action_type="start_game"))


def test_generic_scenario_uses_configured_identity_and_safe_turn_gate():
    definition = create_scenario(
        "generic_mcp",
        mcp_url="http://mcp.invalid",
        scenario_config={
            "scope_id": "my_scene",
            "display_name": "My Scene",
            "game_type": "strategy",
            "turn_field": "can_act",
            "session_end_field": "finished",
            "session_start_tool": "new_run",
            "readonly_tools": "inspect, lookup",
            "instructions": "Never spend the final resource.",
        },
    )
    adapter = definition.capability_resources["mcp_adapter"]

    assert definition.spec.id == "my_scene"
    assert adapter.display_name == "My Scene"
    assert adapter.is_my_turn(UnifiedGameState(raw_state={"can_act": True}))
    assert not adapter.is_my_turn(UnifiedGameState(raw_state={}))
    assert adapter.is_session_finished(UnifiedGameState(raw_state={"finished": True}))
    assert adapter.is_session_start_action(UnifiedAction(action_type="new_run"))
    assert adapter.is_readonly_tool("lookup")
    assert "Never spend" in definition.spec.instructions
    assert "杀戮尖塔" not in definition.spec.instructions


def test_invalid_scenario_or_configuration_is_rejected():
    with pytest.raises(ValueError, match="未注册的场景"):
        create_scenario("missing", mcp_url="http://mcp.invalid")
    with pytest.raises(ValueError, match="场景配置无效"):
        create_scenario(
            "slay_the_spire",
            mcp_url="http://mcp.invalid",
            scenario_config={"unknown": True},
        )


def test_scenario_config_validation_returns_canonical_defaults():
    assert validate_scenario_config("slay_the_spire", {}) == {
        "default_character": "IRONCLAD"
    }


def test_agent_manager_has_one_startup_definition_and_no_rebind_api():
    definition = create_scenario(
        "generic_mcp",
        mcp_url="http://mcp.invalid",
        scenario_config={"scope_id": "first"},
    )
    manager = AgentManager(definition=definition)

    assert manager.current_runtime is not None
    assert manager.current_runtime.scenario_id == "first"
    assert not hasattr(manager, "configure_single_game")
    assert not hasattr(manager, "configure_scenario")


def test_event_assistant_builds_without_mcp_capability():
    definition = create_scenario(
        "event_assistant",
        mcp_url="",
        scenario_config={},
    )
    manager = AgentManager(definition=definition)

    assert definition.capability_resources == {}
    assert definition.spec.capabilities == ("events", "memory", "host_speech")
    assert manager.current_runtime is not None
    assert {item.source for item in manager.current_runtime.router.capabilities} == {
        "events",
        "memory",
    }
