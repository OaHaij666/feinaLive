"""显式 MCP 游戏注册表：运行时与控制台的唯一游戏目录。"""

from __future__ import annotations

from typing import Any

from pydantic import ValidationError

from apps.ai.mcp.adapter import MCPGameAdapter
from apps.ai.mcp.client import MCPClient
from apps.ai.mcp.games.base import GameProfile
from apps.ai.mcp.games.generic import GenericGameProfile
from apps.ai.mcp.games.slay_the_spire import SlayTheSpireProfile

_REGISTERED_GAMES: dict[str, type[GameProfile]] = {
    GenericGameProfile.profile_id: GenericGameProfile,
    SlayTheSpireProfile.profile_id: SlayTheSpireProfile,
}


def list_registered_games() -> list[dict[str, Any]]:
    return [profile.catalog_entry() for profile in _REGISTERED_GAMES.values()]


def validate_game_config(game_id: str, values: dict[str, Any] | None = None) -> dict[str, Any]:
    profile_type = _REGISTERED_GAMES.get(game_id)
    if profile_type is None:
        raise ValueError(f"未注册的 MCP 游戏: {game_id}")
    try:
        return profile_type.config_model.model_validate(values or {}).model_dump()
    except ValidationError as exc:
        raise ValueError(f"游戏配置无效: {exc}") from exc


def create_mcp_game(
    game_id: str,
    *,
    mcp_url: str,
    game_config: dict[str, Any] | None = None,
) -> MCPGameAdapter:
    profile_type = _REGISTERED_GAMES.get(game_id)
    if profile_type is None:
        raise ValueError(f"未注册的 MCP 游戏: {game_id}")
    profile = profile_type(validate_game_config(game_id, game_config))
    return MCPGameAdapter(MCPClient(base_url=mcp_url), profile)
