"""Agent 记忆工具 — memorize / recall

供 GameGraph / HostGraph 的 LLM 调用
"""

from __future__ import annotations

import logging
from typing import Any

from apps.ai.memory.atom import AtomType, MemoryAtom
from apps.ai.memory.engine import get_memory_engine

logger = logging.getLogger(__name__)


def get_memory_tools() -> list[dict]:
    """返回 memorize / recall 工具定义 (OpenAI function calling 格式)"""
    return [
        {
            "type": "function",
            "function": {
                "name": "memorize",
                "description": "记住一条重要信息，跨局保留。用于记录游戏规律、观众偏好、互动事件等。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "content": {
                            "type": "string",
                            "description": "要记住的内容",
                        },
                        "memory_type": {
                            "type": "string",
                            "enum": [
                                "game_mechanic",
                                "game_lore",
                                "viewer_preference",
                                "viewer_fact",
                                "viewer_relation",
                                "host_personality",
                                "episodic",
                                "factual",
                            ],
                            "description": "记忆类型",
                        },
                        "importance": {
                            "type": "number",
                            "description": "重要性 0-1，默认 0.5",
                            "default": 0.5,
                        },
                        "entities": {
                            "type": "array",
                            "items": {"type": "string"},
                            "description": "相关实体名称列表",
                            "default": [],
                        },
                    },
                    "required": ["content", "memory_type"],
                },
            },
        },
        {
            "type": "function",
            "function": {
                "name": "recall",
                "description": "回忆之前记住的信息。用于查询游戏知识、观众偏好等。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {
                            "type": "string",
                            "description": "要回忆的内容关键词",
                        },
                        "memory_type": {
                            "type": "string",
                            "enum": [
                                "game_mechanic",
                                "game_lore",
                                "viewer_preference",
                                "viewer_fact",
                                "viewer_relation",
                                "host_personality",
                                "episodic",
                                "factual",
                            ],
                            "description": "限定记忆类型 (可选)",
                        },
                        "k": {
                            "type": "integer",
                            "description": "返回条数，默认 3",
                            "default": 3,
                        },
                    },
                    "required": ["query"],
                },
            },
        },
    ]


async def handle_memory_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    game_id: str | None = None,
    user_id: str | None = None,
) -> str:
    """处理 Agent 的记忆工具调用"""
    engine = get_memory_engine()

    if tool_name == "memorize":
        try:
            atom_type = AtomType(arguments.get("memory_type", "factual"))
        except ValueError:
            atom_type = AtomType.FACTUAL

        atom = MemoryAtom(
            atom_type=atom_type,
            content=arguments["content"],
            entities=arguments.get("entities", []),
            importance=min(1.0, max(0.0, float(arguments.get("importance", 0.5)))),
            confidence=0.7,
            game_id=game_id,
            user_id=user_id,
        )

        atom_id = await engine.add_atom(atom)

        # 如果是游戏知识类型，同步到知识图谱
        if atom_type in (AtomType.GAME_MECHANIC, AtomType.GAME_LORE) and game_id:
            graph = await engine.ensure_graph(game_id)
            # 简单: 把记忆内容作为 mechanic 节点
            for entity in atom.entities:
                await graph.add_node(
                    node_type="mechanic" if atom_type == AtomType.GAME_MECHANIC else "lore",
                    name=entity,
                    properties={"source": atom.content, "importance": atom.importance},
                )

        return f"已记住 (id={atom_id})"

    elif tool_name == "recall":
        try:
            atom_type = AtomType(arguments.get("memory_type", "")) if arguments.get("memory_type") else None
        except ValueError:
            atom_type = None

        results = await engine.recall(
            query=arguments["query"],
            k=int(arguments.get("k", 3)),
            game_id=game_id,
            user_id=user_id,
            atom_types=[atom_type] if atom_type else None,
        )

        if not results:
            return "没有找到相关记忆"

        lines = []
        for i, atom in enumerate(results, 1):
            score = atom.metadata.get("final_score", 0)
            lines.append(f"{i}. [{atom.atom_type.value}] {atom.content} (相关度: {score:.2f})")
        return "\n".join(lines)

    return "未知工具"


__all__ = ["get_memory_tools", "handle_memory_tool_call"]
