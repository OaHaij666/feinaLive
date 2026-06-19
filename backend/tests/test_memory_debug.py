import pytest

from apps.ai.memory.atom import AtomStatus, AtomType, MemoryAtom
from apps.ai.memory.atom_store import AtomStore
from apps.ai.memory.engine import MemoryEngine
from apps.ai.memory.graph_store import GameKnowledgeGraph
from apps.ai.memory.graph_view import MemoryGraphViewBuilder


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
