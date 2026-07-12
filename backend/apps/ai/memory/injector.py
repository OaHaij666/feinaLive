"""记忆注入器 — 按 Agent 角色差异化注入记忆到 prompt

AgentGraph: SessionMemory (全量) + LongTermMemory (游戏知识) + KnowledgeGraph (协同/克制)
HostRuntime: LongTermMemory (观众记忆 + 主播人设 + 互动事件)
"""

from __future__ import annotations

import logging

from apps.ai.memory.atom import AtomType
from apps.ai.memory.atom_store import AtomStore
from apps.ai.memory.graph_store import GameKnowledgeGraph, expand_graph_from_atoms
from apps.ai.memory.session_memory import SessionMemory
from apps.config import config

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
        context_max_chars: int | None = None,
    ) -> str:
        """为 AgentGraph 构建完整游戏场景记忆上下文

        包含:
        1. SessionMemory (单局记忆，全量)
        2. LongTermMemory (游戏知识，FTS检索)
        3. KnowledgeGraph (协同/克制关系)
        """
        sections = []

        # 1. 单局记忆 — 全量拼接
        context_pending = session.pending_context_to_prompt_text(
            context_max_chars or config.agent_memory_context_max_chars
        )
        sections = []
        for title, content in (
            ("核心记忆", session.core),
            ("重要记忆", session.important),
            ("最近记忆", session.recent),
            ("待总结近期事件", context_pending),
        ):
            if content:
                sections.append(f"【{title}】\n{content}")
        session_text = "\n\n".join(sections)
        if session_text:
            sections.append(session_text)

        recall_query = "\n".join(
            part
            for part in (
                session.core,
                session.important,
                session.recent,
                context_pending,
            )
            if part
        )[-4000:]

        # 2. 当前 Session 驱动的游戏原子混合召回。
        game_knowledge = await self._store.search_fts(
            query=recall_query,
            limit=10,
            game_id=game_id,
            atom_types=[AtomType.GAME_MECHANIC, AtomType.GAME_LORE],
            use_vector=config.embedding_game_graph_enabled,
        )
        if not game_knowledge and recall_query:
            game_knowledge = await self._store.search_fts(
                query="",
                limit=6,
                game_id=game_id,
                atom_types=[AtomType.GAME_MECHANIC, AtomType.GAME_LORE],
                use_vector=False,
            )
        unique_knowledge = []
        seen_contents: set[str] = set()
        for atom in game_knowledge:
            key = "".join(atom.content.lower().split())
            if key and key not in seen_contents:
                seen_contents.add(key)
                unique_knowledge.append(atom)
        game_knowledge = unique_knowledge
        if game_knowledge:
            lines = [f"- {a.content}" for a in game_knowledge]
            sections.append("【游戏经验】\n" + "\n".join(lines))

        # 3. 以命中原子作为图入口，再扩展相关游戏事实边。
        graph_facts = await expand_graph_from_atoms(
            self._store.db_path,
            "game",
            game_id,
            [atom.atom_id for atom in game_knowledge if atom.atom_id],
            limit=12,
        )
        if graph_facts:
            sections.append(
                "【相关游戏关系】\n"
                + "\n".join(
                    f"- {fact['source_label']} --{fact['relation']}--> {fact['target_label']}"
                    for fact in graph_facts
                )
            )
        elif graph:
            # 兼容旧图：没有原子入口时再按牌组/遗物实体名匹配。
            graph_context = await self._build_graph_context(session, graph)
            if graph_context:
                sections.append(graph_context)

        return "\n\n".join(sections) if sections else ""

    async def inject_for_host(
        self, user_id: str | None = None, query: str = ""
    ) -> str:
        """Recall user-scoped atoms and expand their evidence-backed graph facts."""

        if not user_id:
            return ""
        viewer = await self._store.search_fts(
            query=query,
            limit=6,
            user_id=user_id,
            atom_types=[
                AtomType.VIEWER_FACT,
                AtomType.VIEWER_PREFERENCE,
                AtomType.VIEWER_RELATION,
            ],
            use_vector=config.embedding_user_graph_enabled,
        )
        if not viewer and query.strip():
            viewer = await self._store.search_fts(
                query="",
                limit=4,
                user_id=user_id,
                atom_types=[
                    AtomType.VIEWER_FACT,
                    AtomType.VIEWER_PREFERENCE,
                    AtomType.VIEWER_RELATION,
                ],
            )

        sections: list[str] = []
        if viewer:
            sections.append(
                "【相关长期事实】\n" + "\n".join(f"- {atom.content}" for atom in viewer)
            )

        graph_facts = await expand_graph_from_atoms(
            self._store.db_path,
            "user",
            user_id,
            [atom.atom_id for atom in viewer if atom.atom_id],
        )
        if graph_facts:
            lines: list[str] = []
            for fact in graph_facts:
                source = (
                    "用户"
                    if fact["source_type"] == "user"
                    else str(fact["source_label"])
                )
                target = (
                    "用户"
                    if fact["target_type"] == "user"
                    else str(fact["target_label"])
                )
                lines.append(f"- {source} --{fact['relation']}--> {target}")
            sections.append("【相关用户关系】\n" + "\n".join(lines))
        return "\n\n".join(sections)

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

        # 兼容旧数据中的“牌组:xxx+yyy+zzz”格式。
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
