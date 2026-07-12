"""Scenario protocol semantics and the normalized state/action contract."""

import logging
from abc import ABC, abstractmethod
from dataclasses import asdict, dataclass, field
from typing import Any

from pydantic import BaseModel, ConfigDict

from apps.ai.mcp.client import MCPClient
from apps.ai.memory.game_memory import GameMemoryAPI, GameMemoryPolicy

logger = logging.getLogger(__name__)


@dataclass(frozen=True, slots=True)
class GameConfigField:
    key: str
    label: str
    input_type: str = "text"
    default: Any = ""
    description: str = ""
    required: bool = False
    options: list[dict[str, str]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass
class UnifiedGameState:
    game_id: str = ""
    game_type: str = ""
    player: dict = field(default_factory=dict)
    enemies: list[dict] = field(default_factory=list)
    available_actions: list[dict] = field(default_factory=list)
    turn_info: dict = field(default_factory=dict)
    screen_type: str = ""
    game_specific: dict = field(default_factory=dict)
    raw_state: dict = field(default_factory=dict)

    def to_prompt_text(self) -> str:
        lines = [f"游戏: {self.game_id} | 画面: {self.screen_type}"]

        if self.player:
            hp = self.player.get("hp", "?")
            max_hp = self.player.get("max_hp", "?")
            resources = self.player.get("resources", {})
            lines.append(f"玩家: HP {hp}/{max_hp}")
            if resources:
                lines.append(f"资源: {resources}")

        if self.enemies:
            lines.append("敌人:")
            for e in self.enemies:
                name = e.get("name", "未知")
                hp = e.get("hp", "?")
                max_hp = e.get("max_hp", "?")
                intent = e.get("intent", "")
                lines.append(f"  - {name}: HP {hp}/{max_hp} 意图: {intent}")

        if self.available_actions:
            lines.append("可用动作:")
            for a in self.available_actions:
                lines.append(f"  - {a.get('type', '?')}: {a.get('description', '')}")

        if self.turn_info:
            is_player = self.turn_info.get("is_player_turn", True)
            turn_num = self.turn_info.get("turn_number", 0)
            lines.append(f"回合: {turn_num} ({'玩家回合' if is_player else '敌方回合'})")

        if self.game_specific:
            for key, value in self.game_specific.items():
                if isinstance(value, list):
                    lines.append(f"{key}: {', '.join(str(v) for v in value[:10])}")
                else:
                    lines.append(f"{key}: {value}")

        return "\n".join(lines)


@dataclass
class UnifiedAction:
    action_type: str = ""
    params: dict = field(default_factory=dict)
    description: str = ""


class EmptyGameConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")


class ScenarioProfile(ABC):
    config_model: type[BaseModel] = EmptyGameConfig
    profile_id: str = ""
    catalog_name: str = ""
    catalog_description: str = ""
    catalog_game_type: str = "generic"
    config_fields: list[GameConfigField] = []

    def __init__(self, values: dict[str, Any] | None = None):
        self.config = self.config_model.model_validate(values or {})

    @classmethod
    def catalog_entry(cls) -> dict[str, Any]:
        return {
            "scenario_id": cls.profile_id,
            "display_name": cls.catalog_name,
            "description": cls.catalog_description,
            "category": cls.catalog_game_type,
            "config_fields": [item.to_dict() for item in cls.config_fields],
        }

    @property
    @abstractmethod
    def game_id(self) -> str: ...

    @property
    @abstractmethod
    def game_type(self) -> str: ...

    @property
    def display_name(self) -> str:
        return self.game_id

    @property
    def prompt_guidance(self) -> str:
        return (
            "依据 MCP 返回的当前状态和工具定义谨慎操作。"
            "不要假设未在状态、工具说明或记忆中出现的游戏规则；信息不足时优先查询。"
        )

    @property
    def prompt_examples(self) -> str:
        return (
            '{"tool_calls":[{"function":{"name":"request_commentary",'
            '"arguments":{"event_summary":"说明当前决策","reason":"关键节点",'
            '"sync":"on_speech_start"}}},{"function":{"name":"mcp__<工具名>",'
            '"arguments":{}}}]}'
        )

    @abstractmethod
    async def get_state(self, client: MCPClient) -> UnifiedGameState: ...

    @abstractmethod
    async def execute_action(
        self, client: MCPClient, action: UnifiedAction
    ) -> tuple[bool, str]: ...

    @abstractmethod
    async def get_available_actions(self, client: MCPClient) -> list[UnifiedAction]: ...

    @abstractmethod
    def is_my_turn(self, state: UnifiedGameState) -> bool: ...

    async def get_tools_definition(self, client: MCPClient) -> list[dict]:
        return [
            {
                "type": "function",
                "function": {
                    "name": item["name"],
                    "description": item.get("description", ""),
                    "parameters": item.get(
                        "inputSchema", {"type": "object", "properties": {}}
                    ),
                },
            }
            for item in await client.get_tools()
            if item.get("name")
        ]

    async def query_tool(
        self, client: MCPClient, name: str, params: dict | None = None
    ) -> Any:
        """执行无副作用查询工具并返回原始数据。"""
        success, message = await self.execute_action(
            client,
            UnifiedAction(action_type=name, params=params or {})
        )
        return {"success": success, "message": message}

    @property
    def memory_policy(self) -> GameMemoryPolicy:
        """Declare memory lifecycle without teaching AgentGraph scene semantics."""
        return GameMemoryPolicy()

    def is_session_finished(self, state: UnifiedGameState) -> bool:
        """Profiles may map an MCP-specific state to a generic session boundary."""
        return False

    def session_end_event(self, state: UnifiedGameState) -> dict[str, Any]:
        return {
            "source": "profile",
            "screen_type": state.screen_type,
            "game_type": state.game_type,
        }

    def session_restart_actions(self, state: UnifiedGameState) -> list[UnifiedAction]:
        """Return safe actions used after a detected session end.

        Unknown games do not restart automatically. Specific adapters may opt in.
        """
        return []

    def is_readonly_tool(self, name: str) -> bool:
        return False

    def expand_action(self, action: UnifiedAction) -> list[UnifiedAction]:
        return [action]

    def is_session_start_action(self, action: UnifiedAction) -> bool:
        return False

    def format_state_for_prompt(self, raw: dict, fallback: str) -> str:
        """将原始游戏状态格式化为 prompt 文本。

        默认实现尝试使用 UnifiedGameState.to_prompt_text()；
        如果 raw 不是有效的状态字典，则返回 fallback。
        """
        if not raw:
            return fallback
        try:
            state = UnifiedGameState(
                game_id=raw.get("game_id", self.game_id),
                game_type=raw.get("game_type", self.game_type),
                player=raw.get("player", {}),
                enemies=raw.get("enemies", []),
                available_actions=raw.get("available_actions", []),
                turn_info=raw.get("turn_info", {}),
                screen_type=raw.get("screen_type", ""),
                game_specific=raw.get("game_specific", {}),
                raw_state=raw,
            )
            return state.to_prompt_text()
        except Exception:
            return fallback

    async def health_check(self, client: MCPClient) -> bool:
        if await client.health_check():
            return True
        return bool(await client.get_tools(force_refresh=True))

    async def on_game_session_opened(
        self, client: MCPClient, memory: GameMemoryAPI
    ) -> None:
        """Trusted profile hook with a game-scoped, non-graph-writing API."""
        return None
