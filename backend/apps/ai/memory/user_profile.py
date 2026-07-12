"""Viewer profile cache backed by SQLite.

Profiles contain current aggregates and an impression. Durable user facts are
memory atoms; recent conversation turns have their own append-only table.
"""

from __future__ import annotations

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field

from sqlalchemy import delete, select

from apps.config import config
from apps.db import UserProfileDB, ViewerInteractionDB, async_session, init_db

logger = logging.getLogger(__name__)

SUMMARY_INTERVAL = config.ai_summary_interval
MAX_RECENT_MESSAGES = config.ai_max_recent_messages
_user_profiles: dict[str, "UserProfile"] = {}
_db_initialized = False


@dataclass
class UserProfile:
    user_id: str
    username: str
    danmaku_count: int = 0
    interaction_count: int = 0
    key_topics: list[str] = field(default_factory=list)
    impression: str = ""
    recent_messages: list[dict] = field(default_factory=list)
    last_danmaku: str = ""
    last_interaction: float = field(default_factory=time.time)
    last_summary_count: int = 0
    last_summarized_interaction_id: int = 0
    created_at: float = field(default_factory=time.time)
    _dirty: bool = field(default=False, repr=False)
    _pending_interactions: list[tuple[str, str, float]] = field(default_factory=list, repr=False)
    _save_lock: asyncio.Lock = field(default_factory=asyncio.Lock, repr=False)
    _save_task: asyncio.Task | None = field(default=None, repr=False)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "danmaku_count": self.danmaku_count,
            "interaction_count": self.interaction_count,
            "key_topics": self.key_topics,
            "impression": self.impression,
            "recent_messages": self.recent_messages,
            "last_danmaku": self.last_danmaku,
            "last_interaction": self.last_interaction,
            "last_summary_count": self.last_summary_count,
            "last_summarized_interaction_id": self.last_summarized_interaction_id,
            "created_at": self.created_at,
        }

    def to_db_model(self) -> UserProfileDB:
        return UserProfileDB(
            user_id=self.user_id,
            username=self.username,
            danmaku_count=self.danmaku_count,
            interaction_count=self.interaction_count,
            key_topics=json.dumps(self.key_topics, ensure_ascii=False),
            impression=self.impression,
            last_danmaku=self.last_danmaku,
            last_interaction=self.last_interaction,
            last_summary_count=self.last_summary_count,
            last_summarized_interaction_id=self.last_summarized_interaction_id,
            created_at=self.created_at,
        )

    @classmethod
    def from_db_model(cls, row: UserProfileDB, recent_messages: list[dict] | None = None) -> "UserProfile":
        return cls(
            user_id=row.user_id,
            username=row.username,
            danmaku_count=row.danmaku_count,
            interaction_count=row.interaction_count,
            key_topics=json.loads(row.key_topics) if row.key_topics else [],
            impression=row.impression,
            recent_messages=recent_messages or [],
            last_danmaku=row.last_danmaku,
            last_interaction=float(row.last_interaction),
            last_summary_count=row.last_summary_count,
            last_summarized_interaction_id=row.last_summarized_interaction_id,
            created_at=float(row.created_at),
        )

    def should_summarize(self) -> bool:
        return self.interaction_count - self.last_summary_count >= SUMMARY_INTERVAL

    def get_memory_context(self) -> str:
        parts: list[str] = []
        if self.impression:
            parts.append(f"用户印象：{self.impression}")
        if self.key_topics:
            parts.append(f"用户关注话题：{', '.join(self.key_topics)}")
        if self.recent_messages:
            text = "; ".join(f"{m['role']}: {m['content']}" for m in self.recent_messages[-6:])
            parts.append(f"最近对话：{text}")
        return "\n".join(parts)

    def mark_summarized(self, interaction_id: int, user_turns: int) -> None:
        self.last_summarized_interaction_id = max(
            self.last_summarized_interaction_id, interaction_id
        )
        self.last_summary_count = min(
            self.interaction_count, self.last_summary_count + user_turns
        )
        self._dirty = True

    def add_conversation(self, user_msg: str, assistant_msg: str) -> None:
        now = time.time()
        self.danmaku_count += 1
        self.interaction_count += 1
        self.last_danmaku = user_msg
        self.last_interaction = now
        turns = [("user", user_msg, now), ("assistant", assistant_msg, now)]
        self._pending_interactions.extend(turns)
        self.recent_messages.extend({"role": role, "content": content} for role, content, _ in turns)
        self.recent_messages = self.recent_messages[-MAX_RECENT_MESSAGES:]
        for topic in self._extract_topics(user_msg):
            if topic not in self.key_topics:
                self.key_topics.append(topic)
        self.key_topics = self.key_topics[-10:]
        self._dirty = True
        self._schedule_save()

    def update_impression(self, impression: str) -> None:
        self.impression = impression
        self._dirty = True
        self._schedule_save()

    async def flush(self) -> None:
        """Persist queued turns before a summarizer reads its durable queue."""

        task = self._save_task
        if task and not task.done():
            await task
        if self._dirty or self._pending_interactions:
            await self._save_to_db()

    async def acknowledge_summary(self, interaction_id: int, user_turns: int) -> None:
        """Advance the summary cursor while retaining a small recent-context FIFO."""

        self.mark_summarized(interaction_id, user_turns)
        async with self._save_lock:
            async with async_session() as session:
                existing = (
                    await session.execute(
                        select(UserProfileDB).where(UserProfileDB.user_id == self.user_id)
                    )
                ).scalar_one()
                existing.username = self.username
                existing.danmaku_count = self.danmaku_count
                existing.interaction_count = self.interaction_count
                existing.key_topics = json.dumps(self.key_topics, ensure_ascii=False)
                existing.impression = self.impression
                existing.last_danmaku = self.last_danmaku
                existing.last_interaction = self.last_interaction
                existing.last_summary_count = self.last_summary_count
                existing.last_summarized_interaction_id = (
                    self.last_summarized_interaction_id
                )

                keep_ids = list(
                    reversed(
                        (
                            await session.execute(
                                select(ViewerInteractionDB.id)
                                .where(ViewerInteractionDB.user_id == self.user_id)
                                .order_by(ViewerInteractionDB.id.desc())
                                .limit(MAX_RECENT_MESSAGES)
                            )
                        ).scalars().all()
                    )
                )
                prune = delete(ViewerInteractionDB).where(
                    ViewerInteractionDB.user_id == self.user_id,
                    ViewerInteractionDB.id <= interaction_id,
                )
                if keep_ids:
                    prune = prune.where(ViewerInteractionDB.id.not_in(keep_ids))
                await session.execute(prune)
                await session.commit()
                self._dirty = False

    def _schedule_save(self) -> None:
        if self._save_task is None or self._save_task.done():
            self._save_task = asyncio.create_task(self._save_to_db())

    async def _save_to_db(self) -> None:
        async with self._save_lock:
            while self._dirty or self._pending_interactions:
                pending = list(self._pending_interactions)
                self._pending_interactions.clear()
                self._dirty = False
                try:
                    async with async_session() as session:
                        existing = (await session.execute(select(UserProfileDB).where(UserProfileDB.user_id == self.user_id))).scalar_one_or_none()
                        if existing is None:
                            existing = self.to_db_model()
                            session.add(existing)
                            await session.flush()
                        else:
                            existing.username = self.username
                            existing.danmaku_count = self.danmaku_count
                            existing.interaction_count = self.interaction_count
                            existing.key_topics = json.dumps(self.key_topics, ensure_ascii=False)
                            existing.impression = self.impression
                            existing.last_danmaku = self.last_danmaku
                            existing.last_interaction = self.last_interaction
                            existing.last_summary_count = self.last_summary_count
                            existing.last_summarized_interaction_id = (
                                self.last_summarized_interaction_id
                            )
                        for role, content, created_at in pending:
                            session.add(ViewerInteractionDB(user_id=self.user_id, role=role, content=content, created_at=created_at))
                        await session.commit()
                except Exception:
                    self._pending_interactions[:0] = pending
                    self._dirty = True
                    logger.exception("保存用户 %s 画像失败", self.user_id)
                    break

    @staticmethod
    def _extract_topics(text: str) -> list[str]:
        patterns = [r"(唱歌|音乐|歌曲)", r"(游戏|打游戏|玩.*游戏)", r"(动漫|动画|番剧)", r"(主播|小姐姐|小哥哥)", r"(聊天|说话|唠嗑)"]
        topics: list[str] = []
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                topics.append(match.group(1) if match.groups() else match.group(0))
        return topics


async def load_all_profiles_from_db() -> None:
    global _db_initialized
    if _db_initialized:
        return
    await init_db()
    async with async_session() as session:
        profiles = (await session.execute(select(UserProfileDB))).scalars().all()
        for row in profiles:
            turns = (await session.execute(select(ViewerInteractionDB).where(ViewerInteractionDB.user_id == row.user_id).order_by(ViewerInteractionDB.created_at.desc(), ViewerInteractionDB.id.desc()).limit(MAX_RECENT_MESSAGES))).scalars().all()
            recent = [{"role": turn.role, "content": turn.content} for turn in reversed(turns)]
            _user_profiles[row.user_id] = UserProfile.from_db_model(row, recent)
    _db_initialized = True


def get_user_profile(user_id: str, username: str = "") -> UserProfile:
    if user_id not in _user_profiles:
        _user_profiles[user_id] = UserProfile(user_id=user_id, username=username or user_id)
    profile = _user_profiles[user_id]
    if username and profile.username != username:
        profile.username = username
        profile._dirty = True
        profile._schedule_save()
    return profile


def get_all_profiles() -> dict[str, UserProfile]:
    return _user_profiles


def get_active_users(hours: int = 24) -> list[UserProfile]:
    cutoff = time.time() - hours * 3600
    return [profile for profile in _user_profiles.values() if profile.last_interaction > cutoff]


def clear_user_profile(user_id: str) -> None:
    _user_profiles.pop(user_id, None)
    asyncio.create_task(_delete_from_db(user_id))


async def _delete_from_db(user_id: str) -> None:
    async with async_session() as session:
        row = (await session.execute(select(UserProfileDB).where(UserProfileDB.user_id == user_id))).scalar_one_or_none()
        if row:
            await session.delete(row)
            await session.commit()
    try:
        from apps.ai.memory.engine import get_memory_engine

        await get_memory_engine().store.delete_user_memories(user_id)
    except Exception:
        logger.exception("删除用户 %s 的原子记忆失败", user_id)


async def save_all_profiles() -> None:
    for profile in _user_profiles.values():
        if profile._dirty or profile._pending_interactions:
            await profile._save_to_db()


async def init_user_profiles() -> None:
    await load_all_profiles_from_db()
