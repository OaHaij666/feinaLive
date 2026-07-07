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
        def _normalize(val):
            s = str(val)
            upper = s.upper()
            # 仅当大写后命中原生 4 角色时才统一大写；mod class 名（PascalCase）保持原样
            return upper if upper in SlayTheSpireAdapter.CHARACTERS else s

        if "character" in params:
            params["character"] = _normalize(params["character"])
            return params
        for alias in ("character_index", "role", "class", "char"):
            if alias in params:
                val = params[alias]
                if isinstance(val, int):
                    idx = val
                    chars = SlayTheSpireAdapter.CHARACTERS
                    params["character"] = chars[idx] if 0 <= idx < len(chars) else chars[0]
                else:
                    params["character"] = _normalize(val)
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

    async def get_initial_state(self) -> dict | None:
        """start_game 之后调：从 MCP 拉初始牌组/遗物/角色，含具体数值与效果描述。

        返回结构:
        {
            "character": "Wishdell_Mod",     # MCP 原始 class 字段
            "deck_cards": [
                {"id": "Wishdell:Strike", "name": "打击", "count": 5,
                 "cost": 1, "type": "ATTACK", "base_damage": 6, "base_block": None, "base_magic_number": None,
                 "description": "...", "upgraded": {...} | None},
                ...
            ],
            "relics": [
                {"id": "Wishdell:Avenger", "name": "复仇者", "tier": "STARTER",
                 "description": "...", "counter_type": "none"},
                ...
            ],
        }
        """
        try:
            state = await self.get_state()
        except Exception as e:
            logger.error(f"get_initial_state: get_state 失败: {e}")
            return None

        raw = state.raw_state or {}
        character = raw.get("class", "") or ""

        # 1. 牌组：合并相同 id 的牌，统计 count
        from collections import Counter
        raw_deck = raw.get("deck", []) or []
        if not isinstance(raw_deck, list):
            return None

        card_id_counts: Counter = Counter()
        for c in raw_deck:
            if not isinstance(c, dict):
                continue
            cid = c.get("id")
            if cid:
                card_id_counts[cid] += 1

        # 2. 批量查牌详情
        deck_cards: list[dict] = []
        if card_id_counts:
            try:
                card_info = await self._mcp.call_tool(
                    "get_card_info", {"card_ids": list(card_id_counts.keys())}
                )
            except Exception as e:
                logger.warning(f"get_card_info 失败: {e}")
                card_info = None
            card_info = self._unwrap_tool_result(card_info) if card_info else None
            info_map: dict[str, dict] = {}
            if isinstance(card_info, dict):
                for item in card_info.get("cards", []) or []:
                    if isinstance(item, dict) and "error" not in item and item.get("id"):
                        info_map[item["id"]] = item

            for cid, cnt in card_id_counts.items():
                info = info_map.get(cid, {})
                deck_cards.append({
                    "id": cid,
                    "name": info.get("name", cid),
                    "count": cnt,
                    "cost": info.get("cost"),
                    "type": info.get("type", ""),
                    "base_damage": info.get("base_damage"),
                    "base_block": info.get("base_block"),
                    "base_magic_number": info.get("base_magic_number"),
                    "description": info.get("description", ""),
                    "upgraded": info.get("upgraded"),
                })

        # 3. 遗物：批量查
        raw_relics = raw.get("relics", []) or []
        relics: list[dict] = []
        relic_ids = [r.get("id") for r in raw_relics if isinstance(r, dict) and r.get("id")]
        relic_info_map: dict[str, dict] = {}
        if relic_ids:
            try:
                relic_info = await self._mcp.call_tool(
                    "get_relic_info", {"relic_ids": relic_ids}
                )
            except Exception as e:
                logger.warning(f"get_relic_info 失败: {e}")
                relic_info = None
            relic_info = self._unwrap_tool_result(relic_info) if relic_info else None
            if isinstance(relic_info, dict):
                for item in relic_info.get("relics", []) or []:
                    if isinstance(item, dict) and "error" not in item and item.get("id"):
                        relic_info_map[item["id"]] = item

        for r in raw_relics:
            if not isinstance(r, dict):
                continue
            rid = r.get("id", "")
            info = relic_info_map.get(rid, {})
            relics.append({
                "id": rid,
                "name": info.get("name", r.get("name", rid)),
                "tier": info.get("tier", ""),
                "description": info.get("description", ""),
                "counter_type": info.get("counter_type", "none"),
            })

        return {
            "character": character,
            "deck_cards": deck_cards,
            "relics": relics,
        }

    @staticmethod
    def format_initial_state_for_memory(initial: dict) -> str:
        """把 get_initial_state() 返回值格式化成可写入 important 记忆的文本。"""
        lines: list[str] = []
        char = initial.get("character", "") or "?"
        lines.append(f"角色: {char}")

        cards = initial.get("deck_cards", []) or []
        total = sum(c.get("count", 0) for c in cards)
        unique = len(cards)
        lines.append(f"牌组 ({total}张, {unique}种):")

        def _card_stats(c: dict) -> str:
            parts: list[str] = []
            if c.get("cost") is not None:
                parts.append(f"{c['cost']}费")
            if c.get("type"):
                parts.append(c["type"])
            if c.get("base_damage") is not None:
                parts.append(f"伤害{c['base_damage']}")
            if c.get("base_block") is not None:
                parts.append(f"格挡{c['base_block']}")
            if c.get("base_magic_number") is not None:
                parts.append(f"效果值{c['base_magic_number']}")
            return ", ".join(parts) if parts else "?"

        for c in cards:
            name = c.get("name", c.get("id", "?"))
            cnt = c.get("count", 1)
            stats = _card_stats(c)
            desc = c.get("description", "") or ""
            line = f"  {cnt}x {name} ({stats})"
            if desc:
                line += f" - {desc}"
            lines.append(line)
            upg = c.get("upgraded")
            if isinstance(upg, dict) and upg.get("name"):
                upg_stats = []
                if upg.get("base_damage") is not None:
                    upg_stats.append(f"伤害{upg['base_damage']}")
                if upg.get("base_block") is not None:
                    upg_stats.append(f"格挡{upg['base_block']}")
                if upg.get("base_magic_number") is not None:
                    upg_stats.append(f"效果值{upg['base_magic_number']}")
                suffix = f" ({', '.join(upg_stats)})" if upg_stats else ""
                lines.append(f"    ↳ 升级{upg['name']}{suffix}: {upg.get('description', '')}")

        relics = initial.get("relics", []) or []
        if relics:
            lines.append(f"遗物 ({len(relics)}个):")
            for r in relics:
                tier = r.get("tier", "")
                tier_str = f" [{tier}]" if tier else ""
                desc = r.get("description", "") or ""
                lines.append(f"  - {r.get('name', r.get('id', '?'))}{tier_str} - {desc}")

        return "\n".join(lines)

    async def on_game_started(self, memory_writer) -> None:
        """开局成功后：从 MCP 拉初始牌组/遗物/角色，格式化成文本写入 important 记忆。

        memory_writer 是 BaseGameAdapter 协议传入的可调用对象: await memory_writer(text: str)
        """
        try:
            initial = await self.get_initial_state()
            if not initial:
                return
            text = self.format_initial_state_for_memory(initial)
            await memory_writer(text)
            card_total = sum(c.get("count", 0) for c in initial.get("deck_cards", []))
            logger.info(
                f"杀戮尖塔开局副作用: 已写入初始状态到 important 记忆 "
                f"({card_total}张牌, {len(initial.get('relics', []))}个遗物)"
            )
        except Exception as e:
            logger.warning(f"杀戮尖塔开局副作用失败: {e}")

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
            lines.append("敌人(索引从0开始):")
            for i, m in enumerate(monsters):
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
