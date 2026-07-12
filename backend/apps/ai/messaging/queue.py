"""优先级消息队列 - GameGraph / 弹幕 / 礼物 → HostRuntime 统一消费

所有消息由主播 LLM 消费，生成话术后 TTS 输出。

消息来源:
  - game:commentary_request  GameGraph 请求主播解说(带草稿要点) (priority=2)
  - danmaku:danmaku          观众弹幕原文 (priority=3)
  - gift:gift_thanks         礼物感谢 (priority=动态)

消费端: HostRuntime → 主播 LLM 生成话术 → TTS
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from apps.ai.messaging.dynamic_priority import (
    PRIORITY_HIGH,
    PRIORITY_HIGHEST,
    PRIORITY_LOW,
    PRIORITY_NORMAL,
    get_priority_manager,
)
from apps.ai.messaging.rate_limiter import RateLimiter, get_rate_limiter
from apps.config import config
from apps.live.room_session import RoomSessionContext, get_room_session_manager

logger = logging.getLogger(__name__)

PRIORITY_NEVER_DROP = {PRIORITY_HIGHEST, PRIORITY_HIGH}
# Defaults from config, read at import time
_USER_COOLDOWN_SECONDS = config.messaging_user_cooldown_seconds
_DEFAULT_TTL_SECONDS = config.messaging_default_ttl_seconds


@dataclass
class Message:
    id: str = ""
    priority: int = PRIORITY_NORMAL
    source: str = ""
    msg_type: str = "tts"
    content: str = ""
    data: dict = field(default_factory=dict)
    context: dict = field(default_factory=dict)
    created_at: float = 0.0
    expire_at: float = 0.0
    allow_skip: bool = True
    merge_key: str = ""
    cancel_key: str = ""
    user_id: str = ""

    def __post_init__(self):
        if not self.id:
            self.id = str(uuid.uuid4())[:8]
        if not self.created_at:
            self.created_at = time.time()
        if not self.expire_at:
            self.expire_at = self.created_at + _DEFAULT_TTL_SECONDS

    @property
    def is_expired(self) -> bool:
        return time.time() > self.expire_at

    @property
    def age_seconds(self) -> float:
        return time.time() - self.created_at

    def __lt__(self, other: "Message") -> bool:
        if self.priority != other.priority:
            return self.priority < other.priority
        return self.created_at < other.created_at


class PriorityMessageQueue:
    def __init__(
        self,
        rate_limiter: RateLimiter | None = None,
        max_size: int | None = None,
        default_ttl: float | None = None,
    ):
        default_ttl = default_ttl or _DEFAULT_TTL_SECONDS
        self._queue: asyncio.PriorityQueue[Message] = asyncio.PriorityQueue()
        self._rate_limiter = rate_limiter or get_rate_limiter()
        self._max_size = max_size if max_size is not None else config.game_queue_max_size
        self._default_ttl = default_ttl
        self._pending_merge: dict[str, Message] = {}
        self._cancelled_keys: set[str] = set()
        self._user_last_msg: dict[str, float] = {}
        self._muted: bool = False
        self._total_put: int = 0
        self._total_dropped: int = 0
        self._total_consumed: int = 0

    async def put(self, msg: Message) -> bool:
        if msg.context:
            context = RoomSessionContext.from_mapping(msg.context)
            if context is None or not get_room_session_manager().is_current(context):
                logger.debug("Dropped message outside the active room session: %s", msg.context)
                self._total_dropped += 1
                return False
        elif msg.source in {"danmaku", "gift"}:
            logger.debug("Dropped room message without routing context: %s", msg.source)
            self._total_dropped += 1
            return False

        if self._muted:
            logger.debug("队列全局静音，消息丢弃")
            self._total_dropped += 1
            return False

        if msg.cancel_key and msg.cancel_key in self._cancelled_keys:
            logger.debug(f"消息已被取消: cancel_key={msg.cancel_key}")
            self._cancelled_keys.discard(msg.cancel_key)
            self._total_dropped += 1
            return False

        if not self._rate_limiter.allow(msg.source, msg.msg_type):
            logger.debug(f"频率限制: {msg.source}:{msg.msg_type} 跳过")
            self._total_dropped += 1
            return False

        if msg.user_id:
            last = self._user_last_msg.get(msg.user_id, 0)
            if time.time() - last < _USER_COOLDOWN_SECONDS:
                logger.debug(f"用户冷却: user={msg.user_id} 跳过")
                self._total_dropped += 1
                return False
            self._user_last_msg[msg.user_id] = time.time()

        pm = get_priority_manager()
        if msg.source == "danmaku" and pm.danmaku_priority_override is not None:
            original = msg.priority
            msg.priority = pm.danmaku_priority_override
            logger.debug(f"弹幕优先级覆盖: {original} → {msg.priority}")
        elif msg.source == "gift" and pm.gift_priority_override is not None:
            original = msg.priority
            msg.priority = pm.gift_priority_override
            logger.debug(f"礼物优先级覆盖: {original} → {msg.priority}")

        if self._queue.qsize() >= self._max_size:
            if msg.priority in PRIORITY_NEVER_DROP:
                pass
            elif msg.priority == PRIORITY_NORMAL and msg.allow_skip:
                logger.warning(f"队列已满，丢弃普通优先级: {msg.content[:20]}")
                self._total_dropped += 1
                return False
            elif msg.priority >= PRIORITY_LOW:
                logger.debug(f"队列已满，丢弃低优先级: {msg.content[:20]}")
                self._total_dropped += 1
                return False

        if msg.merge_key:
            existing = self._pending_merge.get(msg.merge_key)
            if existing:
                existing.content += f"、{msg.content}"
                logger.debug(f"消息合并: {msg.merge_key}")
                self._total_put += 1
                return True
            self._pending_merge[msg.merge_key] = msg

        await self._queue.put(msg)
        self._total_put += 1
        logger.debug(f"消息入队: [{msg.priority}]{msg.source}/{msg.msg_type} {msg.content[:30]}")
        return True

    async def get(self) -> Message:
        while True:
            msg = await self._queue.get()
            if msg.merge_key:
                self._pending_merge.pop(msg.merge_key, None)
            if msg.cancel_key and msg.cancel_key in self._cancelled_keys:
                logger.debug(f"消费时发现已取消: cancel_key={msg.cancel_key}")
                self._cancelled_keys.discard(msg.cancel_key)
                continue
            if msg.is_expired and msg.allow_skip:
                logger.debug(f"消息已过期，跳过: {msg.content[:20]}")
                self._total_dropped += 1
                continue
            context = RoomSessionContext.from_mapping(msg.context)
            if msg.context and context is None:
                logger.debug("Dropped queued message with malformed context: %s", msg.context)
                self._total_dropped += 1
                continue
            if context is not None and not get_room_session_manager().is_current(context):
                logger.debug("Dropped stale queued message: %s", msg.context)
                self._total_dropped += 1
                continue
            self._total_consumed += 1
            self._record_consumption(msg)
            return msg

    def _record_consumption(self, msg: Message):
        pm = get_priority_manager()
        if msg.source == "danmaku":
            pm.record_danmaku_consumed()
        elif msg.source == "gift":
            pm.record_gift_consumed()

    async def get_nowait(self) -> Message | None:
        try:
            msg = self._queue.get_nowait()
            if msg.merge_key:
                self._pending_merge.pop(msg.merge_key, None)
            if msg.cancel_key and msg.cancel_key in self._cancelled_keys:
                self._cancelled_keys.discard(msg.cancel_key)
                return None
            if msg.is_expired and msg.allow_skip:
                self._total_dropped += 1
                return None
            context = RoomSessionContext.from_mapping(msg.context)
            if msg.context and context is None:
                self._total_dropped += 1
                return None
            if context is not None and not get_room_session_manager().is_current(context):
                self._total_dropped += 1
                return None
            self._total_consumed += 1
            self._record_consumption(msg)
            return msg
        except asyncio.QueueEmpty:
            return None

    def apply_priority_override(self):
        """重建队列，应用当前的优先级覆盖（降级/升级队列中已有消息）"""
        pm = get_priority_manager()
        danmaku_override = pm.danmaku_priority_override
        gift_override = pm.gift_priority_override

        if danmaku_override is None and gift_override is None:
            return

        if self._queue.empty():
            return

        temp_list: list[Message] = []
        while True:
            try:
                msg = self._queue.get_nowait()
                temp_list.append(msg)
            except asyncio.QueueEmpty:
                break

        changed = 0
        for msg in temp_list:
            if msg.source == "danmaku" and danmaku_override is not None:
                if msg.priority != danmaku_override:
                    msg.priority = danmaku_override
                    changed += 1
            elif msg.source == "gift" and gift_override is not None:
                if msg.priority != gift_override:
                    msg.priority = gift_override
                    changed += 1

        for msg in temp_list:
            self._queue.put_nowait(msg)

        if changed > 0:
            logger.info(f"队列优先级调整完成: {changed}条消息")

    def cancel(self, cancel_key: str):
        self._cancelled_keys.add(cancel_key)
        logger.debug(f"消息取消登记: {cancel_key}")

    async def cancel_by_type(self, msg_type: str):
        """取消队列中指定类型的所有未消费消息"""
        temp_list: list[Message] = []
        cancelled = 0
        while True:
            try:
                msg = self._queue.get_nowait()
                if msg.msg_type == msg_type:
                    cancelled += 1
                    self._total_dropped += 1
                else:
                    temp_list.append(msg)
            except asyncio.QueueEmpty:
                break
        for msg in temp_list:
            self._queue.put_nowait(msg)
        if cancelled > 0:
            logger.info(f"已取消 {cancelled} 条 {msg_type} 类型消息")

    def mute(self):
        self._muted = True
        logger.info("消息队列已静音")

    def unmute(self):
        self._muted = False
        logger.info("消息队列已取消静音")

    @property
    def size(self) -> int:
        return self._queue.qsize()

    @property
    def is_empty(self) -> bool:
        return self._queue.empty()

    def get_stats(self) -> dict:
        return {
            "size": self._queue.qsize(),
            "max_size": self._max_size,
            "muted": self._muted,
            "total_put": self._total_put,
            "total_dropped": self._total_dropped,
            "total_consumed": self._total_consumed,
            "drop_rate": f"{self._total_dropped / max(self._total_put, 1) * 100:.1f}%",
        }


_message_queue: PriorityMessageQueue | None = None


def get_message_queue() -> PriorityMessageQueue:
    global _message_queue
    if _message_queue is None:
        _message_queue = PriorityMessageQueue()
    return _message_queue
