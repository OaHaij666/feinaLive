from __future__ import annotations

import pytest

from apps.ai.game_graph import build_game_system_prompt
from apps.ai.game_manager import GameManager
from apps.ai.mcp.adapter import MCPGameAdapter
from apps.ai.mcp.games.base import UnifiedAction, UnifiedGameState
from apps.ai.mcp.games.registry import (
    create_mcp_game,
    list_registered_games,
    validate_game_config,
)
from apps.ai.shared_context import SharedContext


def test_registry_is_the_public_source_for_builtin_games():
    definitions = {item["game_id"]: item for item in list_registered_games()}

    assert set(definitions) == {"generic_mcp", "slay_the_spire"}
    assert definitions["generic_mcp"]["config_fields"]
    assert definitions["slay_the_spire"]["config_fields"][0]["key"] == "default_character"


def test_factory_applies_specific_game_configuration():
    adapter = create_mcp_game(
        "slay_the_spire",
        mcp_url="http://mcp.invalid",
        game_config={"default_character": "WATCHER"},
    )

    assert isinstance(adapter, MCPGameAdapter)
    actions = adapter.session_restart_actions(UnifiedGameState())
    assert [item.action_type for item in actions] == ["proceed", "start_game"]
    assert actions[-1].params == {"character": "WATCHER"}
    assert adapter.is_readonly_tool("get_card_info")
    assert adapter.is_session_start_action(UnifiedAction(action_type="start_game"))
    expanded = adapter.expand_action(
        UnifiedAction(
            action_type="execute_actions",
            params={"actions": [{"action": "play_card", "card_name": "防御"}, {"action": "end_turn"}]},
        )
    )
    assert [item.action_type for item in expanded] == ["play_card", "end_turn"]


def test_generic_profile_uses_configured_identity_and_safe_turn_gate():
    adapter = create_mcp_game(
        "generic_mcp",
        mcp_url="http://mcp.invalid",
        game_config={
            "scope_id": "my_game",
            "display_name": "My Game",
            "game_type": "strategy",
            "turn_field": "can_act",
            "session_end_field": "finished",
            "session_start_tool": "new_run",
            "readonly_tools": "inspect, lookup",
            "instructions": "Never spend the final resource.",
        },
    )

    assert isinstance(adapter, MCPGameAdapter)
    assert adapter.game_id == "my_game"
    assert adapter.display_name == "My Game"
    assert adapter.is_my_turn(UnifiedGameState(raw_state={"can_act": True}))
    assert not adapter.is_my_turn(UnifiedGameState(raw_state={}))
    assert adapter.is_session_finished(UnifiedGameState(raw_state={"finished": True}))
    assert adapter.is_session_start_action(UnifiedAction(action_type="new_run"))
    assert adapter.is_readonly_tool("lookup")
    assert "Never spend" in adapter.prompt_guidance


def test_unregistered_game_is_rejected():
    with pytest.raises(ValueError, match="未注册的 MCP 游戏"):
        create_mcp_game("missing", mcp_url="http://mcp.invalid")


def test_game_config_rejects_unknown_fields():
    with pytest.raises(ValueError, match="游戏配置无效"):
        create_mcp_game(
            "slay_the_spire",
            mcp_url="http://mcp.invalid",
            game_config={"unknown": True},
        )


def test_game_config_validation_returns_canonical_defaults():
    assert validate_game_config("slay_the_spire", {}) == {
        "default_character": "IRONCLAD"
    }


def test_generic_prompt_does_not_leak_slay_the_spire_rules():
    prompt = build_game_system_prompt(
        game_name="My Game",
        game_guidance="Only use declared MCP rules.",
        action_examples='{"actions":[]}',
    )

    assert "My Game" in prompt
    assert "Only use declared MCP rules" in prompt
    assert "杀戮尖塔" not in prompt
    assert "斩杀优先" not in prompt


def test_manager_enforces_one_configured_game():
    manager = GameManager(shared_context=SharedContext())
    first = create_mcp_game(
        "generic_mcp",
        mcp_url="http://mcp.invalid",
        game_config={"scope_id": "first"},
    )
    second = create_mcp_game(
        "generic_mcp",
        mcp_url="http://mcp.invalid",
        game_config={"scope_id": "second"},
    )

    manager.configure_single_game(first)
    manager.configure_single_game(second)

    assert manager.current_graph is not None
    assert manager.current_graph.game_id == "second"
