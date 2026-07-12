"""Read-only memory tools exposed to the game decision agent."""

from __future__ import annotations

from typing import Any

from apps.ai.memory.atom import AtomType
from apps.ai.memory.engine import get_memory_engine


def get_memory_tools(*, read_only: bool = True) -> list[dict]:
    """Return only recall; durable writes belong to the summary pipeline."""
    return [
        {
            "type": "function",
            "function": {
                "name": "recall",
                "description": "查询系统已经验证并保存的游戏经验。此工具只读。",
                "parameters": {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string", "description": "要查询的关键词"},
                        "memory_type": {
                            "type": "string",
                            "enum": ["game_mechanic", "game_lore"],
                            "description": "可选的游戏知识类型",
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
        }
    ]


async def handle_memory_tool_call(
    tool_name: str,
    arguments: dict[str, Any],
    game_id: str | None = None,
    user_id: str | None = None,
) -> str:
    if tool_name != "recall":
        return "该记忆工具为只读，写入由自动总结管线负责"
    try:
        atom_type = (
            AtomType(arguments["memory_type"])
            if arguments.get("memory_type")
            else None
        )
    except ValueError:
        atom_type = None
    results = await get_memory_engine().recall(
        query=str(arguments.get("query", "")),
        k=max(1, min(10, int(arguments.get("k", 3)))),
        game_id=game_id,
        user_id=user_id,
        atom_types=[atom_type] if atom_type else None,
    )
    if not results:
        return "没有找到相关记忆"
    return "\n".join(
        f"{index}. [{atom.atom_type.value}] {atom.content}"
        for index, atom in enumerate(results, 1)
    )


__all__ = ["get_memory_tools", "handle_memory_tool_call"]
