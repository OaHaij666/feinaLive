from __future__ import annotations

import asyncio
import logging
import time
import urllib.parse
from collections.abc import Coroutine
from typing import Any

import aiohttp
from blivedm import BaseHandler, BLiveClient
from blivedm.models import web as web_models

from apps.config import config
from apps.live.adapters.base import LiveEventCallback
from apps.live.models import (
    GiftValue,
    LiveEvent,
    LiveEventType,
    LiveGift,
    LivePlatform,
    LiveUser,
)

logger = logging.getLogger(__name__)


def _bilibili_user(
    uid: int,
    name: str,
    *,
    avatar: str = "",
    badges: list[str] | None = None,
) -> LiveUser:
    raw_id = str(uid) if uid else name
    return LiveUser(
        platform=LivePlatform.BILIBILI,
        platform_user_id=raw_id,
        display_name=name or "未知用户",
        avatar_url=avatar,
        badges=badges or [],
    )


class _BilibiliHandler(BaseHandler):
    def __init__(self, adapter: BilibiliLiveAdapter) -> None:
        self._adapter = adapter

    def _schedule(self, coroutine: Coroutine[Any, Any, None]) -> None:
        self._adapter.schedule(coroutine)

    def _on_heartbeat(self, _client, message: web_models.HeartbeatMessage) -> None:
        self._schedule(
            self._adapter.emit(
                LiveEvent(
                    type=LiveEventType.ROOM_STATS,
                    timestamp=int(time.time()),
                    stats={"popularity": message.popularity},
                )
            )
        )

    def _on_danmaku(self, _client, message: web_models.DanmakuMessage) -> None:
        badges = [message.medal_name] if message.medal_name else []
        self._schedule(
            self._adapter.emit(
                LiveEvent(
                    event_id=f"bilibili:danmaku:{message.rnd}",
                    type=LiveEventType.DANMAKU,
                    timestamp=int(message.timestamp or time.time()),
                    user=_bilibili_user(
                        message.uid,
                        message.uname,
                        avatar=message.face,
                        badges=badges,
                    ),
                    content=message.msg,
                    metadata={"color": message.color, "privilege_type": message.privilege_type},
                )
            )
        )

    def _on_gift(self, _client, message: web_models.GiftMessage) -> None:
        badges = [message.medal_name] if message.medal_name else []
        self._schedule(
            self._adapter.emit(
                LiveEvent(
                    event_id=f"bilibili:gift:{message.tid or message.rnd}",
                    type=LiveEventType.GIFT,
                    timestamp=int(message.timestamp or time.time()),
                    user=_bilibili_user(
                        message.uid,
                        message.uname,
                        avatar=message.face,
                        badges=badges,
                    ),
                    gift=LiveGift(
                        gift_id=str(message.gift_id),
                        name=message.gift_name,
                        count=max(1, int(message.num)),
                        value=GiftValue(
                            value_minor=max(0, int(message.total_coin)) // 10,
                            platform_value=max(0, int(message.total_coin)),
                            platform_unit="金瓜子",
                        ),
                    ),
                )
            )
        )

    def _on_super_chat(self, _client, message: web_models.SuperChatMessage) -> None:
        badges = [message.medal_name] if message.medal_name else []
        self._schedule(
            self._adapter.emit(
                LiveEvent(
                    event_id=f"bilibili:super_chat:{message.id}",
                    type=LiveEventType.SUPER_CHAT,
                    timestamp=int(message.start_time or time.time()),
                    user=_bilibili_user(
                        message.uid,
                        message.uname,
                        avatar=message.face,
                        badges=badges,
                    ),
                    content=message.message,
                    gift=LiveGift(
                        gift_id=str(message.gift_id),
                        name=message.gift_name or "醒目留言",
                        count=1,
                        value=GiftValue(
                            value_minor=max(0, int(message.price)) * 100,
                            platform_value=max(0, int(message.price)),
                            platform_unit="人民币元",
                        ),
                    ),
                )
            )
        )

    def _on_buy_guard(self, _client, message: web_models.GuardBuyMessage) -> None:
        self._schedule(
            self._adapter.emit(
                LiveEvent(
                    event_id=f"bilibili:guard:{message.uid}:{message.start_time}:{message.gift_id}",
                    type=LiveEventType.MEMBERSHIP,
                    timestamp=int(message.start_time or time.time()),
                    user=_bilibili_user(message.uid, message.username),
                    gift=LiveGift(
                        gift_id=str(message.gift_id),
                        name=message.gift_name or "大航海",
                        count=max(1, int(message.num)),
                        value=GiftValue(
                            value_minor=max(0, int(message.price)) // 10,
                            platform_value=max(0, int(message.price)),
                            platform_unit="金瓜子",
                        ),
                    ),
                    metadata={"guard_level": message.guard_level},
                )
            )
        )


class BilibiliLiveAdapter:
    platform = LivePlatform.BILIBILI

    def __init__(self, room_id: str) -> None:
        if not room_id.isdigit() or int(room_id) <= 0:
            raise ValueError("Bilibili room id must be a positive integer")
        self.room_id = room_id
        self._callback: LiveEventCallback | None = None
        self._client: BLiveClient | None = None
        self._session: aiohttp.ClientSession | None = None
        self._tasks: set[asyncio.Task] = set()

    def set_event_callback(self, callback: LiveEventCallback) -> None:
        self._callback = callback

    @property
    def is_running(self) -> bool:
        return self._client is not None and self._client.is_running

    async def connect(self) -> None:
        await self.close()
        sessdata = config.bilibili_sessdata
        cookie_jar = aiohttp.CookieJar()
        if sessdata:
            cookie_jar.update_cookies({"SESSDATA": urllib.parse.unquote(sessdata)})
        self._session = aiohttp.ClientSession(cookie_jar=cookie_jar)
        uid = config.bilibili_uid if sessdata else 0
        self._client = BLiveClient(int(self.room_id), uid=uid, session=self._session)
        self._client.set_handler(_BilibiliHandler(self))
        self._client.start()
        logger.info("Bilibili live adapter started room=%s authenticated=%s", self.room_id, bool(sessdata))

    async def close(self) -> None:
        client = self._client
        self._client = None
        if client is not None:
            client.stop()
            await client.join()
        tasks = list(self._tasks)
        self._tasks.clear()
        for task in tasks:
            task.cancel()
        if tasks:
            await asyncio.gather(*tasks, return_exceptions=True)
        session = self._session
        self._session = None
        if session is not None:
            await session.close()

    async def emit(self, event: LiveEvent) -> None:
        if self._callback is not None:
            await self._callback(event)

    def schedule(self, coroutine: Coroutine[Any, Any, None]) -> None:
        task = asyncio.create_task(coroutine)
        self._tasks.add(task)
        task.add_done_callback(self._tasks.discard)
