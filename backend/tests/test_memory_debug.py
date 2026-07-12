import time

import aiosqlite
import pytest

from apps.ai.memory.atom import AtomStatus, AtomType, MemoryAtom
from apps.ai.memory.atom_store import AtomStore
from apps.ai.memory.engine import MemoryEngine
from apps.ai.memory.graph_store import GameKnowledgeGraph
from apps.ai.memory.graph_view import MemoryGraphViewBuilder
from apps.ai.memory.injector import MemoryInjector
from apps.ai.memory.session_memory import SessionMemory
from apps.ai.memory.vector_store import ChromaVectorStore


@pytest.mark.asyncio
async def test_atom_store_list_update_and_soft_delete(tmp_path):
    db_path = str(tmp_path / "memory.db")
    store = AtomStore(db_path)
    await store.initialize()
    try:
        first_id = await store.insert(
            MemoryAtom(
                atom_type=AtomType.VIEWER_FACT,
                content="观众喜欢机器人角色",
                entities=["机器人"],
                user_id="42",
                importance=0.8,
            )
        )
        await store.insert(
            MemoryAtom(
                atom_type=AtomType.GAME_MECHANIC,
                content="旋风斩适合力量流",
                entities=["旋风斩", "力量"],
                game_id="slay_the_spire",
                importance=0.9,
            )
        )

        page = await store.list_atoms(keyword="旋风斩", page=1, page_size=10)
        assert page["total"] == 1
        assert page["items"][0]["atom_type"] == "game_mechanic"

        updated = await store.update_atom_fields(first_id, {"status": "expired"})
        assert updated is not None
        assert updated.status == AtomStatus.EXPIRED

        count = await store.batch_update_status([first_id], AtomStatus.FORGOTTEN)
        assert count == 1
        detail = await store.get(first_id)
        assert detail is not None
        assert detail.status == AtomStatus.FORGOTTEN
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_graph_builder_handles_missing_graph_tables(tmp_path):
    db_path = str(tmp_path / "memory.db")
    store = AtomStore(db_path)
    await store.initialize()
    try:
        builder = MemoryGraphViewBuilder(db_path, store)
        stats = await builder.graph_counts()
        payload = await builder.overview()
        assert stats == {"graph_nodes": 0, "graph_edges": 0}
        assert payload["snapshot"]["nodes"] == []
        assert payload["snapshot"]["edges"] == []
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_graph_builder_merges_atom_entities_and_game_graph(tmp_path):
    db_path = str(tmp_path / "memory.db")
    store = AtomStore(db_path)
    await store.initialize()
    graph = GameKnowledgeGraph(db_path, "slay_the_spire")
    await graph.initialize()
    try:
        await store.insert(
            MemoryAtom(
                atom_type=AtomType.GAME_MECHANIC,
                content="Strike 与 Vajra 有攻击加成关系",
                entities=["Strike"],
                game_id="slay_the_spire",
                importance=0.9,
            )
        )
        strike_id = await graph.add_node("card", "Strike", {"cost": 1})
        vajra_id = await graph.add_node("relic", "Vajra", {})
        await graph.add_edge(strike_id, vajra_id, "synergizes_with", confidence=0.8)

        payload = await MemoryGraphViewBuilder(db_path, store).overview(
            game_id="slay_the_spire"
        )
        node_ids = {node["id"] for node in payload["snapshot"]["nodes"]}
        relations = {edge["relation_type"] for edge in payload["snapshot"]["edges"]}
        assert any(node_id.startswith("atom:") for node_id in node_ids)
        assert "entity:strike" in node_ids
        assert any(node_id.startswith("game:") for node_id in node_ids)
        assert {"mentions", "matches", "synergizes_with"}.issubset(relations)
    finally:
        await graph.close()
        await store.close()


@pytest.mark.asyncio
async def test_memory_engine_recall_returns_score_breakdown(tmp_path):
    db_path = str(tmp_path / "memory.db")
    engine = MemoryEngine(db_path)
    await engine.initialize()
    try:
        await engine.add_atom(
            MemoryAtom(
                atom_type=AtomType.GAME_MECHANIC,
                content="旋风斩配合力量可以造成很高伤害",
                entities=["旋风斩", "力量"],
                game_id="slay_the_spire",
                importance=0.9,
            )
        )

        results = await engine.recall("旋风斩", k=3, game_id="slay_the_spire")
        assert len(results) == 1
        assert "final_score" in results[0].metadata
        assert "bm25_score" in results[0].metadata
        assert "temporal_score" in results[0].metadata
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
async def test_user_atom_is_persisted_as_graph_evidence(tmp_path):
    db_path = str(tmp_path / "memory.db")
    store = AtomStore(db_path)
    await store.initialize()
    try:
        atom_id = await store.insert(
            MemoryAtom(
                atom_type=AtomType.VIEWER_PREFERENCE,
                content="用户喜欢空洞骑士",
                entities=["空洞骑士"],
                user_id="viewer-1",
                metadata={
                    "relations": [
                        {
                            "subject": "用户",
                            "predicate": "likes",
                            "object": "空洞骑士",
                        }
                    ]
                },
            )
        )
        async with aiosqlite.connect(db_path) as db:
            atom_node = await (
                await db.execute(
                    "SELECT node_id FROM memory_atoms WHERE id=?", (atom_id,)
                )
            ).fetchone()
            assert atom_node and atom_node[0]
            likes = await (
                await db.execute(
                    """
                    SELECT e.id FROM knowledge_edges e
                    JOIN knowledge_nodes s ON s.id=e.source_node_id
                    JOIN knowledge_nodes t ON t.id=e.target_node_id
                    WHERE s.owner_type='user' AND s.owner_id='viewer-1'
                      AND e.relation='likes' AND t.label='空洞骑士'
                    """
                )
            ).fetchone()
            assert likes
            evidence = await (
                await db.execute(
                    "SELECT atom_id FROM knowledge_edge_evidence WHERE edge_id=?",
                    (likes[0],),
                )
            ).fetchone()
            assert evidence == (atom_id,)
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_host_recall_expands_only_the_selected_user_graph(tmp_path):
    db_path = str(tmp_path / "memory.db")
    store = AtomStore(db_path)
    await store.initialize()
    try:
        await store.insert(
            MemoryAtom(
                atom_type=AtomType.VIEWER_PREFERENCE,
                content="用户喜欢策略游戏",
                entities=["策略游戏"],
                user_id="42",
                metadata={
                    "relations": [
                        {
                            "subject": "用户",
                            "predicate": "likes",
                            "object": "策略游戏",
                        }
                    ]
                },
            )
        )
        await store.insert(
            MemoryAtom(
                atom_type=AtomType.VIEWER_PREFERENCE,
                content="另一个用户喜欢策略游戏",
                entities=["策略游戏"],
                user_id="99",
                metadata={
                    "relations": [
                        {
                            "subject": "用户",
                            "predicate": "likes",
                            "object": "策略游戏",
                        }
                    ]
                },
            )
        )

        prompt = await MemoryInjector(store).inject_for_host("42", "策略游戏")

        assert "用户喜欢策略游戏" in prompt
        assert "用户 --likes--> 策略游戏" in prompt
        assert "另一个用户" not in prompt
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_game_recall_uses_session_atoms_as_graph_seeds(tmp_path):
    db_path = str(tmp_path / "memory.db")
    store = AtomStore(db_path)
    await store.initialize()
    try:
        await store.insert(
            MemoryAtom(
                atom_type=AtomType.GAME_MECHANIC,
                content="旋风斩与力量效果协同",
                entities=["旋风斩", "力量"],
                game_id="slay_the_spire",
                metadata={
                    "relations": [
                        {
                            "subject": "旋风斩",
                            "predicate": "synergizes_with",
                            "object": "力量",
                        }
                    ]
                },
            )
        )
        session = SessionMemory()
        session.update_important("当前牌组包含旋风斩")

        prompt = await MemoryInjector(store).inject_for_game(
            session, "slay_the_spire"
        )

        assert "旋风斩与力量效果协同" in prompt
        assert "旋风斩 --synergizes_with--> 力量" in prompt
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_keyword_recall_can_explicitly_disable_embedding(tmp_path):
    db_path = str(tmp_path / "memory.db")
    store = AtomStore(db_path)
    await store.initialize()
    await store.insert(
        MemoryAtom(
            atom_type=AtomType.GAME_MECHANIC,
            content="旋风斩会受到力量加成",
            game_id="slay_the_spire",
        )
    )

    class ExplodingEmbedClient:
        available = True

        async def embed_text(self, _text):
            raise AssertionError("embedding should be disabled")

    class AvailableVectorStore:
        available = True

        async def close(self):
            return None

    store.set_embed_client(ExplodingEmbedClient())
    store._vector_store = AvailableVectorStore()
    try:
        results = await store.search_fts(
            "旋风斩",
            game_id="slay_the_spire",
            use_vector=False,
        )
        assert [atom.content for atom in results] == ["旋风斩会受到力量加成"]
    finally:
        await store.close()


@pytest.mark.asyncio
async def test_chroma_is_a_filterable_atom_index(tmp_path):
    vectors = ChromaVectorStore(str(tmp_path / "chroma"), "test_atoms")
    await vectors.initialize()
    try:
        await vectors.upsert(
            1,
            [1.0, 0.0],
            "用户喜欢空洞骑士",
            {"atom_id": 1, "status": "active", "atom_type": "viewer_preference", "user_id": "u1"},
        )
        await vectors.upsert(
            2,
            [1.0, 0.0],
            "另一个用户的记忆",
            {"atom_id": 2, "status": "active", "atom_type": "viewer_fact", "user_id": "u2"},
        )
        result = await vectors.query([1.0, 0.0], 5, user_id="u1")
        assert set(result) == {1}
    finally:
        await vectors.close()


def test_retrieval_access_does_not_reset_memory_decay():
    now = time.time()
    atom = MemoryAtom(
        created_at=now - 20 * 86400,
        last_accessed_at=now,
        last_reinforced_at=None,
        ttl_days=10,
    )
    assert atom.compute_temporal_score(now) < 0.1
