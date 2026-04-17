"""用户画像管理 - 记录用户特征、互动历史、印象摘要"""

import asyncio
import json
import logging
import re
import time
from dataclasses import dataclass, field

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from apps.db import UserProfileDB, async_session

logger = logging.getLogger(__name__)

SUMMARY_INTERVAL = 10
MAX_RECENT_MESSAGES = 16

_user_profiles: dict[str, "UserProfile"] = {}
_db_initialized: bool = False


@dataclass
class UserProfile:
    user_id: str
    username: str
    danmaku_count: int = 0
    interaction_count: int = 0
    key_topics: list[str] = field(default_factory=list)
    impression: str = ""
    long_term_memory: str = ""
    recent_messages: list[dict] = field(default_factory=list)
    last_danmaku: str = ""
    last_interaction: float = field(default_factory=time.time)
    last_summary_count: int = 0
    created_at: float = field(default_factory=time.time)
    _dirty: bool = field(default=False, repr=False)

    def to_dict(self) -> dict:
        return {
            "user_id": self.user_id,
            "username": self.username,
            "danmaku_count": self.danmaku_count,
            "interaction_count": self.interaction_count,
            "key_topics": self.key_topics,
            "impression": self.impression,
            "long_term_memory": self.long_term_memory,
            "recent_messages": self.recent_messages,
            "last_danmaku": self.last_danmaku,
            "last_interaction": self.last_interaction,
            "last_summary_count": self.last_summary_count,
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
            long_term_memory=self.long_term_memory,
            recent_messages=json.dumps(self.recent_messages, ensure_ascii=False),
            last_danmaku=self.last_danmaku,
            last_interaction=self.last_interaction,
            last_summary_count=self.last_summary_count,
            created_at=self.created_at,
        )

    @classmethod
    def from_db_model(cls, db_model: UserProfileDB) -> "UserProfile":
        return cls(
            user_id=db_model.user_id,
            username=db_model.username,
            danmaku_count=db_model.danmaku_count,
            interaction_count=db_model.interaction_count,
            key_topics=json.loads(db_model.key_topics) if db_model.key_topics else [],
            impression=db_model.impression,
            long_term_memory=db_model.long_term_memory,
            recent_messages=json.loads(db_model.recent_messages) if db_model.recent_messages else [],
            last_danmaku=db_model.last_danmaku,
            last_interaction=db_model.last_interaction,
            last_summary_count=db_model.last_summary_count,
            created_at=db_model.created_at,
            _dirty=False,
        )

    def should_summarize(self) -> bool:
        new_interactions = self.interaction_count - self.last_summary_count
        return new_interactions >= SUMMARY_INTERVAL

    def get_memory_context(self) -> str:
        parts = []
        if self.long_term_memory:
            parts.append(f"用户长期记忆：{self.long_term_memory}")
        if self.impression:
            parts.append(f"用户印象：{self.impression}")
        if self.key_topics:
            parts.append(f"用户关注话题：{', '.join(self.key_topics)}")
        if self.recent_messages:
            recent = self.recent_messages[-6:]
            recent_text = "; ".join([f"{m['role']}: {m['content']}" for m in recent])
            parts.append(f"最近对话：{recent_text}")
        return "\n".join(parts) if parts else ""

    def mark_summarized(self):
        self.last_summary_count = self.interaction_count

    def add_conversation(self, user_msg: str, assistant_msg: str):
        self.danmaku_count += 1
        self.interaction_count += 1
        self.last_danmaku = user_msg
        self.last_interaction = time.time()
        self.recent_messages.append({"role": "user", "content": user_msg})
        self.recent_messages.append({"role": "assistant", "content": assistant_msg})
        if len(self.recent_messages) > MAX_RECENT_MESSAGES:
            self.recent_messages = self.recent_messages[-MAX_RECENT_MESSAGES:]
        topics = self._extract_topics(user_msg)
        for topic in topics:
            if topic not in self.key_topics:
                self.key_topics.append(topic)
        if len(self.key_topics) > 10:
            self.key_topics = self.key_topics[-10:]
        self._dirty = True
        asyncio.create_task(self._save_to_db())

    def update_long_term_memory(self, memory: str):
        self.long_term_memory = memory
        logger.info(f"用户 {self.username} 长期记忆已更新: {memory[:50]}...")
        self._dirty = True
        asyncio.create_task(self._save_to_db())

    def update_impression(self, impression: str):
        self.impression = impression
        logger.info(f"用户 {self.username} 印象已更新: {impression[:50]}...")
        self._dirty = True
        asyncio.create_task(self._save_to_db())

    async def _save_to_db(self):
        try:
            async with async_session() as session:
                stmt = select(UserProfileDB).where(UserProfileDB.user_id == self.user_id)
                result = await session.execute(stmt)
                existing = result.scalar_one_or_none()

                if existing:
                    existing.username = self.username
                    existing.danmaku_count = self.danmaku_count
                    existing.interaction_count = self.interaction_count
                    existing.key_topics = json.dumps(self.key_topics, ensure_ascii=False)
                    existing.impression = self.impression
                    existing.long_term_memory = self.long_term_memory
                    existing.recent_messages = json.dumps(self.recent_messages, ensure_ascii=False)
                    existing.last_danmaku = self.last_danmaku
                    existing.last_interaction = self.last_interaction
                    existing.last_summary_count = self.last_summary_count
                else:
                    session.add(self.to_db_model())
                await session.commit()
                self._dirty = False
                logger.debug(f"用户 {self.username} 已保存到数据库")
        except Exception as e:
            logger.error(f"保存用户 {self.username} 到数据库失败: {e}")

    def _extract_topics(self, text: str) -> list[str]:
        topics = []
        patterns = [
            r'(唱歌|音乐|歌曲)',
            r'(游戏|打游戏|玩.*游戏)',
            r'(动漫|动画|番剧)',
            r'(主播|小姐姐|小哥哥)',
            r'(聊天|说话|唠嗑)',
        ]
        for pattern in patterns:
            if pattern in text:
                match = re.search(pattern, text)
                if match:
                    topics.append(match.group(1) if match.groups() else match.group(0))
        return topics


async def load_all_profiles_from_db():
    global _db_initialized
    if _db_initialized:
        return
    try:
        async with async_session() as session:
            result = await session.execute(select(UserProfileDB))
            db_profiles = result.scalars().all()
            for db_p in db_profiles:
                profile = UserProfile.from_db_model(db_p)
                _user_profiles[profile.user_id] = profile
            _db_initialized = True
            logger.info(f"从数据库加载了 {len(db_profiles)} 个用户画像")
    except Exception as e:
        logger.error(f"从数据库加载用户画像失败: {e}")


def get_user_profile(user_id: str, username: str = "") -> UserProfile:
    if user_id not in _user_profiles:
        _user_profiles[user_id] = UserProfile(
            user_id=user_id,
            username=username or user_id,
            created_at=time.time(),
        )
        logger.debug(f"创建新用户画像: {username or user_id}")
    profile = _user_profiles[user_id]
    if username and profile.username != username:
        profile.username = username
        profile._dirty = True
        asyncio.create_task(profile._save_to_db())
    return profile


def get_all_profiles() -> dict[str, UserProfile]:
    return _user_profiles


def get_active_users(hours: int = 24) -> list[UserProfile]:
    cutoff = time.time() - hours * 3600
    return [p for p in _user_profiles.values() if p.last_interaction > cutoff]


def clear_user_profile(user_id: str):
    if user_id in _user_profiles:
        del _user_profiles[user_id]
    asyncio.create_task(_delete_from_db(user_id))


async def _delete_from_db(user_id: str):
    try:
        async with async_session() as session:
            from apps.db import UserProfileDB
            stmt = select(UserProfileDB).where(UserProfileDB.user_id == user_id)
            result = await session.execute(stmt)
            db_profile = result.scalar_one_or_none()
            if db_profile:
                await session.delete(db_profile)
                await session.commit()
                logger.info(f"已从数据库删除用户 {user_id} 的记忆")
    except Exception as e:
        logger.error(f"从数据库删除用户记忆失败: {e}")


async def save_all_profiles():
    for profile in _user_profiles.values():
        if profile._dirty:
            await profile._save_to_db()
    logger.info(f"保存了 {len(_user_profiles)} 个用户画像到数据库")


async def init_user_profiles():
    await load_all_profiles_from_db()
