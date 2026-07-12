"""Danmaku admission, buffering, selection and queueing for HostRuntime."""

import asyncio
import logging
import time

from apps.ai.admin_commands import get_admin_handler
from apps.ai.history import get_session
from apps.ai.messaging.dynamic_priority import get_priority_manager
from apps.ai.messaging.queue import Message, get_message_queue
from apps.config import config
from apps.live.room_session import RoomSessionContext, get_room_session_manager

logger = logging.getLogger(__name__)


class DanmakuInput:
    def __init__(
        self,
        context: RoomSessionContext,
        msg_id: str = "",
        user: str = "",
        content: str = "",
        timestamp: float = 0,
        uid: int = 0,
    ):
        self.context = context
        self.msg_id = msg_id
        self.user = user
        self.content = content
        self.timestamp = timestamp or time.time()
        self.uid = uid

    def to_dict(self) -> dict:
        return {
            "context": self.context.to_dict(),
            "msg_id": self.msg_id,
            "user": self.user,
            "content": self.content,
            "timestamp": self.timestamp,
            "uid": self.uid,
        }


class AIHostBrain:
    POLL_INTERVAL_SECONDS = config.ai_poll_interval_seconds

    def __init__(self):
        self._danmaku_buffer: list[DanmakuInput] = []
        self._admin_handler = get_admin_handler()
        self._poll_running: bool = False
        self._poll_task: asyncio.Task | None = None

    def push_danmaku(
        self,
        context: RoomSessionContext,
        msg_id: str,
        user: str,
        content: str,
        uid: int = 0,
    ) -> bool:
        if not get_room_session_manager().is_current(context):
            logger.debug("Rejected stale danmaku at HostBrain boundary: %s", context)
            return False
        if content.strip() == "/clear":
            from apps.ai.memory import clear_user_profile
            clear_user_profile(str(uid) if uid else user)
            logger.info(f"用户 {user} 清除了自己的记忆")
            return False

        cmd_result = self._admin_handler.sync_handle(uid, user, content)
        if cmd_result:
            logger.info(f"Admin command executed: {cmd_result.message}")
            return False

        if not self._admin_handler.should_process_danmaku(uid, user):
            logger.debug(f"弹幕被过滤 (sleep模式): [{user}] {content}")
            return False

        danmaku = DanmakuInput(
            context=context,
            msg_id=msg_id,
            user=user,
            content=content,
            uid=uid,
        )
        self._danmaku_buffer = [
            item
            for item in self._danmaku_buffer
            if get_room_session_manager().is_current(item.context)
        ]
        self._danmaku_buffer.append(danmaku)
        if len(self._danmaku_buffer) > 20:
            self._danmaku_buffer = self._danmaku_buffer[-20:]
        logger.debug(f"弹幕入缓冲: [{user}] {content}")
        return True

    async def start_polling(self):
        if self._poll_running:
            return
        self._poll_running = True
        self._poll_task = asyncio.create_task(self._poll_loop())
        logger.info(f"弹幕轮询启动 (间隔={self.POLL_INTERVAL_SECONDS}s)")

    async def stop_polling(self):
        self._poll_running = False
        if self._poll_task and not self._poll_task.done():
            self._poll_task.cancel()
            try:
                await self._poll_task
            except asyncio.CancelledError:
                pass
        logger.info("弹幕轮询停止")

    async def _poll_loop(self):
        while self._poll_running:
            try:
                await asyncio.sleep(self.POLL_INTERVAL_SECONDS)
                await self._poll_danmaku()
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"弹幕轮询异常: {e}", exc_info=True)
                await asyncio.sleep(1)

    async def _poll_danmaku(self):
        if self._admin_handler.get_state().is_sleeping:
            return

        unanswered = [
            d for d in self.get_unanswered()
            if self._admin_handler.should_process_danmaku(d.uid, d.user)
        ]
        if not unanswered:
            return

        await self._enqueue_danmaku(unanswered)

    def get_unanswered(self) -> list[DanmakuInput]:
        unanswered = []
        for d in self._danmaku_buffer:
            if not get_room_session_manager().is_current(d.context):
                continue
            history = get_session(d.context.session_id)
            if not history.is_answered(d.msg_id):
                unanswered.append(d)
        return unanswered

    async def try_reply(self) -> bool:
        if self._admin_handler.get_state().is_sleeping:
            return False

        unanswered = [
            d for d in self.get_unanswered()
            if self._admin_handler.should_process_danmaku(d.uid, d.user)
        ]
        if not unanswered:
            return False

        return await self._enqueue_danmaku(unanswered)

    async def _enqueue_danmaku(self, unanswered: list[DanmakuInput]) -> bool:
        if not unanswered:
            return False

        first = unanswered[0]
        context = first.context
        if not get_room_session_manager().is_current(context):
            return False
        user = first.user
        combined_contents = [first.content]
        combined_msg_ids = [first.msg_id]

        for d in unanswered[1:]:
            if d.user == user and d.context == context:
                combined_contents.append(d.content)
                combined_msg_ids.append(d.msg_id)
            else:
                break

        combined_text = "\n".join(combined_contents)
        pm = get_priority_manager()
        priority = pm.get_danmaku_priority()

        queue = get_message_queue()
        enqueued = await queue.put(Message(
            priority=priority,
            source="danmaku",
            msg_type="danmaku",
            content=combined_text,
            data={"user": user, "uid": first.uid, "msg_id": first.msg_id},
            context=context.to_dict(),
            user_id=str(first.uid),
            expire_at=time.time() + 60,
        ))

        if enqueued:
            # Only commit admission after the queue accepted the message. A
            # muted/full/rate-limited queue must leave it eligible for retry.
            history = get_session(context.session_id)
            history.mark_answered_batch(combined_msg_ids)
            logger.debug(f"弹幕入队: [{user}] {combined_text[:30]} (优先级={priority})")

        return enqueued

    def clear_buffer(self):
        self._danmaku_buffer.clear()

    @property
    def buffer_size(self) -> int:
        return len(self._danmaku_buffer)

    @property
    def unanswered_count(self) -> int:
        return len(self.get_unanswered())


_brain: AIHostBrain | None = None


def get_host_brain() -> AIHostBrain:
    """Return the one admission brain behind the authoritative room session."""

    global _brain
    if _brain is None:
        _brain = AIHostBrain()
    return _brain


def reset_host_brains():
    """Clear the HostBrain singleton for tests or application restart."""

    global _brain
    _brain = None
