"""B站直播弹幕客户端"""

import asyncio
import logging
from typing import Callable

from blivedm import BLiveClient, BaseHandler

from .handlers import DanmakuHandler
from .models import DanmakuMessage, GiftMessage, HeartbeatMessage, UserEnterMessage

logger = logging.getLogger(__name__)


class CustomHandler(BaseHandler):
    def __init__(self, handler: DanmakuHandler, callback: Callable):
        self.handler = handler
        self.callback = callback
        self.room_id = 0

    def set_room_id(self, room_id: int):
        self.room_id = room_id

    async def _on_danmaku(self, client: BLiveClient, message: dict):
        msg = self.handler.parse_danmu_msg(message)
        if msg:
            await self.callback("danmaku", msg)

    async def _on_gift(self, client: BLiveClient, message: dict):
        gift = self.handler.parse_gift(message)
        if gift:
            await self.callback("gift", gift)

    async def _on_buy_guard(self, client: BLiveClient, message: dict):
        enter = self.handler.parse_user_enter(message)
        if enter:
            await self.callback("user_enter", enter)

    async def _on_heartbeat(self, client: BLiveClient, popularity: int):
        heartbeat = self.handler.parse_heartbeat(popularity)
        await self.callback("heartbeat", heartbeat)


class BilibiliClient:
    def __init__(self, room_id: int):
        self.room_id = room_id
        self.client: BLiveClient | None = None
        self.handler = DanmakuHandler(room_id)
        self.custom_handler: CustomHandler | None = None
        self._callback: Callable | None = None
        self._task: asyncio.Task | None = None

    def set_callback(self, callback: Callable):
        self._callback = callback

    async def _message_callback(self, msg_type: str, data):
        if self._callback:
            await self._callback(msg_type, data)

    async def connect(self):
        if self.client:
            await self.close()

        self.custom_handler = CustomHandler(self.handler, self._message_callback)
        self.custom_handler.set_room_id(self.room_id)
        self.client = BLiveClient(room_id=self.room_id)
        self.client.add_handler(self.custom_handler)

        logger.info(f"Connecting to room {self.room_id}...")
        self._task = asyncio.create_task(self._run_client())

    async def _run_client(self):
        if self.client:
            try:
                await self.client.start()
            except Exception as e:
                logger.error(f"Client error: {e}")
                raise

    async def close(self):
        if self.client:
            self.client.remove_handler(self.custom_handler)
            self.client.stop()
            self.client = None
        if self._task:
            self._task.cancel()
            self._task = None
        logger.info(f"Disconnected from room {self.room_id}")

    @property
    def is_running(self) -> bool:
        return self.client is not None and self.client._running
