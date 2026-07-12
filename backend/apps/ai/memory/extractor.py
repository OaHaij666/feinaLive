"""Extract durable game knowledge from game actions.

Viewer atoms are created only by the batched interaction summarizer so that
single-turn extraction and cross-turn synthesis cannot compete.
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

返回 JSON 数组，每条记忆包含可规范化的关系:
[{{"content": "记忆内容", "type": "game_mechanic 或 game_lore", "importance": 0.0-1.0, "entities": ["相关实体"], "relations": [{{"subject":"实体A","predicate":"synergizes_with","object":"实体B"}}]}}]

如果没有值得长期记住的内容，返回空数组 []"""

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
                metadata={"relations": fact.get("relations", [])},
            ))
        return atoms

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
