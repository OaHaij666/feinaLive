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
        session_text = f"{session.important} {session.core}".lower()
        if not session_text.strip():
            return ""

        # 方案1：从图谱已有节点名中反向匹配 SessionMemory 文本
        all_node_names = await graph.get_all_node_names()
        relevant = [n for n in all_node_names if n.lower() in session_text]

        # 方案2：从 SessionMemory 文本中解析牌组/遗物实体名，去图谱确认
        extracted = self._extract_entity_names(session_text)
        for name in extracted:
            if name not in (n.lower() for n in relevant):
                results = await graph.search(name, k=1)
                relevant.extend(r["name"] for r in results)

        # 去重，取前 8 个
        unique_names: list[str] = []
        seen = set()
        for name in relevant:
            key = name.lower()
            if key not in seen:
                unique_names.append(name)
                seen.add(key)
        unique_names = unique_names[:8]

        if not unique_names:
            return ""

        return await graph.get_related(unique_names)

    @staticmethod
    def _extract_entity_names(text: str) -> list[str]:
        """从记忆文本中解析牌组/遗物实体名"""
        import re

        names: list[str] = []

        # 牌组:xxx+yyy+zzz 格式 (request_memory_update 产生的)
        for match in re.finditer(r"牌组[:：]\s*(.+)", text):
            cards = re.split(r"[+、,，\s]+", match.group(1))
            names.extend(
                c.strip()
                for c in cards
                if c.strip() and not re.match(r"^\d+x?\d*$", c.strip())
            )

        # Nx 卡牌名 (format_initial_state_for_memory 产生的)
        for match in re.finditer(r"\d+x\s+(.+?)\s*\((\d+)费", text):
            names.append(match.group(1).strip())

        # - 遗物名 [tier] 格式
        for match in re.finditer(r"-\s+(.+?)\s*[\[\-\n]", text):
            names.append(match.group(1).strip())

        return names


__all__ = ["MemoryInjector"]
