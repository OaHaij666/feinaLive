import sqlite3

import pytest
from sqlalchemy import select
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

from apps.ai.memory import engine as engine_module
from apps.ai.memory import summarizer
from apps.ai.memory import user_profile as profiles
from apps.db import Base, UserProfileDB, ViewerInteractionDB
from apps.storage.migrations import prepare_database


@pytest.mark.asyncio
async def test_summary_reads_durable_queue_beyond_recent_fifo(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'profiles.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)

    monkeypatch.setattr(profiles, "async_session", sessions)
    monkeypatch.setattr(summarizer, "async_session", sessions)

    profile = profiles.UserProfile(user_id="42", username="viewer")
    for index in range(10):
        profile.add_conversation(f"message-{index}", f"reply-{index}")
    await profile.flush()

    assert len(profile.recent_messages) == profiles.MAX_RECENT_MESSAGES

    seen_interaction_counts: list[int] = []

    async def fake_summary(_profile, interactions):
        seen_interaction_counts.append(len(interactions))
        return {
            "impression": "喜欢策略游戏",
            "atoms": [
                {
                    "content": "用户喜欢策略游戏",
                    "type": "viewer_preference",
                    "importance": 0.8,
                    "entities": ["策略游戏"],
                    "relations": [
                        {
                            "subject": "用户",
                            "predicate": "likes",
                            "object": "策略游戏",
                        }
                    ],
                }
            ],
        }

    captured_atoms = []

    class FakeStore:
        def __init__(self):
            self.contents: dict[str, set[str]] = {}

        async def source_group_contents(self, _user_id, source_group_id):
            return set(self.contents.get(source_group_id, set()))

    class FakeMemoryEngine:
        def __init__(self):
            self.store = FakeStore()

        async def add_atoms(self, atoms):
            captured_atoms.extend(atoms)
            for atom in atoms:
                self.store.contents.setdefault(atom.source_group_id, set()).add(
                    atom.content
                )
            return list(range(1, len(atoms) + 1))

    fake_engine = FakeMemoryEngine()
    monkeypatch.setattr(summarizer, "generate_user_memory_summary", fake_summary)
    monkeypatch.setattr(
        engine_module, "get_memory_engine", lambda: fake_engine
    )

    result = await summarizer.summarize_if_needed(profile)

    assert result is not None
    assert seen_interaction_counts == [20]
    assert len(captured_atoms) == 1
    assert captured_atoms[0].metadata["relations"][0]["predicate"] == "likes"
    assert profile.last_summary_count == 10
    assert profile.last_summarized_interaction_id > 0

    async with sessions() as session:
        stored = await session.get(UserProfileDB, "42")
        assert stored is not None
        assert stored.last_summarized_interaction_id == profile.last_summarized_interaction_id
        retained = (
            await session.execute(
                select(ViewerInteractionDB).where(
                    ViewerInteractionDB.user_id == "42"
                )
            )
        ).scalars().all()
        assert len(retained) == profiles.MAX_RECENT_MESSAGES

    profile.add_conversation("new-message", "new-reply")
    await profile.flush()
    await summarizer.summarize_if_needed(profile, force=True)
    assert seen_interaction_counts == [20, 2]

    await engine.dispose()


@pytest.mark.asyncio
async def test_summary_retry_reuses_batch_result_and_atoms(tmp_path, monkeypatch):
    engine = create_async_engine(f"sqlite+aiosqlite:///{tmp_path / 'retry.db'}")
    sessions = async_sessionmaker(engine, expire_on_commit=False)
    async with engine.begin() as connection:
        await connection.run_sync(Base.metadata.create_all)
    monkeypatch.setattr(profiles, "async_session", sessions)
    monkeypatch.setattr(summarizer, "async_session", sessions)

    profile = profiles.UserProfile(user_id="7", username="retry-user")
    profile.add_conversation("我喜欢解谜游戏", "记住啦")
    await profile.flush()

    llm_calls = 0

    async def fake_summary(_profile, _interactions):
        nonlocal llm_calls
        llm_calls += 1
        return {
            "impression": "喜欢解谜",
            "atoms": [
                {
                    "content": "用户喜欢解谜游戏",
                    "type": "viewer_preference",
                    "entities": ["解谜游戏"],
                    "relations": [],
                }
            ],
        }

    class FakeStore:
        def __init__(self):
            self.contents: dict[str, set[str]] = {}

        async def source_group_contents(self, _user_id, source_group_id):
            return set(self.contents.get(source_group_id, set()))

    class FakeMemoryEngine:
        def __init__(self):
            self.store = FakeStore()
            self.atoms = []

        async def add_atoms(self, atoms):
            self.atoms.extend(atoms)
            for atom in atoms:
                self.store.contents.setdefault(atom.source_group_id, set()).add(
                    atom.content
                )
            return list(range(1, len(atoms) + 1))

    fake_engine = FakeMemoryEngine()
    monkeypatch.setattr(summarizer, "generate_user_memory_summary", fake_summary)
    monkeypatch.setattr(engine_module, "get_memory_engine", lambda: fake_engine)

    real_acknowledge = profile.acknowledge_summary
    attempts = 0

    async def fail_once(interaction_id, user_turns):
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            raise RuntimeError("simulated crash after atom commit")
        await real_acknowledge(interaction_id, user_turns)

    monkeypatch.setattr(profile, "acknowledge_summary", fail_once)
    with pytest.raises(RuntimeError):
        await summarizer.summarize_if_needed(profile, force=True)
    await summarizer.summarize_if_needed(profile, force=True)

    assert llm_calls == 1
    assert len(fake_engine.atoms) == 1
    assert profile.last_summary_count == 1
    await engine.dispose()


def test_summary_json_parser_accepts_fenced_json():
    parsed = summarizer._parse_json_object(
        """```json
{"impression":"稳定用户","atoms":[]}
```"""
    )
    assert parsed == {"impression": "稳定用户", "atoms": []}


def test_storage_migration_adds_summary_cursor(tmp_path):
    db_path = tmp_path / "legacy.db"
    connection = sqlite3.connect(db_path)
    connection.execute(
        "CREATE TABLE viewer_profiles (user_id TEXT PRIMARY KEY, last_summary_count INTEGER DEFAULT 0)"
    )
    connection.commit()
    connection.close()

    prepare_database(str(db_path))

    connection = sqlite3.connect(db_path)
    try:
        columns = {
            row[1]
            for row in connection.execute("PRAGMA table_info(viewer_profiles)").fetchall()
        }
        assert "last_summarized_interaction_id" in columns
        versions = {
            row[0]
            for row in connection.execute("SELECT version FROM schema_migrations")
        }
        assert 3 in versions
    finally:
        connection.close()
