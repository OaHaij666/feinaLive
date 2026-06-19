"""记忆注入器 — 按 Agent 角色差异化注入记忆到 prompt

GameGraph: SessionMemory (全量) + LongTermMemory (游戏知识) + KnowledgeGraph (协同/克制)
HostGraph: LongTermMemory (观众记忆 + 主播人设 + 互动事件)
"""

from __future__ import annotations

import logging
from typing import Any

from apps.ai.memory.atom import AtomType
from apps.ai.memory.atom_store import AtomStore
from apps.ai.memory.graph_store import GameKnowledgeGraph
from apps.ai.memory.session_memory import SessionMemory

logger = logging.getLogger(__name__)


class MemoryInjector:
    """按 Agent 角色注入记忆到 prompt"""

    def __init__(self, store: AtomStore):
        self._store = store

    async def inject_for_game(
        self,
        session: SessionMemory,
        game_id: str,
        graph: GameKnowledgeGraph | None = None,
    ) -> str:
        """为 GameGraph 构建完整记忆上下文

        包含:
        1. SessionMemory (单局记忆，全量)
        2. LongTermMemory (游戏知识，FTS检索)
        3. KnowledgeGraph (协同/克制关系)
        """
        sections = []

        # 1. 单局记忆 — 全量拼接
        session_text = session.to_prompt_text()
        if session_text:
            sections.append(session_text)

        # 2. 长期游戏知识 — top 10
        game_knowledge = await self._store.search_fts(
            query="",
            limit=10,
            game_id=game_id,
            atom_types=[AtomType.GAME_MECHANIC, AtomType.GAME_LORE],
        )
        if game_knowledge:
            lines = [f"- {a.content}" for a in game_knowledge]
            sections.append("【游戏经验】\n" + "\n".join(lines))

        # 3. 知识图谱 — 查询当前牌组/遗物的协同关系
        if graph:
            graph_context = await self._build_graph_context(session, graph)
            if graph_context:
                sections.append(graph_context)

        return "\n\n".join(sections) if sections else ""

    async def inject_for_host(self, user_id: str | None = None) -> str:
        """为 HostGraph 构建记忆上下文

        包含:
        1. 主播人设 (HOST_PERSONALITY)
        2. 观众记忆 (VIEWER_FACT, VIEWER_PREFERENCE, VIEWER_RELATION)
        3. 最近互动 (EPISODIC)
        """
        sections = []

        # 主播人设
        personality = await self._store.search_fts(
            query="",
            limit=10,
            atom_types=[AtomType.HOST_PERSONALITY],
        )
        if personality:
            lines = [f"- {a.content}" for a in personality]
            sections.append("【关于自己】\n" + "\n".join(lines))

        # 观众记忆
        if user_id:
            viewer = await self._store.search_fts(
                query="",
                limit=5,
                user_id=user_id,
                atom_types=[AtomType.VIEWER_FACT, AtomType.VIEWER_PREFERENCE, AtomType.VIEWER_RELATION],
            )
            if viewer:
                lines = [f"- {a.content}" for a in viewer]
                sections.append("【关于这位观众】\n" + "\n".join(lines))

        # 最近互动
        recent = await self._store.search_fts(
            query="",
            limit=5,
            atom_types=[AtomType.EPISODIC],
        )
        if recent:
            lines = [f"- {a.content}" for a in recent]
            sections.append("【最近互动】\n" + "\n".join(lines))

        return "\n\n".join(sections) if sections else ""

    async def _build_graph_context(
        self,
        session: SessionMemory,
        graph: GameKnowledgeGraph,
    ) -> str:
        """从 SessionMemory 中提取当前牌组/遗物关键词，查询图谱"""
        # 从 important 层提取关键词 (通常包含牌组/遗物信息)
        keywords: list[str] = []
        for layer_text in [session.important, session.core]:
            if not layer_text:
                continue
            # 简单提取：查找【】中的关键词
            import re
            found = re.findall(r"【([^】]+)】", layer_text)
            keywords.extend(found[:5])

        if not keywords:
            return ""

        # 用关键词查询图谱
        all_names: list[str] = []
        for kw in keywords[:3]:
            results = await graph.search(kw, k=3)
            all_names.extend(r["name"] for r in results)

        if not all_names:
            return ""

        # 去重
        unique_names = list(dict.fromkeys(all_names))[:8]
        return await graph.get_related(unique_names)


__all__ = ["MemoryInjector"]
