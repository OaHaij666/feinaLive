"""用户画像管理 - 记录用户特征、互动历史、印象摘要"""

import logging
import re
import time
from dataclasses import dataclass, field
from typing import Optional

logger = logging.getLogger(__name__)

SUMMARY_INTERVAL = 10
MAX_RECENT_MESSAGES = 16  # 8轮对话 (用户弹幕+主播回复)


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

    def should_summarize(self) -> bool:
        new_interactions = self.interaction_count - self.last_summary_count
        return new_interactions >= SUMMARY_INTERVAL

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

    def update_long_term_memory(self, memory: str):
        self.long_term_memory = memory
        logger.info(f"用户 {self.username} 长期记忆已更新: {memory[:50]}...")

    def update_impression(self, impression: str):
        self.impression = impression
        logger.info(f"用户 {self.username} 印象已更新: {impression[:50]}...")

    def _extract_topics(self, text: str) -> list[str]:
        topics = []
        patterns = [
            r'(唱歌|音乐|歌曲)',
            r'(美食|吃|喝|好吃)',
            r'(游戏|玩|打游戏)',
            r'(电影|剧|番|动漫)',
            r'(睡觉|休息|累)',
            r'(工作|上班|下班)',
            r'(学习|考试|作业)',
        ]
        for pattern in patterns:
            match = re.search(pattern, text)
            if match:
                topics.append(match.group(1))
        return topics

    def get_memory_context(self) -> str:
        parts = []
        if self.long_term_memory:
            parts.append(f"【用户长期记忆】{self.long_term_memory}")
        if self.impression:
            parts.append(f"【用户印象】{self.impression}")
        if self.key_topics:
            topics_str = "、".join(self.key_topics[:5])
            parts.append(f"【兴趣话题】{topics_str}")
        if self.recent_messages and self.danmaku_count >= 3:
            history_lines = []
            for m in self.recent_messages[-10:]:
                prefix = "用户" if m["role"] == "user" else "主播"
                history_lines.append(f"{prefix}: {m['content']}")
            parts.append(f"【近期互动】\n" + "\n".join(history_lines))
        return "\n\n".join(parts) if parts else ""


_user_profiles: dict[str, UserProfile] = {}


def get_user_profile(user_id: str, username: str = "") -> UserProfile:
    if user_id not in _user_profiles:
        _user_profiles[user_id] = UserProfile(
            user_id=user_id,
            username=username or user_id,
        )
    profile = _user_profiles[user_id]
    if username and profile.username != username:
        profile.username = username
    return profile


def clear_user_profile(user_id: str) -> bool:
    if user_id in _user_profiles:
        del _user_profiles[user_id]
        logger.info(f"用户 {user_id} 画像已清除")
        return True
    return False


def get_all_profiles() -> dict[str, UserProfile]:
    return _user_profiles.copy()


def get_active_users(hours: int = 24) -> list[UserProfile]:
    cutoff = time.time() - (hours * 3600)
    return [p for p in _user_profiles.values() if p.last_interaction >= cutoff]
