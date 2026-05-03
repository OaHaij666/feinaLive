"""优先级消息队列 - GameGraph / 弹幕 / 礼物 → HostGraph 统一消费

所有消息由主播 LLM 消费，生成话术后 TTS 输出。

消息来源:
  - game:commentary_request  GameGraph 请求主播解说(带草稿要点) (priority=1)
  - danmaku:danmaku          观众弹幕原文 (priority=2)
  - gift:gift_thanks         礼物感谢 (priority=3)

消费端: HostGraph._host_loop() → 主播 LLM 生成话术 → TTS
"""

import asyncio
import logging
import time
import uuid
from dataclasses import dataclass, field

from apps.ai.messaging.rate_limiter import RateLimiter, get_rate_limiter

logger = logging.getLogger(__name__)

USER_COOLDOWN_SECONDS = 3.0
PRIORITY_INTERRUPT = 0
PRIORITY_HIGH = 1
PRIORITY_NORMAL = 2
PRIORITY_LOW = 3
PRIORITY_DISPOSABLE = 4
PRIORITY_NEVER_DROP = {PRIORITY_INTERRUPT, PRIORITY_HIGH}


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
            self.expire_at = self.created_at + 30

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
        max_size: int = 20,
        default_ttl: float = 30.0,
    ):
        self._queue: asyncio.PriorityQueue[Message] = asyncio.PriorityQueue()
        self._rate_limiter = rate_limiter or get_rate_limiter()
        self._max_size = max_size
        self._default_ttl = default_ttl
        self._pending_merge: dict[str, Message] = {}
        self._cancelled_keys: set[str] = set()
        self._user_last_msg: dict[str, float] = {}
        self._muted: bool = False
        self._total_put: int = 0
        self._total_dropped: int = 0
        self._total_consumed: int = 0

    async def put(self, msg: Message) -> bool:
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
            if time.time() - last < USER_COOLDOWN_SECONDS:
                logger.debug(f"用户冷却: user={msg.user_id} 跳过")
                self._total_dropped += 1
                return False
            self._user_last_msg[msg.user_id] = time.time()

        if self._queue.qsize() >= self._max_size:
            if msg.priority in PRIORITY_NEVER_DROP:
                pass
            elif msg.priority == PRIORITY_NORMAL and msg.allow_skip:
                logger.warning(f"队列已满，丢弃中优先级: {msg.content[:20]}")
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
                continue
            self._total_consumed += 1
            return msg

    async def get_nowait(self) -> Message | None:
        try:
            msg = self._queue.get_nowait()
            if msg.merge_key:
                self._pending_merge.pop(msg.merge_key, None)
            if msg.cancel_key and msg.cancel_key in self._cancelled_keys:
                self._cancelled_keys.discard(msg.cancel_key)
                return None
            if msg.is_expired and msg.allow_skip:
                return None
            self._total_consumed += 1
            return msg
        except asyncio.QueueEmpty:
            return None

    def cancel(self, cancel_key: str):
        self._cancelled_keys.add(cancel_key)
        logger.debug(f"消息取消登记: {cancel_key}")

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
