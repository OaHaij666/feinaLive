"""B站直播弹幕客户端"""

import asyncio
import logging
import urllib.parse
from typing import Callable

import aiohttp
from blivedm import BLiveClient, BaseHandler
from blivedm.models import web as web_models

from apps.config import config

logger = logging.getLogger(__name__)


class DanmakuData:
    def __init__(self, msg: web_models.DanmakuMessage):
        self.uid = msg.uid
        self.user = msg.uname
        self.content = msg.msg
        self.timestamp = msg.timestamp
        self.color = msg.color
        self.medal_level = msg.medal_level
        self.medal_name = msg.medal_name
        self.privilege_type = msg.privilege_type

    def to_dict(self):
        return {
            "uid": self.uid,
            "user": self.user,
            "content": self.content,
            "timestamp": self.timestamp,
            "color": self.color,
            "medal_level": self.medal_level,
            "medal_name": self.medal_name,
            "privilege_type": self.privilege_type,
        }


class GiftData:
    def __init__(self, msg: web_models.GiftMessage):
        self.uid = msg.uid
        self.uname = msg.uname
        self.gift_name = msg.gift_name
        self.num = msg.num
        self.total_coin = msg.total_coin

    def to_dict(self):
        return {
            "uid": self.uid,
            "uname": self.uname,
            "gift_name": self.gift_name,
            "num": self.num,
            "total_coin": self.total_coin,
        }


class CustomHandler(BaseHandler):
    def __init__(self, callback: Callable):
        self.callback = callback
        self.room_id = 0

    def set_room_id(self, room_id: int):
        self.room_id = room_id

    def _on_heartbeat(self, client: BLiveClient, message: web_models.HeartbeatMessage):
        pass

    def _on_danmaku(self, client: BLiveClient, message: web_models.DanmakuMessage):
        asyncio.create_task(self.callback("danmaku", DanmakuData(message)))

    def _on_gift(self, client: BLiveClient, message: web_models.GiftMessage):
        asyncio.create_task(self.callback("gift", GiftData(message)))

    def _on_buy_guard(self, client: BLiveClient, message: web_models.GuardBuyMessage):
        pass

    def _on_super_chat(self, client: BLiveClient, message: web_models.SuperChatMessage):
        pass


class BilibiliClient:
    def __init__(self, room_id: int):
        self.room_id = room_id
        self.client: BLiveClient | None = None
        self.custom_handler: CustomHandler | None = None
        self._callback: Callable | None = None
        self._task: asyncio.Task | None = None
        self._session: aiohttp.ClientSession | None = None

    def set_callback(self, callback: Callable):
        self._callback = callback

    async def _message_callback(self, msg_type: str, data):
        if self._callback:
            await self._callback(msg_type, data)

    def _get_sessdata(self) -> str | None:
        raw_sessdata = config.bilibili_sessdata
        if not raw_sessdata:
            return None
        if "%" in raw_sessdata:
            return urllib.parse.unquote(raw_sessdata)
        return raw_sessdata

    async def connect(self):
        if self.client:
            await self.close()

        self.custom_handler = CustomHandler(self._message_callback)
        self.custom_handler.set_room_id(self.room_id)

        sessdata = self._get_sessdata()
        if sessdata:
            logger.info(f"Connecting to room {self.room_id} with SESSDATA...")
            cookie_jar = aiohttp.CookieJar()
            cookie_jar.update_cookies({"SESSDATA": sessdata})
            self._session = aiohttp.ClientSession(cookie_jar=cookie_jar)
            self.client = BLiveClient(self.room_id, session=self._session)
        else:
            logger.warning(f"Connecting to room {self.room_id} WITHOUT SESSDATA - usernames will be masked and UIDs will be 0")
            self._session = aiohttp.ClientSession()
            self.client = BLiveClient(self.room_id, session=self._session)

        self.client.set_handler(self.custom_handler)

        logger.info(f"[B站弹幕] 正在连接直播间 {self.room_id}...")
        self.client.start()
        logger.info(f"[B站弹幕] ✅ 成功连接到直播间 {self.room_id}")

    async def close(self):
        if self.client:
            self.client.stop()
            await self.client.join()
            self.client = None
        if self._session:
            await self._session.close()
            self._session = None
        logger.info(f"Disconnected from room {self.room_id}")

    @property
    def is_running(self) -> bool:
        return self.client is not None and self.client.is_running
