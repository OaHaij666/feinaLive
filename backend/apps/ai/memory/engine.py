"""Unified session, atomic-memory and knowledge-graph engine."""

from __future__ import annotations

import asyncio
import json
import logging
import re
from pathlib import Path
from typing import Any

from apps.ai.client import ChatMessage, ChatRequest, get_ai_client
from apps.ai.embedding import EmbeddingClient
from apps.ai.memory.atom import AtomType, MemoryAtom
from apps.ai.memory.atom_store import AtomStore
from apps.ai.memory.game_memory import GameMemoryContext, GameMemoryPolicy, LayerName
from apps.ai.memory.graph_store import GameKnowledgeGraph, expand_graph_from_atoms
from apps.ai.memory.injector import MemoryInjector
from apps.ai.memory.lifecycle import AtomLifecycleManager
from apps.ai.memory.session_memory import SessionMemory, SessionMemoryEvent
from apps.ai.memory.vector_store import ChromaVectorStore

logger = logging.getLogger(__name__)


class MemoryEngine:
    """One authoritative memory pipeline for both session and durable knowledge."""

    def __init__(self, db_path: str, config_dict: dict[str, Any] | None = None):
        from apps.config import config

        self._db_path = db_path
        self._config_dict = config_dict or {}
        threshold = max(1, int(config.game_memory_threshold))
        self._game_summary_batch_size = threshold
        self._fallback_session = SessionMemory(
            pending_maxlen=max(40, threshold + 8),
            summarize_threshold=threshold,
        )
        self._sessions: dict[str, SessionMemory] = {}
        self._external_session_ids: dict[str, str | None] = {}
        self._policies: dict[str, GameMemoryPolicy] = {}
        self._selected_game_id = ""
        self._last_game_id = ""
        configured_db = Path(config.app_db_path).resolve()
        current_db = Path(db_path).resolve()
        chroma_path = (
            config.chroma_path if current_db == configured_db else str(current_db.parent / "chroma")
        )
        self._vector_store = ChromaVectorStore(chroma_path, config.chroma_collection)
        self._store = AtomStore(db_path, vector_store=self._vector_store)
        self._embed_client = EmbeddingClient()
        self._embed_on_write = bool(self._config_dict.get("embed_on_write", True))
        if self._embed_client.available:
            self._store.set_embed_client(self._embed_client)
            self._store.set_embed_on_write(self._embed_on_write)
            logger.info("Embedding 客户端已接入 AtomStore")
        else:
            logger.info("Embedding 未配置，AtomStore 使用纯 FTS5 检索")
        self._lifecycle = AtomLifecycleManager(self._store, config_dict)
        self._injector = MemoryInjector(self._store)
        self._graphs: dict[str, GameKnowledgeGraph] = {}
        self._summary_locks: dict[str, asyncio.Lock] = {}
        self._initialized = False

    async def initialize(self):
        if self._initialized:
            return
        await self._store.initialize()
        await self._lifecycle.start()
        self._initialized = True
        logger.info("MemoryEngine 初始化完成")

    async def shutdown(self):
        for game_id in list(self._sessions):
            session = self._sessions[game_id]
            while session.active and session.pending_events:
                if not await self._summarize_session(session, force=True):
                    break
            await self.persist_session_snapshot(game_id)
        await self._lifecycle.stop()
        for graph in self._graphs.values():
            await graph.close()
        self._graphs.clear()
        await self._store.close()
        self._initialized = False
        logger.info("MemoryEngine 关闭")

    @property
    def session(self) -> SessionMemory:
        return self._sessions.get(
            self._selected_game_id or self._last_game_id, self._fallback_session
        )

    @property
    def selected_game_id(self) -> str:
        return self._selected_game_id

    def get_game_session(self, game_id: str) -> SessionMemory | None:
        return self._sessions.get(game_id)

    def register_game_policy(self, game_id: str, policy: GameMemoryPolicy) -> GameMemoryPolicy:
        self._policies[game_id] = policy
        if game_id in self._sessions:
            self._sessions[game_id].set_summarize_threshold(policy.summary_threshold)
        return policy

    def get_game_policy(self, game_id: str) -> GameMemoryPolicy:
        if game_id in self._policies:
            return self._policies[game_id]
        from apps.config import config

        policy = GameMemoryPolicy(
            summary_threshold=config.game_memory_threshold,
            idle_summary_seconds=config.game_memory_idle_seconds,
            context_max_chars=config.game_memory_context_max_chars,
        )
        self._policies[game_id] = policy
        return policy

    def _resolve_game_id(self, game_id: str | None = None) -> str:
        return game_id or self._last_game_id or self._selected_game_id or "game"

    @property
    def store(self) -> AtomStore:
        return self._store

    @property
    def embed_client(self):
        return self._embed_client

    @property
    def db_path(self) -> str:
        return self._db_path

    def _new_session(self, game_id: str) -> SessionMemory:
        policy = self.get_game_policy(game_id)
        return SessionMemory(
            pending_maxlen=max(40, policy.summary_threshold + 8),
            summarize_threshold=max(1, policy.summary_threshold),
        )

    def _restore_policy_from_row(
        self, game_id: str, row: dict[str, Any], *, force: bool = False
    ) -> None:
        if game_id in self._policies and not force:
            return
        raw = row.get("policy_json")
        if not raw:
            return
        try:
            payload = json.loads(raw) if isinstance(raw, str) else raw
            if isinstance(payload, dict) and payload:
                self.register_game_policy(game_id, GameMemoryPolicy(**payload))
        except (TypeError, ValueError, json.JSONDecodeError):
            logger.warning("忽略无效的游戏记忆策略: game_id=%s", game_id)

    @staticmethod
    def _restore_session_payload(payload: dict[str, Any], target: SessionMemory) -> None:
        row = payload["session"]
        target.restore(
            game_id=str(row["game_id"]),
            session_id=str(row["session_id"]),
            core=str(row["core"] or ""),
            important=str(row["important"] or ""),
            recent=str(row["recent"] or ""),
            summarized_until_id=int(row["summarized_until_event_id"] or 0),
            events=[
                SessionMemoryEvent(
                    event_id=int(item["id"]),
                    event_type=str(item["event_type"]),
                    content=str(item["content"]),
                    metadata=item["metadata"],
                    created_at=float(item["created_at"]),
                )
                for item in payload["events"]
            ],
        )

    async def ensure_game_session(self, game_id: str) -> SessionMemory:
        """Restore or create the independent working session for one game."""
        self._last_game_id = game_id
        current = self._sessions.get(game_id)
        if current and current.active:
            return current
        restored = await self._store.restore_active_game_session(game_id)
        if restored:
            self._restore_policy_from_row(game_id, restored["session"])
            session = self._new_session(game_id)
            self._restore_session_payload(restored, session)
            self._sessions[game_id] = session
            self._external_session_ids[game_id] = restored["session"].get("external_session_id")
            return session
        return await self.start_new_game(game_id)

    async def select_game(self, game_id: str) -> dict[str, Any]:
        self._selected_game_id = game_id
        await self.ensure_graph(game_id)
        session = self._sessions.get(game_id)
        if session is None:
            restored = await self._store.restore_active_game_session(game_id)
            if restored:
                self._restore_policy_from_row(game_id, restored["session"])
                session = self._new_session(game_id)
                self._restore_session_payload(restored, session)
                self._sessions[game_id] = session
                self._external_session_ids[game_id] = restored["session"].get("external_session_id")
        return await self.get_game_session_status(game_id, session.session_id if session else "")

    async def open_game_session(
        self,
        game_id: str,
        *,
        external_session_id: str | None = None,
        policy: GameMemoryPolicy | None = None,
    ) -> dict[str, Any]:
        policy_was_registered = game_id in self._policies
        if policy:
            self.register_game_policy(game_id, policy)
        resolved_policy = self.get_game_policy(game_id)
        if resolved_policy.session_mode == "external" and not external_session_id:
            raise ValueError("external 会话模式必须提供 external_session_id")
        current = self._sessions.get(game_id)
        if (
            current
            and current.active
            and external_session_id
            and self._external_session_ids.get(game_id) == external_session_id
        ):
            return await self.get_game_session_status(game_id, current.session_id)
        if external_session_id:
            persisted = await self._store.restore_game_session_by_external_id(
                game_id, external_session_id
            )
            if persisted:
                row = persisted["session"]
                self._restore_policy_from_row(
                    game_id,
                    row,
                    force=not policy_was_registered and policy is None,
                )
                resolved_policy = self.get_game_policy(game_id)
                if int(row.get("active") or 0):
                    restored = self._new_session(game_id)
                    self._restore_session_payload(persisted, restored)
                    self._sessions[game_id] = restored
                    self._external_session_ids[game_id] = external_session_id
                self._last_game_id = game_id
                return await self.get_game_session_status(game_id, str(row["session_id"]))
        if current and current.active and resolved_policy.session_mode == "continuous":
            return await self.get_game_session_status(game_id, current.session_id)
        retained = {"core": "", "important": "", "recent": ""}
        if current:
            if current.active:
                await self.finish_game_session(game_id=game_id, force=True)
            for layer in retained:
                if resolved_policy.retention_for(layer) == "carry":
                    retained[layer] = str(getattr(current, layer))
        session = await self.start_new_game(
            game_id,
            external_session_id=external_session_id,
        )
        session.update_core(retained["core"])
        session.update_important(retained["important"])
        session.update_recent(retained["recent"])
        await self.persist_session_snapshot(game_id)
        return await self.get_game_session_status(game_id, session.session_id)

    async def start_new_game(
        self, game_id: str = "game", *, external_session_id: str | None = None
    ) -> SessionMemory:
        self._last_game_id = game_id
        session = self._new_session(game_id)
        session.start_session(game_id)
        self._sessions[game_id] = session
        self._external_session_ids[game_id] = external_session_id
        await self._store.create_game_session(
            session.session_id,
            game_id,
            external_session_id=external_session_id,
            policy=self.get_game_policy(game_id).to_dict(),
        )
        return session

    async def record_game_event(
        self,
        event_type: str,
        content: str,
        metadata: dict[str, Any] | None = None,
        *,
        game_id: str | None = None,
        external_event_id: str | None = None,
    ) -> SessionMemoryEvent | None:
        scope = game_id or str((metadata or {}).get("game_id") or self._resolve_game_id())
        session = await self.ensure_game_session(scope)
        event_id, created_at = await self._store.append_game_event(
            session_id=session.session_id,
            game_id=scope,
            event_type=event_type,
            content=content,
            metadata=metadata,
            external_event_id=external_event_id,
        )
        if any(event.event_id == event_id for event in session.pending_events):
            return next(event for event in session.pending_events if event.event_id == event_id)
        return session.append_event(
            event_type,
            content,
            metadata,
            event_id=event_id,
            created_at=created_at,
        )

    async def record_mcp_event(
        self,
        game_id: str,
        *,
        event_type: str,
        tool_name: str,
        arguments: dict[str, Any] | None = None,
        result: Any = None,
        success: bool = True,
        external_event_id: str | None = None,
    ) -> SessionMemoryEvent | None:
        payload = json.loads(
            json.dumps(
                {
                    "source": "mcp",
                    "tool_name": tool_name,
                    "arguments": arguments or {},
                    "result": result,
                    "success": success,
                },
                ensure_ascii=False,
                default=str,
            )
        )
        content = json.dumps(payload, ensure_ascii=False)
        event = await self.record_game_event(
            event_type,
            content,
            payload,
            game_id=game_id,
            external_event_id=external_event_id,
        )
        await self.summarize_session_if_needed(game_id)
        return event

    async def update_working_memory(
        self,
        game_id: str,
        layer: LayerName,
        content: str,
        *,
        source: str = "adapter",
    ) -> None:
        session = await self.ensure_game_session(game_id)
        getattr(session, f"update_{layer}")(content)
        await self.persist_session_snapshot(game_id)
        await self.record_game_event(
            "working_memory_update",
            f"{layer}: {content}",
            {"source": source, "layer": layer, "game_id": game_id},
            game_id=game_id,
        )
        await self.summarize_session_if_needed(game_id)

    async def summarize_session_if_needed(self, game_id: str | None = None) -> bool:
        return await self.summarize_session_memory(game_id=game_id, force=False)

    async def summarize_idle_if_needed(
        self, idle_seconds: float | None = None, game_id: str | None = None
    ) -> bool:
        scope = self._resolve_game_id(game_id)
        session = await self.ensure_game_session(scope)
        if await self.summarize_backlog_if_needed(scope):
            return True
        delay = idle_seconds or self.get_game_policy(scope).idle_summary_seconds
        if not session.is_idle(delay):
            return False
        return await self.summarize_session_memory(game_id=scope, force=True)

    async def summarize_backlog_if_needed(self, game_id: str | None = None) -> bool:
        scope = self._resolve_game_id(game_id)
        if not scope:
            return False
        live = self._sessions.get(scope)
        restored = await self._store.restore_oldest_pending_game_session(
            scope, live.session_id if live else ""
        )
        if not restored:
            return False
        backlog = self._new_session(scope)
        self._restore_session_payload(restored, backlog)
        return await self._summarize_session(backlog, force=True)

    async def finish_game_session(self, *, game_id: str | None = None, force: bool = True) -> bool:
        scope = self._resolve_game_id(game_id)
        session = self._sessions.get(scope)
        if not session:
            return False
        summarized = False
        while session.active and session.pending_events:
            completed = await self._summarize_session(session, force=force)
            if not completed:
                break
            summarized = True
        if session.active:
            await self._store.close_game_session(session.session_id)
            session.end_session()
        self._summary_locks.pop(session.session_id, None)
        return summarized

    async def close_game_session(
        self,
        game_id: str,
        *,
        reason: str = "closed",
        final_event: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        if final_event:
            await self.record_game_event(
                "session_closed",
                json.dumps(final_event, ensure_ascii=False, default=str),
                {"reason": reason, "game_id": game_id},
                game_id=game_id,
            )
        policy = self.get_game_policy(game_id)
        await self.finish_game_session(game_id=game_id, force=policy.flush_on_session_end)
        session = self._sessions.get(game_id)
        return await self.get_game_session_status(game_id, session.session_id if session else "")

    async def persist_session_snapshot(self, game_id: str | None = None) -> None:
        scope = self._resolve_game_id(game_id)
        session = self._sessions.get(scope)
        if session and session.active:
            await self._store.save_game_session_snapshot(
                session.session_id,
                session.core,
                session.important,
                session.recent,
            )

    @staticmethod
    def _parse_summary_json(text: str) -> dict[str, Any] | None:
        payload = str(text or "").strip()
        if payload.startswith("```"):
            lines = payload.splitlines()
            payload = "\n".join(lines[1:-1]).strip()
        try:
            parsed = json.loads(payload)
        except (TypeError, json.JSONDecodeError):
            return None
        return parsed if isinstance(parsed, dict) else None

    @staticmethod
    def _normalize_relation(value: Any) -> str:
        relation = re.sub(r"[^a-zA-Z0-9_]+", "_", str(value or "related_to").strip().lower())
        return relation.strip("_") or "related_to"

    async def _summary_recall_context(
        self, query: str, session: SessionMemory
    ) -> tuple[list[MemoryAtom], list[dict[str, Any]]]:
        if not query.strip() or not session.game_id:
            return [], []
        from apps.config import config

        atoms = await self._store.search_fts(
            query=query[-4000:],
            limit=6,
            game_id=session.game_id,
            atom_types=[AtomType.GAME_MECHANIC, AtomType.GAME_LORE],
            use_vector=config.embedding_game_graph_enabled,
        )
        unique_atoms: list[MemoryAtom] = []
        seen_contents: set[str] = set()
        for atom in atoms:
            key = re.sub(r"\s+", "", atom.content).lower()
            if key and key not in seen_contents:
                seen_contents.add(key)
                unique_atoms.append(atom)
        atoms = unique_atoms
        facts = await expand_graph_from_atoms(
            self._db_path,
            "game",
            session.game_id,
            [atom.atom_id for atom in atoms if atom.atom_id],
            limit=8,
        )
        return atoms, facts

    async def summarize_session_memory(
        self, *, game_id: str | None = None, force: bool = False
    ) -> bool:
        """Summarize one fixed event batch and align durable candidates once."""
        scope = self._resolve_game_id(game_id)
        session = await self.ensure_game_session(scope)
        return await self._summarize_session(session, force=force)

    async def _summarize_session(self, session: SessionMemory, *, force: bool) -> bool:
        lock = self._summary_locks.setdefault(session.session_id, asyncio.Lock())
        async with lock:
            memory_policy = self.get_game_policy(session.game_id)
            pending_events = session.pending_events
            if not pending_events or (not force and not session.should_summarize()):
                return False
            batch_size = max(1, memory_policy.summary_threshold)
            events: list[SessionMemoryEvent] = []
            prompt_lines: list[str] = []
            used_chars = 0
            prompt_budget = memory_policy.context_max_chars
            for event in pending_events[:batch_size]:
                line = event.to_prompt_line()
                if not events and len(line) > prompt_budget:
                    keep = max(200, prompt_budget - 40)
                    line = f"{line[:keep]}…（事件内容已按预算截断）"
                cost = len(line) + (1 if prompt_lines else 0)
                if events and used_chars + cost > prompt_budget:
                    break
                events.append(event)
                prompt_lines.append(line)
                used_chars += cost
            pending = "\n".join(prompt_lines)
            first_event_id = events[0].event_id
            last_event_id = events[-1].event_id
            source_group_id = (
                f"game-summary:{session.game_id}:{session.session_id}:"
                f"{first_event_id}-{last_event_id}"
            )

            saved = await self._store.get_game_summary_batch(source_group_id)
            data = self._parse_summary_json(saved or "") if saved else None
            if data is None:
                ai = get_ai_client()
                if not ai.available:
                    logger.debug("AI 不可用，保留游戏事件等待稍后总结")
                    return False
                if memory_policy.durable_memory_enabled:
                    recalled_atoms, recalled_facts = await self._summary_recall_context(
                        pending, session
                    )
                else:
                    recalled_atoms, recalled_facts = [], []
                from apps.config import config

                eagerness = config.game_memory_eagerness
                if eagerness <= 2:
                    durable_policy = "非常保守：仅输出已被强证据验证的跨局事实。"
                elif eagerness >= 4:
                    durable_policy = (
                        "积极：可输出有明确单批证据的潜在规律，但不得输出猜测或瞬时状态。"
                    )
                else:
                    durable_policy = "平衡：输出证据明确且大概率跨局有用的事实。"
                old_atoms = (
                    "\n".join(f"- [{atom.atom_id}] {atom.content}" for atom in recalled_atoms)
                    or "（无相关长期事实）"
                )
                old_facts = (
                    "\n".join(
                        f"- {fact['source_label']} --{fact['relation']}--> {fact['target_label']}"
                        for fact in recalled_facts
                    )
                    or "（无相关关系）"
                )
                prompt = f"""你是游戏直播 AI 的记忆整理器。一次完成单局记忆压缩和长期知识候选提取。

【当前单局记忆】
core: {session.core or "（暂无）"}
important: {session.important or "（暂无）"}
recent: {session.recent or "（暂无）"}

【本批事件】
{pending}

【局部召回的旧事实】
{old_atoms}

【局部召回的旧关系】
{old_facts}

要求：
1. session.core 保留当前会话中已确认且持续影响决策的规则、目标和约束；important 保留当前关键资源、进度与状态评估；recent 保留近期行动和下一步注意事项。
2. durable_candidates 只提取跨会话仍有价值、且有本批 MCP 事件证据的游戏机制或世界观知识。普通操作、瞬时状态和未经验证猜测不得进入长期知识。
3. 不要重复旧事实；若本批为旧关系提供支持或反驳证据，可以输出同一关系并用 stance 标记 supports 或 contradicts。
4. type 只能是 game_mechanic 或 game_lore；predicate 使用简短稳定的英文 snake_case。
5. 没有长期价值时 durable_candidates 必须为空数组。
6. 当前长期知识提取策略：{durable_policy}

严格返回 JSON 对象：
{{
  "session": {{"core":"", "important":"", "recent":""}},
  "durable_candidates": [{{
    "content":"自包含的原子事实", "type":"game_mechanic", "importance":0.8,
    "entities":["实体"],
    "relations":[{{"subject":"实体A", "predicate":"synergizes_with", "object":"实体B", "stance":"supports"}}],
    "evidence":"本批事件中的依据"
  }}]
}}"""
                response = await ai.chat(
                    ChatRequest(
                        messages=[ChatMessage(role="user", content=prompt)],
                        model="",
                        temperature=0.2,
                        max_tokens=1100,
                        json_format=True,
                    )
                )
                if not response or not response.content:
                    return False
                data = self._parse_summary_json(response.content)
                if data is None:
                    logger.warning("游戏记忆总结 JSON 解析失败: %s", response.content[:160])
                    return False
                persisted = await self._store.save_game_summary_batch(
                    source_group_id=source_group_id,
                    session_id=session.session_id,
                    game_id=session.game_id,
                    first_event_id=first_event_id,
                    last_event_id=last_event_id,
                    result_json=json.dumps(data, ensure_ascii=False, sort_keys=True),
                )
                data = self._parse_summary_json(persisted)
                if data is None:
                    return False

            session_data = data.get("session", data)
            if not isinstance(session_data, dict):
                session_data = {}
            summary = {
                "core": str(session_data.get("core", session.core) or ""),
                "important": str(session_data.get("important", session.important) or ""),
                "recent": str(session_data.get("recent", session.recent) or ""),
            }
            candidates = data.get("durable_candidates", [])
            if not memory_policy.durable_memory_enabled or not isinstance(candidates, list):
                candidates = []
            existing_contents = await self._store.game_source_group_contents(
                session.game_id, source_group_id
            )
            atoms: list[MemoryAtom] = []
            for item in candidates[:6]:
                atom = self._candidate_to_atom(item, source_group_id, existing_contents, session)
                if atom:
                    await self._align_existing_atom(atom)
                    atoms.append(atom)
                    existing_contents.add(atom.content)
            if atoms:
                await self.add_atoms(atoms)

            await self._store.apply_game_summary_batch(
                source_group_id=source_group_id,
                session_id=session.session_id,
                core=summary["core"],
                important=summary["important"],
                recent=summary["recent"],
                last_event_id=last_event_id,
            )
            session.apply_summary(summary, until_event_id=last_event_id)
            return True

    @staticmethod
    def _content_key(content: str) -> str:
        return re.sub(r"[^\w\u4e00-\u9fff]+", "", content.lower())

    async def _align_existing_atom(self, atom: MemoryAtom) -> None:
        """Mark and reinforce an exact prior fact; the new atom remains evidence."""
        matches = await self._store.search_fts(
            query=atom.content,
            limit=6,
            game_id=atom.game_id,
            atom_types=[atom.atom_type],
            use_vector=False,
        )
        key = self._content_key(atom.content)
        for existing in matches:
            if key and self._content_key(existing.content) == key:
                atom.metadata["aligned_atom_id"] = existing.atom_id
                await self._store.reinforce(existing.atom_id, new_confidence=atom.confidence)
                return

    def _candidate_to_atom(
        self,
        item: Any,
        source_group_id: str,
        existing_contents: set[str],
        session: SessionMemory,
    ) -> MemoryAtom | None:
        if not isinstance(item, dict):
            return None
        content = str(item.get("content", "")).strip()
        if not content or content in existing_contents:
            return None
        try:
            atom_type = AtomType(str(item.get("type", "game_mechanic")))
        except ValueError:
            atom_type = AtomType.GAME_MECHANIC
        if atom_type not in {AtomType.GAME_MECHANIC, AtomType.GAME_LORE}:
            atom_type = AtomType.GAME_MECHANIC
        relations: list[dict[str, str]] = []
        raw_relations = item.get("relations", [])
        if isinstance(raw_relations, list):
            for relation in raw_relations[:8]:
                if not isinstance(relation, dict):
                    continue
                subject = str(relation.get("subject", "")).strip()
                obj = str(relation.get("object", "")).strip()
                if not subject or not obj:
                    continue
                stance = str(relation.get("stance", "supports")).lower()
                relations.append(
                    {
                        "subject": subject,
                        "predicate": self._normalize_relation(relation.get("predicate")),
                        "object": obj,
                        "stance": "contradicts" if stance == "contradicts" else "supports",
                    }
                )
        try:
            importance = min(1.0, max(0.0, float(item.get("importance", 0.7))))
        except (TypeError, ValueError):
            importance = 0.7
        raw_entities = item.get("entities", [])
        entities = raw_entities if isinstance(raw_entities, list) else []
        return MemoryAtom(
            source_group_id=source_group_id,
            atom_type=atom_type,
            content=content,
            entities=[str(entity).strip() for entity in entities if str(entity).strip()][:12],
            importance=importance,
            confidence=0.75,
            game_id=session.game_id,
            session_id=session.session_id,
            metadata={
                "source": "game_session_summary",
                "evidence": str(item.get("evidence", ""))[:1000],
                "relations": relations,
            },
        )

    async def add_atom(self, atom: MemoryAtom) -> int:
        atom_id = await self._store.insert(atom)
        await self._lifecycle.run_manual_reinforcement([atom])
        await self._store.recompute_graph_strengths()
        return atom_id

    async def add_atoms(self, atoms: list[MemoryAtom]) -> list[int]:
        if not atoms:
            return []
        atom_ids = await self._store.insert_many(atoms)
        await self._lifecycle.run_manual_reinforcement(atoms)
        await self._store.recompute_graph_strengths()
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
        for atom in results[:k]:
            await self._store.touch(atom.atom_id)
        return results[:k]

    async def inject_for_game(self, game_id: str) -> str:
        session = await self.ensure_game_session(game_id)
        return await self._injector.inject_for_game(
            session=session,
            game_id=game_id,
            graph=self._graphs.get(game_id),
            context_max_chars=self.get_game_policy(game_id).context_max_chars,
        )

    async def get_game_memory_context(self, game_id: str, query: str = "") -> GameMemoryContext:
        from apps.config import config

        session = await self.ensure_game_session(game_id)
        recall_query = query or "\n".join(
            part
            for part in (
                session.core,
                session.important,
                session.recent,
                session.pending_context_to_prompt_text(
                    self.get_game_policy(game_id).context_max_chars
                ),
            )
            if part
        )
        atoms = await self._store.search_fts(
            query=recall_query[-4000:],
            limit=10,
            game_id=game_id,
            atom_types=[AtomType.GAME_MECHANIC, AtomType.GAME_LORE],
            use_vector=config.embedding_game_graph_enabled,
        )
        facts = await expand_graph_from_atoms(
            self._db_path,
            "game",
            game_id,
            [atom.atom_id for atom in atoms if atom.atom_id],
            limit=12,
        )
        return GameMemoryContext(
            game_id=game_id,
            session_id=session.session_id,
            core=session.core,
            important=session.important,
            recent=session.recent,
            pending_events=[
                {
                    "event_id": event.event_id,
                    "event_type": event.event_type,
                    "content": event.content,
                    "metadata": event.metadata,
                    "created_at": event.created_at,
                }
                for event in session.pending_events
            ],
            recalled_atoms=[
                {
                    "atom_id": atom.atom_id,
                    "type": atom.atom_type.value,
                    "content": atom.content,
                    "entities": atom.entities,
                }
                for atom in atoms
            ],
            graph_facts=facts,
        )

    async def get_game_session_status(
        self, game_id: str, session_id: str | None = None
    ) -> dict[str, Any]:
        session = self._sessions.get(game_id)
        target_id = session_id or (session.session_id if session else "")
        stored = await self._store.game_session_status(target_id) if target_id else None
        return {
            "game_id": game_id,
            "selected": self._selected_game_id == game_id,
            "policy": self.get_game_policy(game_id).to_dict(),
            "session_id": target_id,
            "active": bool(session and session.active and session.session_id == target_id),
            "core": session.core if session and session.session_id == target_id else "",
            "important": session.important if session and session.session_id == target_id else "",
            "recent": session.recent if session and session.session_id == target_id else "",
            "pending_count": (
                len(session.pending_events)
                if session and session.session_id == target_id
                else int((stored or {}).get("pending_count") or 0)
            ),
            "stored": stored or {},
        }

    async def list_game_scopes(self) -> list[dict[str, Any]]:
        stored = {item["game_id"]: item for item in await self._store.list_game_scopes()}
        for game_id, session in self._sessions.items():
            item = stored.setdefault(
                game_id,
                {"game_id": game_id, "session_count": 0, "atom_count": 0, "active": 0},
            )
            item["active"] = int(session.active)
            item["selected"] = game_id == self._selected_game_id
            item["policy"] = self.get_game_policy(game_id).to_dict()
        for game_id, item in stored.items():
            item.setdefault("selected", game_id == self._selected_game_id)
            item.setdefault("policy", self.get_game_policy(game_id).to_dict())
        return list(stored.values())

    async def inject_for_host(self, user_id: str | None = None, query: str = "") -> str:
        return await self._injector.inject_for_host(user_id=user_id, query=query)

    def get_graph(self, game_id: str) -> GameKnowledgeGraph | None:
        return self._graphs.get(game_id)

    async def ensure_graph(self, game_id: str) -> GameKnowledgeGraph:
        if game_id not in self._graphs:
            graph = GameKnowledgeGraph(self._db_path, game_id)
            await graph.initialize()
            self._graphs[game_id] = graph
        return self._graphs[game_id]

    async def run_maintenance(self) -> dict[str, int]:
        return await self._lifecycle.run_maintenance()


_engine: MemoryEngine | None = None


def get_memory_engine() -> MemoryEngine:
    global _engine
    if _engine is None:
        from apps.config import config

        _engine = MemoryEngine(config.memory_db_path)
    return _engine


async def init_memory_engine() -> MemoryEngine:
    engine = get_memory_engine()
    await engine.initialize()
    return engine


__all__ = ["MemoryEngine", "get_memory_engine", "init_memory_engine"]
