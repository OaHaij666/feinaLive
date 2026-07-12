"""Lifecycle and queue consumption runtime for the AI host."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from enum import Enum

from apps.ai.host_brain import AIHostBrain, get_host_brain
from apps.ai.host_messages import HostMessageProcessor, ReplyCallback
from apps.ai.messaging.queue import Message, PriorityMessageQueue, get_message_queue

logger = logging.getLogger(__name__)

MessageHandler = Callable[[Message], Awaitable[None]]


class HostRuntimeState(str, Enum):
    STOPPED = "stopped"
    STARTING = "starting"
    RUNNING = "running"
    STOPPING = "stopping"
    FAILED = "failed"


class HostRuntime:
    """Supervise HostBrain admission polling and the single host consumer."""

    def __init__(
        self,
        on_reply: ReplyCallback | None = None,
        *,
        brain: AIHostBrain | None = None,
        queue: PriorityMessageQueue | None = None,
        processor: HostMessageProcessor | None = None,
    ) -> None:
        self._brain = brain or get_host_brain()
        self._queue = queue or get_message_queue()
        self._processor = processor or HostMessageProcessor(on_reply=on_reply)
        self._state = HostRuntimeState.STOPPED
        self._task: asyncio.Task[None] | None = None
        self._lifecycle_lock = asyncio.Lock()
        self._handlers: dict[str, MessageHandler] = {
            "prepared_speech": self._processor.handle_prepared_speech,
            "danmaku": self._processor.handle_danmaku,
            "gift_thanks": self._processor.handle_gift,
        }

    @property
    def state(self) -> HostRuntimeState:
        return self._state

    @property
    def is_running(self) -> bool:
        return self._state is HostRuntimeState.RUNNING

    async def start(self) -> None:
        async with self._lifecycle_lock:
            if self._state in {HostRuntimeState.STARTING, HostRuntimeState.RUNNING}:
                logger.warning("主播 Runtime 已在运行")
                return

            self._state = HostRuntimeState.STARTING
            try:
                await self._brain.start_polling()
                self._task = asyncio.create_task(
                    self._consume_loop(),
                    name="host-runtime-consumer",
                )
            except Exception:
                self._state = HostRuntimeState.FAILED
                await self._brain.stop_polling()
                raise
            self._state = HostRuntimeState.RUNNING
            logger.info("主播 Runtime 启动")

    async def stop(self) -> None:
        async with self._lifecycle_lock:
            if self._state is HostRuntimeState.STOPPED:
                return
            self._state = HostRuntimeState.STOPPING
            await self._brain.stop_polling()
            task = self._task
            self._task = None
            if task and not task.done():
                task.cancel()
                try:
                    await task
                except asyncio.CancelledError:
                    pass
            self._state = HostRuntimeState.STOPPED
            logger.info("主播 Runtime 停止")

    async def process_next(self, timeout: float | None = None) -> Message:
        """Consume one message; useful for deterministic tests and supervision."""

        self._queue.apply_priority_override()
        if timeout is None:
            message = await self._queue.get()
        else:
            message = await asyncio.wait_for(self._queue.get(), timeout=timeout)
        await self._dispatch(message)
        return message

    async def _consume_loop(self) -> None:
        while self._state is HostRuntimeState.RUNNING:
            try:
                await self.process_next(timeout=5.0)
            except asyncio.TimeoutError:
                continue
            except asyncio.CancelledError:
                raise
            except Exception:
                # A failed message must not terminate the only queue consumer.
                logger.exception("主播 Runtime 消费消息失败")

    async def _dispatch(self, message: Message) -> None:
        handler = self._handlers.get(message.msg_type)
        if handler is None:
            logger.warning("未知消息类型: %s", message.msg_type)
            return
        try:
            await handler(message)
        except asyncio.CancelledError:
            raise
        except Exception as exc:
            await self._processor.fail(message, exc)
            logger.error(
                "主播消息处理失败: id=%s type=%s error=%s",
                message.id,
                message.msg_type,
                exc,
                exc_info=True,
            )
