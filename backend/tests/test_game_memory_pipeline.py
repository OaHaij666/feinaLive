import json
from types import SimpleNamespace

import aiosqlite
import pytest

from apps.agent.capabilities.mcp import MCPCapability
from apps.agent.mutual_context import MutualContext
from apps.agent.scenarios.profile import UnifiedAction
from apps.agent.state import CapabilityCall, Observation
from apps.ai.client import ChatResponse
from apps.ai.memory.atom import AtomType, MemoryAtom
from apps.ai.memory.engine import MemoryEngine
from apps.ai.memory.game_memory import GameMemoryPolicy
from apps.ai.memory.session_memory import SessionMemory


class FakeAI:
    available = True

    def __init__(self, payloads):
        self.payloads = list(payloads)
        self.calls = []

    async def chat(self, request):
        self.calls.append(request)
        payload = self.payloads.pop(0)
        return ChatResponse(content=json.dumps(payload, ensure_ascii=False), model="fake")


class OfflineAI:
    available = False


def summary_payload(*, stance="supports", content="金刚杵会提升力量"):
    return {
        "session": {
            "core": "金刚杵提供力量",
            "important": "当前持有金刚杵",
            "recent": "刚获得遗物",
        },
        "durable_candidates": [
            {
                "content": content,
                "type": "game_mechanic",
                "importance": 0.9,
                "entities": ["金刚杵", "力量"],
                "relations": [
                    {
                        "subject": "金刚杵",
                        "predicate": "increases strength",
                        "object": "力量",
                        "stance": stance,
                    }
                ],
                "evidence": "本局获得金刚杵后力量增加",
            }
        ],
    }


def test_agent_context_contains_whole_pending_batch_not_fixed_tail():
    session = SessionMemory(summarize_threshold=30)
    session.start_session("spire")
    for index in range(1, 31):
        session.append_event("action", f"事件-{index}")
    context = session.pending_context_to_prompt_text(max_chars=12000)
    assert "事件-1" in context
    assert "事件-30" in context
    assert len(context.splitlines()) == 30


def test_agent_context_budget_trims_only_offline_backlog_from_oldest_side():
    session = SessionMemory(summarize_threshold=3)
    session.start_session("spire")
    for index in range(1, 21):
        session.append_event("action", f"事件-{index}-" + "x" * 120)
    context = session.pending_context_to_prompt_text(max_chars=1000)
    assert "事件-20-" in context
    assert "事件-1-" not in context
    assert len(context) <= 1000


@pytest.mark.asyncio
async def test_threshold_summary_updates_session_and_durable_graph(tmp_path, monkeypatch):
    fake = FakeAI([summary_payload()])
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: fake)
    engine = MemoryEngine(str(tmp_path / "memory.db"))
    await engine.initialize()
    engine.register_game_policy("spire", GameMemoryPolicy(summary_threshold=2))
    try:
        await engine.start_new_game("spire")
        await engine.record_game_event("reward", "获得金刚杵")
        assert not await engine.summarize_session_if_needed()
        await engine.record_game_event("state", "力量从0变为1")
        assert await engine.summarize_session_if_needed()
        assert len(fake.calls) == 1
        assert engine.session.core == "金刚杵提供力量"
        atoms = await engine.store.search_fts(
            "金刚杵", game_id="spire", atom_types=[AtomType.GAME_MECHANIC]
        )
        assert [atom.content for atom in atoms] == ["金刚杵会提升力量"]
        async with aiosqlite.connect(engine.db_path) as db:
            edge = await (
                await db.execute(
                    "SELECT id FROM knowledge_edges WHERE relation='increases_strength'"
                )
            ).fetchone()
            assert edge
            evidence = await (
                await db.execute(
                    "SELECT stance FROM knowledge_edge_evidence WHERE edge_id=?",
                    (edge[0],),
                )
            ).fetchall()
            assert evidence == [("supports",)]
    finally:
        await engine.finish_game_session(force=False)
        await engine.shutdown()


@pytest.mark.asyncio
async def test_summary_prompt_contains_only_locally_recalled_knowledge(tmp_path, monkeypatch):
    fake = FakeAI([summary_payload()])
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: fake)
    engine = MemoryEngine(str(tmp_path / "memory.db"))
    await engine.initialize()
    try:
        await engine.add_atoms(
            [
                MemoryAtom(
                    atom_type=AtomType.GAME_MECHANIC,
                    content="Vajra increases Strength",
                    entities=["Vajra", "Strength"],
                    game_id="spire",
                ),
                MemoryAtom(
                    atom_type=AtomType.GAME_LORE,
                    content="Neow lives beyond the spire",
                    entities=["Neow"],
                    game_id="spire",
                ),
            ]
        )
        await engine.start_new_game("spire")
        await engine.record_game_event("reward", "Vajra increased Strength")
        assert await engine.summarize_session_memory(force=True)
        prompt = fake.calls[0].messages[0].content
        assert "Vajra increases Strength" in prompt
        assert "Neow lives beyond the spire" not in prompt
    finally:
        await engine.finish_game_session(force=False)
        await engine.shutdown()


@pytest.mark.asyncio
async def test_saved_batch_retries_without_second_llm_or_duplicate_atom(tmp_path, monkeypatch):
    fake = FakeAI([summary_payload()])
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: fake)
    engine = MemoryEngine(str(tmp_path / "memory.db"))
    await engine.initialize()
    await engine.start_new_game("spire")
    await engine.record_game_event("reward", "获得金刚杵")
    original_apply = engine.store.apply_game_summary_batch
    failed_once = False

    async def fail_once(**kwargs):
        nonlocal failed_once
        if not failed_once:
            failed_once = True
            raise RuntimeError("simulated crash after atom commit")
        await original_apply(**kwargs)

    monkeypatch.setattr(engine.store, "apply_game_summary_batch", fail_once)
    try:
        with pytest.raises(RuntimeError):
            await engine.summarize_session_memory(force=True)
        assert await engine.summarize_session_memory(force=True)
        assert len(fake.calls) == 1
        page = await engine.store.list_atoms(game_id="spire", keyword="金刚杵")
        assert page["total"] == 1
    finally:
        await engine.finish_game_session(force=False)
        await engine.shutdown()


@pytest.mark.asyncio
async def test_same_relation_reuses_edge_and_adds_contradicting_evidence(tmp_path, monkeypatch):
    fake = FakeAI(
        [
            summary_payload(),
            summary_payload(stance="contradicts", content="新证据表明金刚杵不会提升力量"),
        ]
    )
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: fake)
    engine = MemoryEngine(str(tmp_path / "memory.db"))
    await engine.initialize()
    try:
        await engine.start_new_game("spire")
        await engine.record_game_event("observation", "力量增加")
        await engine.summarize_session_memory(force=True)
        await engine.record_game_event("observation", "移除其他加成后力量未增加")
        await engine.summarize_session_memory(force=True)
        async with aiosqlite.connect(engine.db_path) as db:
            edges = await (
                await db.execute(
                    "SELECT id FROM knowledge_edges WHERE relation='increases_strength'"
                )
            ).fetchall()
            assert len(edges) == 1
            stances = await (
                await db.execute(
                    "SELECT stance FROM knowledge_edge_evidence WHERE edge_id=? ORDER BY stance",
                    (edges[0][0],),
                )
            ).fetchall()
            assert stances == [("contradicts",), ("supports",)]
    finally:
        await engine.finish_game_session(force=False)
        await engine.shutdown()


@pytest.mark.asyncio
async def test_idle_and_finish_force_flush_below_threshold(tmp_path, monkeypatch):
    fake = FakeAI([summary_payload(), summary_payload(content="第二局长期事实")])
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: fake)
    engine = MemoryEngine(str(tmp_path / "memory.db"))
    await engine.initialize()
    engine.register_game_policy("spire", GameMemoryPolicy(summary_threshold=99))
    try:
        await engine.start_new_game("spire")
        await engine.record_game_event("observation", "第一局少量事件")
        engine.session._last_event_at -= 1000
        assert await engine.summarize_idle_if_needed(120)

        await engine.record_game_event("observation", "结束前少量事件")
        assert await engine.finish_game_session(force=True)
        assert len(fake.calls) == 2
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
async def test_offline_finished_run_is_replayed_as_durable_backlog(tmp_path, monkeypatch):
    engine = MemoryEngine(str(tmp_path / "memory.db"))
    await engine.initialize()
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: OfflineAI())
    await engine.start_new_game("spire")
    old_session_id = engine.session.session_id
    await engine.record_game_event("observation", "离线时发现的机制")
    assert not await engine.finish_game_session(force=True)

    fake = FakeAI([summary_payload(content="离线事件恢复出的长期事实")])
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: fake)
    await engine.start_new_game("spire")
    try:
        assert engine.session.session_id != old_session_id
        assert await engine.summarize_backlog_if_needed()
        assert len(fake.calls) == 1
        page = await engine.store.list_atoms(game_id="spire", keyword="离线事件恢复出的长期事实")
        assert page["total"] == 1
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
async def test_mcp_capability_flushes_before_manual_start_and_scenario_end(monkeypatch):
    timeline = []

    class Session:
        def update_important(self, text):
            timeline.append("important")

    class Engine:
        session = Session()

        async def ensure_game_session(self, game_id):
            timeline.append("ensure")

        async def close_game_session(self, game_id, **kwargs):
            timeline.append("flush")
            return {"active": False}

        async def open_game_session(self, game_id, **kwargs):
            timeline.append("new_session")
            return {"active": True}

        async def update_working_memory(self, *args, **kwargs):
            timeline.append("important")

        async def record_game_event(self, *args, **kwargs):
            timeline.append("event")

        async def record_mcp_event(self, *args, **kwargs):
            timeline.append("event")

        async def summarize_session_if_needed(self, game_id=None):
            return False

    class Adapter:
        game_id = "spire"
        memory_policy = GameMemoryPolicy()

        async def execute_action(self, action):
            timeline.append(f"execute:{action.action_type}")
            return True, ""

        def is_session_start_action(self, action):
            return action.action_type == "start_game"

        def is_readonly_tool(self, name):
            return False

        async def on_game_session_opened(self, memory):
            await memory.update_layer("important", "初始牌组", source="test")

        def is_session_finished(self, state):
            return state.raw_state.get("screen_type") == "GAME_OVER"

        def session_end_event(self, state):
            return {"screen_type": "GAME_OVER"}

        def session_restart_actions(self, state):
            return [
                UnifiedAction(action_type="proceed", params={}),
                UnifiedAction(action_type="start_game", params={"character": "IRONCLAD"}),
            ]

    engine = Engine()
    monkeypatch.setattr("apps.agent.capabilities.mcp.get_memory_engine", lambda: engine)

    capability = MCPCapability(Adapter(), MutualContext())
    await capability.execute(
        CapabilityCall(name="mcp__start_game", arguments={})
    )
    assert timeline.index("flush") < timeline.index("execute:start_game")
    assert "new_session" in timeline

    timeline.clear()
    state = SimpleNamespace(raw_state={"screen_type": "GAME_OVER"})
    assert await capability.handle_terminal(
        Observation(source="mcp", summary="game over", data=state, terminal=True)
    )
    assert timeline[0] == "flush"
    assert "execute:proceed" in timeline
    assert "execute:start_game" in timeline


@pytest.mark.asyncio
async def test_game_sessions_and_working_layers_are_isolated_by_game(tmp_path, monkeypatch):
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: OfflineAI())
    engine = MemoryEngine(str(tmp_path / "memory.db"))
    await engine.initialize()
    engine.register_game_policy(
        "world_game",
        GameMemoryPolicy(
            session_mode="per_run",
            layer_retention={"core": "carry", "important": "reset", "recent": "reset"},
        ),
    )
    try:
        first = await engine.open_game_session("world_game", external_session_id="world-1")
        await engine.update_working_memory("world_game", "core", "世界主线已推进")
        await engine.update_working_memory("world_game", "important", "当前在城镇")

        await engine.open_game_session("arena", external_session_id="match-1")
        await engine.update_working_memory("arena", "core", "竞技场规则")
        assert engine.get_game_session("world_game").core == "世界主线已推进"
        assert engine.get_game_session("arena").core == "竞技场规则"

        same = await engine.open_game_session("world_game", external_session_id="world-1")
        assert same["session_id"] == first["session_id"]

        second = await engine.open_game_session("world_game", external_session_id="world-2")
        assert second["session_id"] != first["session_id"]
        world = engine.get_game_session("world_game")
        assert world.core == "世界主线已推进"
        assert world.important == ""
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
async def test_external_mcp_event_id_is_idempotent_per_game(tmp_path, monkeypatch):
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: OfflineAI())
    engine = MemoryEngine(str(tmp_path / "memory.db"))
    await engine.initialize()
    try:
        await engine.open_game_session("spire", external_session_id="run-1")
        first = await engine.record_mcp_event(
            "spire",
            event_type="tool_result",
            tool_name="get_card_info",
            result={"name": "旋风斩"},
            external_event_id="event-1",
        )
        second = await engine.record_mcp_event(
            "spire",
            event_type="tool_result",
            tool_name="get_card_info",
            result={"name": "重复响应"},
            external_event_id="event-1",
        )
        assert first.event_id == second.event_id
        assert len(engine.get_game_session("spire").pending_events) == 1
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
async def test_knowledge_graph_scope_can_switch_without_cross_game_leakage(tmp_path, monkeypatch):
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: OfflineAI())
    engine = MemoryEngine(str(tmp_path / "memory.db"))
    await engine.initialize()
    try:
        await engine.select_game("game_a")
        assert engine.get_game_session("game_a") is None
        graph_a = await engine.ensure_graph("game_a")
        await graph_a.add_node("entity", "共同实体", {"source": "A"})

        await engine.select_game("game_b")
        graph_b = await engine.ensure_graph("game_b")
        await graph_b.add_node("entity", "共同实体", {"source": "B"})

        await engine.add_atom(
            MemoryAtom(
                atom_type=AtomType.GAME_MECHANIC,
                content="alpha-only mechanic",
                game_id="game_a",
            )
        )
        await engine.add_atom(
            MemoryAtom(
                atom_type=AtomType.GAME_MECHANIC,
                content="beta-only mechanic",
                game_id="game_b",
            )
        )

        assert engine.selected_game_id == "game_b"
        assert (await graph_a.search("共同实体"))[0]["properties"]["source"] == "A"
        assert (await graph_b.search("共同实体"))[0]["properties"]["source"] == "B"
        context_a = await engine.get_game_memory_context("game_a", "alpha-only")
        assert [item["content"] for item in context_a.recalled_atoms] == ["alpha-only mechanic"]
        assert engine.selected_game_id == "game_b"
        scopes = {item["game_id"] for item in await engine.list_game_scopes()}
        assert {"game_a", "game_b"}.issubset(scopes)
    finally:
        await engine.shutdown()


@pytest.mark.asyncio
async def test_active_external_session_and_policy_restore_after_restart(tmp_path, monkeypatch):
    monkeypatch.setattr("apps.ai.memory.engine.get_ai_client", lambda: OfflineAI())
    db_path = str(tmp_path / "memory.db")
    first = MemoryEngine(db_path)
    await first.initialize()
    policy = GameMemoryPolicy(
        session_mode="external",
        layer_retention={"core": "carry", "important": "carry", "recent": "reset"},
        summary_threshold=7,
    )
    opened = await first.open_game_session(
        "external_game", external_session_id="remote-run-9", policy=policy
    )
    await first.update_working_memory("external_game", "core", "远端世界状态")
    await first.shutdown()

    second = MemoryEngine(db_path)
    await second.initialize()
    try:
        restored = await second.ensure_game_session("external_game")
        assert restored.session_id == opened["session_id"]
        assert restored.core == "远端世界状态"
        assert second.get_game_policy("external_game").session_mode == "external"
        assert second.get_game_policy("external_game").summary_threshold == 7
    finally:
        await second.close_game_session("external_game", reason="test_complete")
        await second.shutdown()
