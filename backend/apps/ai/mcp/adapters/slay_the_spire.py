"""Slay the Spire MCP 适配器 — 包裹 MCPClient，实现 BaseGameAdapter"""

import asyncio
import json
import logging
from typing import Any

from apps.ai.mcp.base_adapter import BaseGameAdapter, UnifiedAction, UnifiedGameState
from apps.ai.mcp.client import MCPClient
from apps.ai.memory.engine import get_memory_engine
from apps.config import config

logger = logging.getLogger(__name__)


class SlayTheSpireAdapter(BaseGameAdapter):
    def __init__(self, base_url: str = ""):
        self._mcp = MCPClient(base_url=base_url or config.game_mcp_url)

    @property
    def game_id(self) -> str:
        return "slay_the_spire"

    @property
    def game_type(self) -> str:
        return "roguelike_card"

    CHARACTERS = ["IRONCLAD", "SILENT", "DEFECT", "WATCHER"]

    @staticmethod
    def _fix_start_game_params(params: dict) -> dict:
        if "character" in params:
            params["character"] = str(params["character"]).upper()
            return params
        for alias in ("character_index", "role", "class", "char"):
            if alias in params:
                val = params[alias]
                if isinstance(val, int):
                    idx = val
                    chars = SlayTheSpireAdapter.CHARACTERS
                    params["character"] = chars[idx] if 0 <= idx < len(chars) else chars[0]
                else:
                    params["character"] = str(val).upper()
                del params[alias]
                return params
        if not params.get("character"):
            params["character"] = "IRONCLAD"
        return params

    @staticmethod
    def _unwrap_tool_result(raw: Any) -> Any:
        if isinstance(raw, dict) and "content" in raw:
            for item in raw["content"]:
                if item.get("type") == "text":
                    text = item.get("text", "")
                    try:
                        return json.loads(text)
                    except json.JSONDecodeError:
                        return text
        return raw

    async def get_state(self) -> UnifiedGameState:
        try:
            raw = await self._mcp.call_tool("get_game_state")
            state = self._unwrap_tool_result(raw)
            if isinstance(state, dict) and "game_state" in state:
                gs = state.pop("game_state")
                state["_game_state"] = gs
                for k, v in gs.items():
                    if k not in state:
                        state[k] = v
            if isinstance(state, dict) and not state.get("screen_type"):
                screen_raw = await self._mcp.call_tool("get_screen_state")
                screen_state = self._unwrap_tool_result(screen_raw)
                if isinstance(screen_state, dict):
                    for k in ("screen_type", "screen_name", "room_phase", "room_type", "choice_list"):
                        if k in screen_state and k not in state:
                            state[k] = screen_state[k]
            if not isinstance(state, dict) or not state.get("screen_type"):
                cmds_raw = await self._mcp.call_tool("get_available_commands")
                cmds_state = self._unwrap_tool_result(cmds_raw)
                if isinstance(cmds_state, dict) and cmds_state.get("screen_type"):
                    if not isinstance(state, dict):
                        state = {}
                    for k in ("screen_type", "room_phase", "ready_for_command", "in_game"):
                        if k in cmds_state and k not in state:
                            state[k] = cmds_state[k]
            if isinstance(state, dict):
                return self._raw_to_unified(state)
            return self._raw_to_unified({})
        except Exception as e:
            logger.error(f"获取游戏状态异常: {e}")
            return self._raw_to_unified({})

    async def execute_action(self, action: UnifiedAction) -> tuple[bool, str]:
        try:
            params = dict(action.params)
            atype = action.action_type
            error_msg = ""

            if atype == "start_game":
                await self._mcp.call_tool("abandon_run")
                params = self._fix_start_game_params(params)
                result = await self._mcp.call_tool("start_game", params)
                success = result is not None
                if not success:
                    error_msg = f"start_game failed: {result}"
                else:
                    # 确保知识图谱初始化
                    try:
                        engine = get_memory_engine()
                        await engine.ensure_graph(self.game_id)
                    except Exception as e:
                        logger.debug(f"知识图谱初始化失败: {e}")
                return success, error_msg
            elif atype == "execute_actions":
                result = await self._mcp.call_tool("execute_actions", params)
            elif atype == "play_card":
                result = await self._mcp.call_tool("play_card", params)
            elif atype == "end_turn":
                result = await self._mcp.call_tool("end_turn", params)
            elif atype == "choose":
                result = await self._mcp.call_tool("choose", params)
            elif atype == "use_potion":
                result = await self._mcp.call_tool("use_potion", params)
            elif atype == "discard_potion":
                result = await self._mcp.call_tool("discard_potion", params)
            elif atype == "proceed":
                result = await self._mcp.call_tool("proceed", params)
            elif atype == "confirm":
                result = await self._mcp.call_tool("confirm", params)
            elif atype == "skip":
                result = await self._mcp.call_tool("skip", params)
            elif atype == "cancel":
                result = await self._mcp.call_tool("cancel", params)
            elif atype == "select_cards":
                result = await self._mcp.call_tool("select_cards", params)
            elif atype in ("get_screen_state", "get_game_state", "get_available_commands",
                           "get_card_info", "get_relic_info", "get_potion_info"):
                result = await self._mcp.call_tool(atype, params)
            elif atype == "abandon_run":
                result = await self._mcp.call_tool("abandon_run", params)
            elif atype == "save_game":
                result = await self._mcp.call_tool("save_game", params)
            else:
                logger.warning(f"未知动作类型: {atype}")
                return False, f"unknown action: {atype}"

            if isinstance(result, dict):
                if result.get("isError"):
                    texts = []
                    for item in result.get("content", []):
                        if item.get("type") == "text":
                            texts.append(item["text"])
                    error_msg = "; ".join(texts)
                    return False, error_msg
                if result.get("content"):
                    return True, ""
            if result is None:
                return False, f"{atype} returned None"

            return True, ""

        except Exception as e:
            logger.error(f"执行游戏动作失败 [{action.action_type}]: {e}")
            return False, str(e)

    async def get_available_actions(self) -> list[UnifiedAction]:
        commands = await self._mcp.call_tool("get_available_commands")
        if not commands:
            return []
        result = []
        for cmd in commands.get("available_tools", []):
            result.append(UnifiedAction(
                action_type=cmd.get("tool", ""),
                description=cmd.get("description", ""),
            ))
        return result

    def is_my_turn(self, state: UnifiedGameState) -> bool:
        screen = state.raw_state.get("screen_type", "")
        if screen == "GAME_OVER":
            return True
        ready = state.raw_state.get("ready_for_command", False)
        in_combat = state.raw_state.get("in_combat", screen == "NONE")
        can_proceed = state.raw_state.get("can_proceed", False)

        if not ready:
            return False

        return in_combat or screen in ("MAIN_MENU", "NONE", "MAP", "EVENT", "COMBAT_REWARD", "CARD_REWARD",
                                        "SHOP_SCREEN", "SHOP_ROOM", "REST", "BOSS_REWARD",
                                        "GRID", "HAND_SELECT") or can_proceed

    async def get_tools_definition(self) -> list[dict]:
        result = await self._mcp.get_tools()
        mcp_tools = result.get("tools", []) if isinstance(result, dict) else (result if isinstance(result, list) else [])
        openai_tools = []
        for t in mcp_tools:
            defn = {
                "type": "function",
                "function": {
                    "name": t["name"],
                    "description": t.get("description", ""),
                    "parameters": t.get("inputSchema", {"type": "object", "properties": {}}),
                },
            }
            openai_tools.append(defn)
        return openai_tools

    async def query_tool(self, name: str, params: dict | None = None) -> Any:
        raw = await self._mcp.call_tool(name, params or {})
        return self._unwrap_tool_result(raw)

    async def health_check(self) -> bool:
        try:
            result = await self._mcp.call_tool("get_game_state")
            return result is not None
        except Exception:
            return False

    def _raw_to_unified(self, raw: dict | None) -> UnifiedGameState:
        if not raw:
            return UnifiedGameState(game_id=self.game_id, game_type=self.game_type)

        combat = raw.get("combat_state", {})
        player_combat = combat.get("player", {})

        enemies = []
        for m in combat.get("monsters", []):
            move = m.get("move", {})
            enemies.append({
                "name": m.get("name", "未知"),
                "hp": m.get("current_hp", 0),
                "max_hp": m.get("max_hp", 0),
                "intent": m.get("intent", ""),
                "damage": move.get("damage") if move else None,
            })

        resources = {}
        energy = player_combat.get("current_energy", raw.get("current_energy"))
        if energy is not None:
            resources["energy"] = energy
        block = player_combat.get("block", 0)
        if block:
            resources["block"] = block

        player = {
            "hp": raw.get("current_hp", 0),
            "max_hp": raw.get("max_hp", 80),
        }

        turn_info = {
            "is_player_turn": raw.get("ready_for_command", True),
            "turn_number": raw.get("floor", 0),
            "resources": resources if resources else {},
        }

        game_specific = {
            "screen_type": raw.get("screen_type", ""),
            "room_phase": raw.get("room_phase", ""),
            "hand": [c.get("name", "") for c in combat.get("hand", [])],
            "choices": raw.get("choice_list", []),
            "gold": raw.get("gold", 0),
        }

        return UnifiedGameState(
            game_id=self.game_id,
            game_type=self.game_type,
            player=player,
            enemies=enemies,
            turn_info=turn_info,
            screen_type=raw.get("screen_type", ""),
            game_specific=game_specific,
            raw_state=raw,
        )

    def format_state_for_prompt(self, raw: dict, fallback: str) -> str:
        lines = []
        screen = raw.get("screen_type", "?")
        floor = raw.get("floor", "?")
        hp = raw.get("current_hp", "?")
        max_hp = raw.get("max_hp", "?")

        lines.append(f"画面: {screen} | 楼层: {floor}")
        lines.append(f"HP: {hp}/{max_hp}")

        combat = raw.get("combat_state", {})
        player_combat = combat.get("player", {})
        energy = player_combat.get("current_energy", raw.get("current_energy", raw.get("energy")))
        if energy is not None:
            lines.append(f"费用: {energy}")

        monsters = combat.get("monsters", raw.get("monsters", []))
        if monsters:
            lines.append("敌人:")
            for i, m in enumerate(monsters, 1):
                if m.get("is_gone"):
                    continue
                intent = m.get("intent", "?")
                move = m.get("move", {})
                damage = move.get("damage") if move else None
                hits = move.get("hits", "") if move else ""
                intent_detail = intent
                if damage:
                    intent_detail += f" {damage}"
                    if hits and hits > 1:
                        intent_detail += f"x{hits}"
                block = m.get("block", 0)
                block_str = f" [格挡{block}]" if block else ""
                lines.append(f"  [{i}] {m.get('name')} HP:{m.get('current_hp')}/{m.get('max_hp')} 意图:{intent_detail}{block_str}")

        hand = combat.get("hand", raw.get("hand", []))
        if hand:
            lines.append("手牌:")
            for i, c in enumerate(hand, 1):
                playable = "可出" if c.get("is_playable") else "不可出"
                target = " 需目标" if c.get("has_target") else ""
                lines.append(f"  {i}. {c.get('name')} 费{c.get('cost')} {playable}{target}")

        choices = raw.get("choice_list", [])
        if choices:
            lines.append("选项:")
            for i, ch in enumerate(choices, 1):
                lines.append(f"  {i}. {ch}")

        return "\n".join(lines)

    async def ingest_game_state_to_graph(self, state: UnifiedGameState) -> int:
        """从当前游戏状态提取知识图谱节点

        提取: 手牌、遗物、敌人 → 图谱节点
        """
        try:
            engine = get_memory_engine()
            graph = await engine.ensure_graph(self.game_id)
        except Exception as e:
            logger.debug(f"知识图谱不可用: {e}")
            return 0

        items = []
        raw = state.raw_state

        # 手牌 → card 节点
        combat = raw.get("combat_state", {})
        for card in combat.get("hand", []):
            name = card.get("name", "")
            if name:
                items.append({
                    "type": "node",
                    "node_type": "card",
                    "name": name,
                    "properties": {
                        "cost": card.get("cost"),
                        "type": card.get("type", ""),
                        "rarity": card.get("rarity", ""),
                    },
                })

        # 遗物 → relic 节点
        for relic in raw.get("relics", []):
            name = relic.get("name", "") if isinstance(relic, dict) else str(relic)
            if name:
                items.append({
                    "type": "node",
                    "node_type": "relic",
                    "name": name,
                    "properties": {},
                })

        # 敌人 → enemy 节点
        for enemy in state.enemies:
            name = enemy.get("name", "")
            if name:
                items.append({
                    "type": "node",
                    "node_type": "enemy",
                    "name": name,
                    "properties": {
                        "hp": enemy.get("hp"),
                        "max_hp": enemy.get("max_hp"),
                        "intent": enemy.get("intent", ""),
                    },
                })

        if items:
            return await graph.ingest(items)
        return 0
