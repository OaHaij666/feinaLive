"""通用 MCP 场景 Profile。

它只依赖 MCP 的工具描述和少量可配置字段，不包含任何具体游戏规则。
"""

from __future__ import annotations

import json
from typing import Any, cast

from pydantic import BaseModel, ConfigDict, Field

from apps.agent.scenarios.profile import (
    GameConfigField,
    ScenarioProfile,
    UnifiedAction,
    UnifiedGameState,
)
from apps.ai.mcp.client import MCPClient
from apps.ai.memory.game_memory import GameMemoryPolicy
from apps.config import config


class GenericGameConfig(BaseModel):
    model_config = ConfigDict(extra="forbid")

    scope_id: str = Field(default="generic_mcp", min_length=1, max_length=80)
    display_name: str = Field(default="通用 MCP 游戏", min_length=1, max_length=80)
    game_type: str = Field(default="generic", min_length=1, max_length=80)
    state_tool: str = Field(default="get_game_state", min_length=1, max_length=120)
    turn_field: str = Field(default="ready_for_command", min_length=1, max_length=160)
    session_start_tool: str = Field(default="", max_length=120)
    session_end_field: str = Field(default="", max_length=160)
    readonly_tools: str = Field(default="", max_length=2000)
    instructions: str = Field(default="", max_length=12000)


class GenericMCPScenarioProfile(ScenarioProfile):
    config_model = GenericGameConfig
    profile_id = "generic_mcp"
    catalog_name = "通用 MCP 游戏"
    catalog_description = "依靠 MCP 工具描述运行，不内置任何具体游戏规则。"
    catalog_game_type = "generic"
    config_fields = [
        GameConfigField(
            "scope_id",
            "记忆作用域 ID",
            default="generic_mcp",
            required=True,
            description="用于隔离会话、历史和知识图谱；保存后不要随意更改。",
        ),
        GameConfigField("display_name", "显示名称", default="通用 MCP 游戏", required=True),
        GameConfigField("game_type", "游戏类型", default="generic", required=True),
        GameConfigField(
            "state_tool",
            "状态工具",
            default="get_game_state",
            required=True,
            description="每轮获取完整游戏状态的 MCP tool 名。",
        ),
        GameConfigField(
            "turn_field",
            "可操作字段",
            default="ready_for_command",
            required=True,
            description="状态中该布尔字段为 true 时才允许 Agent 操作，支持点路径。",
        ),
        GameConfigField(
            "session_start_tool",
            "会话开始工具",
            default="",
            description="可选；成功执行该工具时新建记忆会话。",
        ),
        GameConfigField(
            "session_end_field",
            "会话结束字段",
            default="",
            description="可选；状态中该字段为 true 时结束当前记忆会话。",
        ),
        GameConfigField(
            "readonly_tools",
            "只读工具",
            input_type="textarea",
            default="",
            description="逗号或换行分隔；这些工具可在同轮并行查询，不按游戏动作处理。",
        ),
        GameConfigField(
            "instructions",
            "游戏规则与操作约束",
            input_type="textarea",
            default="",
            description="只填写 MCP 无法表达的稳定规则，不要粘贴瞬时状态。",
        ),
    ]

    @property
    def values(self) -> GenericGameConfig:
        return cast(GenericGameConfig, self.config)

    @property
    def game_id(self) -> str:
        return self.values.scope_id

    @property
    def display_name(self) -> str:
        return self.values.display_name

    @property
    def game_type(self) -> str:
        return self.values.game_type

    @property
    def prompt_guidance(self) -> str:
        base = super().prompt_guidance
        return f"{base}\n{self.values.instructions}" if self.values.instructions else base

    @property
    def memory_policy(self) -> GameMemoryPolicy:
        return GameMemoryPolicy(
            session_mode="continuous" if self.values.session_end_field == "" else "per_run",
            summary_threshold=config.agent_memory_threshold,
            idle_summary_seconds=config.agent_memory_idle_seconds,
            context_max_chars=config.agent_memory_context_max_chars,
        )

    @staticmethod
    def _unwrap(raw: Any) -> Any:
        if isinstance(raw, dict) and "content" in raw:
            for item in raw.get("content", []):
                if item.get("type") != "text":
                    continue
                text = item.get("text", "")
                try:
                    return json.loads(text)
                except (TypeError, json.JSONDecodeError):
                    return text
        return raw

    @staticmethod
    def _read_field(raw: dict[str, Any], path: str) -> Any:
        value: Any = raw
        for part in path.split("."):
            if not isinstance(value, dict):
                return None
            value = value.get(part)
        return value

    async def get_state(self, client: MCPClient) -> UnifiedGameState:
        raw = self._unwrap(await client.call_tool(self.values.state_tool))
        state = raw if isinstance(raw, dict) else {"value": raw}
        player = state.get("player", {}) if isinstance(state.get("player"), dict) else {}
        enemies = state.get("enemies", []) if isinstance(state.get("enemies"), list) else []
        actions = state.get("available_actions", [])
        return UnifiedGameState(
            game_id=self.game_id,
            game_type=self.game_type,
            player=player,
            enemies=enemies,
            available_actions=actions if isinstance(actions, list) else [],
            turn_info=state.get("turn_info", {}) if isinstance(state.get("turn_info"), dict) else {},
            screen_type=str(state.get("screen_type") or state.get("phase") or ""),
            game_specific=state.get("game_specific", {}) if isinstance(state.get("game_specific"), dict) else {},
            raw_state=state,
        )

    async def execute_action(
        self, client: MCPClient, action: UnifiedAction
    ) -> tuple[bool, str]:
        try:
            result = await client.call_tool(action.action_type, action.params)
        except Exception as exc:
            return False, str(exc)
        if result is None:
            return False, f"{action.action_type} returned None"
        if isinstance(result, dict) and result.get("isError"):
            messages = [
                str(item.get("text", ""))
                for item in result.get("content", [])
                if item.get("type") == "text"
            ]
            return False, "; ".join(filter(None, messages)) or "MCP tool error"
        return True, ""

    async def query_tool(
        self, client: MCPClient, name: str, params: dict | None = None
    ) -> Any:
        return self._unwrap(await client.call_tool(name, params or {}))

    async def get_available_actions(self, client: MCPClient) -> list[UnifiedAction]:
        return [
            UnifiedAction(action_type=item.get("name", ""), description=item.get("description", ""))
            for item in await client.get_tools()
            if item.get("name")
        ]

    def is_my_turn(self, state: UnifiedGameState) -> bool:
        return self._read_field(state.raw_state, self.values.turn_field) is True

    def is_session_finished(self, state: UnifiedGameState) -> bool:
        return bool(
            self.values.session_end_field
            and self._read_field(state.raw_state, self.values.session_end_field) is True
        )

    def is_readonly_tool(self, name: str) -> bool:
        names = {
            item.strip()
            for item in self.values.readonly_tools.replace(",", "\n").splitlines()
            if item.strip()
        }
        return name in names

    def is_session_start_action(self, action: UnifiedAction) -> bool:
        return bool(
            self.values.session_start_tool
            and action.action_type == self.values.session_start_tool
        )
