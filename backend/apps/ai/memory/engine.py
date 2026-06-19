"""统一记忆引擎 — 整合单局记忆、长期记忆、知识图谱"""

from __future__ import annotations

import json
import logging
import time
from typing import Any

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.memory.atom import AtomType, MemoryAtom
from apps.ai.memory.atom_store import AtomStore
from apps.ai.memory.graph_store import GameKnowledgeGraph
from apps.ai.memory.injector import MemoryInjector
from apps.ai.memory.lifecycle import AtomLifecycleManager
from apps.ai.memory.session_memory import SessionMemory
from apps.ai.memory.extractor import MemoryExtractor

logger = logging.getLogger(__name__)


class MemoryEngine:
    """统一记忆引擎 — 整合单局记忆、长期记忆、知识图谱"""

    def __init__(self, db_path: str, config_dict: dict[str, Any] | None = None):
        self._db_path = db_path
        self._session = SessionMemory()
        self._store = AtomStore(db_path)
        self._lifecycle = AtomLifecycleManager(self._store, config_dict)
        self._extractor = MemoryExtractor(config_dict)
        self._injector = MemoryInjector(self._store)
        self._graphs: dict[str, GameKnowledgeGraph] = {}
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        await self._store.initialize()
        await self._lifecycle.start()
        self._initialized = True
        logger.info("MemoryEngine 初始化完成")

    async def shutdown(self):
        await self._lifecycle.stop()
        for graph in self._graphs.values():
            await graph.close()
        self._graphs.clear()
        await self._store.close()
        self._initialized = False
        logger.info("MemoryEngine 关闭")

    # === 单局记忆 (SessionMemory) ===

    @property
    def session(self) -> SessionMemory:
        return self._session

    @property
    def store(self) -> AtomStore:
        return self._store

    @property
    def db_path(self) -> str:
        return self._db_path

    def start_new_game(self):
        self._session.start_session()

    def record_game_event(
        self,
        event_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
    ):
        return self._session.append_event(event_type, content, metadata)

    async def summarize_session_if_needed(self) -> bool:
        if not self._session.should_summarize():
            return False
        return await self.summarize_session_memory()

    async def summarize_session_memory(self) -> bool:
        pending = self._session.pending_to_prompt_text()
        if not pending:
            return False

        ai = get_ai_client()
        if not ai.available:
            logger.debug("AI 不可用，跳过单局记忆总结")
            return False

        prompt = f"""你是游戏直播 AI 的单局记忆整理器。请把待总结事件压缩进三层单局记忆。

要求：
- core：只保留本局内已经确认、影响长期决策的机制/规则发现。
- important：保留当前牌组、遗物、路线、关键状态评估。
- recent：保留最近战术、刚发生的重要操作和下一步注意事项。
- 单局记忆用完即弃，不要写用户记忆。
- 删除噪声、重复和已经过期的细节。
- 返回 JSON 对象，字段必须是 core / important / recent。

【当前 core】
{self._session.core or '（暂无）'}

【当前 important】
{self._session.important or '（暂无）'}

【当前 recent】
{self._session.recent or '（暂无）'}

【待总结事件】
{pending}
"""
        request = ChatRequest(
            messages=[ChatMessage(role="user", content=prompt)],
            model="",
            temperature=0.2,
            max_tokens=700,
            json_format=True,
        )
        response = await ai.chat(request)
        if not response or not response.content:
            return False
        try:
            data = json.loads(response.content)
        except json.JSONDecodeError:
            logger.warning("单局记忆总结 JSON 解析失败: %s", response.content[:120])
            return False
        self._session.apply_summary({
            "core": str(data.get("core", self._session.core) or ""),
            "important": str(data.get("important", self._session.important) or ""),
            "recent": str(data.get("recent", self._session.recent) or ""),
        })
        return True

    # === 长期记忆 (AtomStore) ===

    async def add_atom(self, atom: MemoryAtom) -> int:
        atom_id = await self._store.insert(atom)
        await self._lifecycle.run_manual_reinforcement([atom])
        return atom_id

    async def add_atoms(self, atoms: list[MemoryAtom]) -> list[int]:
        if not atoms:
            return []
        atom_ids = await self._store.insert_many(atoms)
        await self._lifecycle.run_manual_reinforcement(atoms)
        return atom_ids

    async def recall(
        self,
        query: str,
        k: int = 5,
        game_id: str | None = None,
        user_id: str | None = None,
        atom_types: list[AtomType] | None = None,
    ) -> list[MemoryAtom]:
        results = await self._store.search_fts(
            query=query,
            limit=k * 2,
            game_id=game_id,
            user_id=user_id,
            atom_types=atom_types,
        )
        # 按时间衰减分数排序
        now = time.time()
        for atom in results:
            temporal = atom.compute_temporal_score(now)
            bm25 = float(atom.metadata.get("bm25_score", 0.5))
            atom.metadata["final_score"] = bm25 * temporal
        results.sort(
            key=lambda a: float(a.metadata.get("final_score", 0)),
            reverse=True,
        )
        for atom in results[:k]:
            await self._store.touch(atom.atom_id)
        return results[:k]

    async def extract_and_store(
        self,
        source: str,
        content: str,
        context: dict[str, Any] | None = None,
    ) -> list[int]:
        atoms = await self._extractor.extract(source, content, context)
        return await self.add_atoms(atoms)

    # === 记忆注入 ===

    async def inject_for_game(self, game_id: str) -> str:
        graph = self._graphs.get(game_id)
        return await self._injector.inject_for_game(
            session=self._session,
            game_id=game_id,
            graph=graph,
        )

    async def inject_for_host(self, user_id: str | None = None) -> str:
        return await self._injector.inject_for_host(user_id=user_id)

    # === 知识图谱 ===

    def get_graph(self, game_id: str) -> GameKnowledgeGraph | None:
        return self._graphs.get(game_id)

    async def ensure_graph(self, game_id: str) -> GameKnowledgeGraph:
        if game_id not in self._graphs:
            graph = GameKnowledgeGraph(self._db_path, game_id)
            await graph.initialize()
            self._graphs[game_id] = graph
        return self._graphs[game_id]

    # === 生命周期 ===

    async def run_maintenance(self) -> dict[str, int]:
        return await self._lifecycle.run_maintenance()


# 全局单例
_engine: MemoryEngine | None = None


def get_memory_engine() -> MemoryEngine:
    global _engine
    if _engine is None:
        from apps.config import config
        db_path = getattr(config, "memory_db_path", "data/memory.db")
        _engine = MemoryEngine(db_path)
    return _engine


async def init_memory_engine() -> MemoryEngine:
    engine = get_memory_engine()
    await engine.initialize()
    return engine


__all__ = ["MemoryEngine", "get_memory_engine", "init_memory_engine"]
