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

    async def health_check(self) -> bool:
        return False
