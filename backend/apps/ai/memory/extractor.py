"""记忆提取器 — 从 Agent 动作中提取长期记忆原子

游戏动作 → GAME_MECHANIC / GAME_LORE
弹幕互动 → VIEWER_PREFERENCE / VIEWER_FACT / VIEWER_RELATION / EPISODIC
"""

from __future__ import annotations

import json
import logging
from typing import Any

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.memory.atom import AtomType, MemoryAtom
from apps.config import config

logger = logging.getLogger(__name__)

# 游戏动作记忆提取 prompt
_GAME_EXTRACT_PROMPT = """分析以下游戏动作，提取跨局有效的游戏核心规律。

游戏: {game_id}
动作: {action}
结果: {result}
当前状态: {state_summary}

请提取:
1. 游戏机制规律 (如卡牌协同、遗物配合、敌人弱点等)
2. 游戏背景知识 (如角色特性、事件规则等)

注意: 只提取跨局有效的知识，不要提取单局战术/牌组/事件。

返回 JSON 数组，每条记忆:
[{{"content": "记忆内容", "type": "game_mechanic 或 game_lore", "importance": 0.0-1.0, "entities": ["相关实体"]}}]

如果没有值得长期记住的内容，返回空数组 []"""

# 弹幕互动记忆提取 prompt
_INTERACTION_EXTRACT_PROMPT = """分析以下弹幕互动，提取关于观众的信息。

观众ID: {user_id}
弹幕: {danmaku}
主播回复: {reply}

请提取:
1. 观众偏好 (如喜欢什么游戏风格)
2. 观众事实 (如是老粉、喜欢某个角色等)
3. 观众关系 (如和其他观众的关系)
4. 互动事件 (如有趣的对话)

返回 JSON 数组，每条记忆:
[{{"content": "记忆内容", "type": "viewer_preference/viewer_fact/viewer_relation/episodic", "importance": 0.0-1.0, "entities": ["相关实体"]}}]

如果没有值得记住的内容，返回空数组 []"""


class MemoryExtractor:
    """从 Agent 动作中提取长期记忆原子"""

    def __init__(self, config_dict: dict[str, Any] | None = None):
        self._config = config_dict or {}

    async def extract(
        self,
        source: str,
        content: str,
        context: dict[str, Any] | None = None,
    ) -> list[MemoryAtom]:
        ctx = context or {}
        if source == "game_action":
            return await self._extract_from_game(content, ctx)
        elif source == "interaction":
            return await self._extract_from_interaction(content, ctx)
        elif source == "danmaku":
            return await self._extract_from_danmaku(content, ctx)
        return []

    async def _extract_from_game(self, content: str, context: dict) -> list[MemoryAtom]:
        prompt = _GAME_EXTRACT_PROMPT.format(
            game_id=context.get("game_id", "unknown"),
            action=context.get("action", content),
            result=context.get("result", ""),
            state_summary=context.get("state_summary", ""),
        )
        facts = await self._llm_extract(prompt)
        atoms = []
        for fact in facts:
            atom_type_str = fact.get("type", "game_mechanic")
            try:
                atom_type = AtomType(atom_type_str)
            except ValueError:
                atom_type = AtomType.GAME_MECHANIC
            if atom_type not in (AtomType.GAME_MECHANIC, AtomType.GAME_LORE):
                continue
            atoms.append(MemoryAtom(
                atom_type=atom_type,
                content=fact.get("content", ""),
                entities=fact.get("entities", []),
                importance=min(1.0, max(0.0, float(fact.get("importance", 0.5)))),
                confidence=0.7,
                game_id=context.get("game_id"),
            ))
        return atoms

    async def _extract_from_interaction(self, content: str, context: dict) -> list[MemoryAtom]:
        prompt = _INTERACTION_EXTRACT_PROMPT.format(
            user_id=context.get("user_id", "unknown"),
            danmaku=context.get("danmaku", content),
            reply=context.get("reply", ""),
        )
        facts = await self._llm_extract(prompt)
        atoms = []
        for fact in facts:
            atom_type_str = fact.get("type", "episodic")
            try:
                atom_type = AtomType(atom_type_str)
            except ValueError:
                atom_type = AtomType.EPISODIC
            atoms.append(MemoryAtom(
                atom_type=atom_type,
                content=fact.get("content", ""),
                entities=fact.get("entities", []),
                importance=min(1.0, max(0.0, float(fact.get("importance", 0.5)))),
                confidence=0.7,
                user_id=context.get("user_id"),
            ))
        return atoms

    async def _extract_from_danmaku(self, content: str, context: dict) -> list[MemoryAtom]:
        return await self._extract_from_interaction(content, context)

    async def _llm_extract(self, prompt: str) -> list[dict]:
        """调用 LLM 提取结构化事实"""
        ai = get_ai_client()
        if not ai.available:
            return []

        messages = [ChatMessage(role="user", content=prompt)]
        request = ChatRequest(
            messages=messages,
            model=config.llm_model,
            temperature=0.2,
            max_tokens=500,
        )

        try:
            response = await ai.chat(request)
            if not response or not response.content:
                return []

            text = response.content.strip()
            # 尝试提取 JSON 数组
            if "[" in text:
                start = text.index("[")
                end = text.rindex("]") + 1
                json_str = text[start:end]
                facts = json.loads(json_str)
                if isinstance(facts, list):
                    return [f for f in facts if isinstance(f, dict) and f.get("content")]
            return []
        except Exception as e:
            logger.warning(f"LLM 记忆提取失败: {e}")
            return []


__all__ = ["MemoryExtractor"]
