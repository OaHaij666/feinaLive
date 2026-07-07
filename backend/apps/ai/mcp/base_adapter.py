"""MCP 游戏适配器 - 抽象基类与统一状态格式"""

import logging
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from typing import Any

logger = logging.getLogger(__name__)


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


class BaseGameAdapter(ABC):
    @property
    @abstractmethod
    def game_id(self) -> str: ...

    @property
    @abstractmethod
    def game_type(self) -> str: ...

    @abstractmethod
    async def get_state(self) -> UnifiedGameState: ...

    @abstractmethod
    async def execute_action(self, action: UnifiedAction) -> tuple[bool, str]: ...

    @abstractmethod
    async def get_available_actions(self) -> list[UnifiedAction]: ...

    @abstractmethod
    def is_my_turn(self, state: UnifiedGameState) -> bool: ...

    @abstractmethod
    async def get_tools_definition(self) -> list[dict]: ...

    async def query_tool(self, name: str, params: dict | None = None) -> Any:
        """执行无副作用查询工具并返回原始数据。"""
        success, message = await self.execute_action(
            UnifiedAction(action_type=name, params=params or {})
        )
        return {"success": success, "message": message}

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

    async def health_check(self) -> bool:
        """默认健康检查：通过 MCP client 检查。

        子类可覆盖此方法提供自定义健康检查逻辑。
        """
        if hasattr(self, "_mcp_client") and self._mcp_client:
            return await self._mcp_client.health_check()
        return False

    async def on_game_started(self, memory_writer) -> None:
        """新游戏成功开始后的钩子。默认无操作。

        子类可重写以执行游戏特定的开局副作用（例如杀戮尖塔在开局后
        从 MCP 拉初始牌组/遗物写入 important 记忆）。

        Args:
            memory_writer: 可调用对象，接受一段文本，将其写入 important 记忆层。
                           协议: `await memory_writer(text: str) -> None`
        """
        return None
