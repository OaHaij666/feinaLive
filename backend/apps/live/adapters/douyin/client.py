from __future__ import annotations

import asyncio
import gzip
import logging
import random
import re
import string
import time
from urllib.parse import urlencode

import httpx
import websockets

from apps.config import config
from apps.live.adapters.base import LiveEventCallback
from apps.live.adapters.douyin.protocol import (
    ChatMessage,
    ControlMessage,
    EmojiChatMessage,
    GiftMessage,
    LikeMessage,
    MemberMessage,
    PushFrame,
    Response,
    RoomStatsMessage,
    RoomUserSeqMessage,
    SocialMessage,
    User,
)
from apps.live.adapters.douyin.signing import generate_signature
from apps.live.models import (
    GiftValue,
    LiveEvent,
    LiveEventType,
    LiveGift,
    LivePlatform,
    LiveUser,
)

logger = logging.getLogger(__name__)
USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/140.0.0.0 Safari/537.36"
)


def _token(length: int) -> str:
    alphabet = string.ascii_letters + string.digits + "-_"
    return "".join(random.choice(alphabet) for _ in range(length))


def _cookie_value(cookie: str, name: str) -> str:
    for part in cookie.split(";"):
        key, _, value = part.strip().partition("=")
        if key == name:
            return value
    return ""


def _douyin_user(user: User) -> LiveUser:
    raw_id = user.sec_uid or user.id_str or str(user.id) or user.display_id or user.nick_name
    badges = []
    if user.fans_club and user.fans_club.data.club_name:
        badges.append(
            f"{user.fans_club.data.club_name} Lv.{user.fans_club.data.level}"
        )
    avatars = user.avatar_thumb.url_list_list if user.avatar_thumb else []
    return LiveUser(
        platform=LivePlatform.DOUYIN,
        platform_user_id=raw_id,
        display_name=user.nick_name or "未知用户",
        avatar_url=avatars[0] if avatars else "",
        badges=badges,
    )


class DouyinLiveAdapter:
    """Douyin web-live connector; all protocol details stop at this adapter."""

    platform = LivePlatform.DOUYIN

    def __init__(self, room_id: str) -> None:
        self.room_id = room_id.strip()
        if not self.room_id:
            raise ValueError("Douyin web room id must not be empty")
        self._callback: LiveEventCallback | None = None
        self._task: asyncio.Task | None = None
        self._stop = asyncio.Event()
        self._socket = None
        self._internal_room_id = ""
        self._ttwid = ""

    def set_event_callback(self, callback: LiveEventCallback) -> None:
        self._callback = callback

    @property
    def is_running(self) -> bool:
        return self._task is not None and not self._task.done()

    async def connect(self) -> None:
        await self.close()
        self._stop = asyncio.Event()
        self._task = asyncio.create_task(self._run(), name="douyin-live-adapter")
        await asyncio.sleep(0)
        if self._task.done() and (error := self._task.exception()):
            raise error

    async def close(self) -> None:
        self._stop.set()
        socket = self._socket
        self._socket = None
        if socket is not None:
            await socket.close()
        task = self._task
        self._task = None
        if task is not None and not task.done():
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def emit(self, event: LiveEvent) -> None:
        if self._callback is not None:
            await self._callback(event)

    async def _run(self) -> None:
        retry = 1.0
        while not self._stop.is_set():
            try:
                await self._connect_once()
                retry = 1.0
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                if self._stop.is_set():
                    break
                logger.warning("Douyin live connection failed: %s; retrying in %.1fs", exc, retry)
                try:
                    await asyncio.wait_for(self._stop.wait(), timeout=retry)
                except asyncio.TimeoutError:
                    pass
                retry = min(30.0, retry * 2)

    async def _connect_once(self) -> None:
        await self._resolve_room()
        websocket_url = await asyncio.to_thread(self._signed_websocket_url)
        headers = {"Cookie": config.douyin_cookie or f"ttwid={self._ttwid}"}
        async with websockets.connect(
            websocket_url,
            origin="https://live.douyin.com",
            additional_headers=headers,
            user_agent_header=USER_AGENT,
            compression=None,
            ping_interval=None,
            max_size=8 * 1024 * 1024,
            open_timeout=15,
        ) as socket:
            self._socket = socket
            logger.info("Douyin live adapter connected web_rid=%s room_id=%s", self.room_id, self._internal_room_id)
            heartbeat = asyncio.create_task(self._heartbeat(socket))
            try:
                async for payload in socket:
                    if isinstance(payload, str):
                        continue
                    await self._handle_frame(socket, payload)
            finally:
                heartbeat.cancel()
                await asyncio.gather(heartbeat, return_exceptions=True)
                self._socket = None

    async def _resolve_room(self) -> None:
        cookie = config.douyin_cookie or ""
        headers = {"User-Agent": USER_AGENT}
        if cookie:
            headers["Cookie"] = cookie
        async with httpx.AsyncClient(follow_redirects=True, timeout=15) as client:
            response = await client.get(f"https://live.douyin.com/{self.room_id}", headers=headers)
            response.raise_for_status()
            self._ttwid = _cookie_value(cookie, "ttwid") or response.cookies.get("ttwid", "")
            match = re.search(r'roomId\\?"\s*:\s*\\?"(\d+)\\?"', response.text)
            if not match:
                match = re.search(r'room_id\\?"\s*:\s*\\?"(\d+)\\?"', response.text)
            if not match:
                raise RuntimeError("无法从抖音直播页解析内部 room_id；请检查 web_rid/Cookie")
            self._internal_room_id = match.group(1)
        if not self._ttwid:
            raise RuntimeError("抖音未返回 ttwid；请在设置中提供有效 Cookie")

    def _signed_websocket_url(self) -> str:
        now_ms = int(time.time() * 1000)
        unique_id = str(random.randint(7_000_000_000_000_000_000, 7_999_999_999_999_999_999))
        params = {
            "app_name": "douyin_web",
            "version_code": "180800",
            "webcast_sdk_version": "1.0.14-beta.0",
            "update_version_code": "1.0.14-beta.0",
            "compress": "gzip",
            "device_platform": "web",
            "cookie_enabled": "true",
            "browser_language": "zh-CN",
            "browser_platform": "Win32",
            "browser_name": "Mozilla",
            "browser_version": USER_AGENT,
            "browser_online": "true",
            "tz_name": "Asia/Shanghai",
            "cursor": f"d-1_u-1_fh-0_t-{now_ms}_r-1",
            "internal_ext": f"internal_src:dim|wss_push_room_id:{self._internal_room_id}|first_req_ms:{now_ms}|fetch_time:{now_ms}|seq:1|wss_info:0-{now_ms}-0-0",
            "host": "https://live.douyin.com",
            "aid": "6383",
            "live_id": "1",
            "did_rule": "3",
            "endpoint": "live_pc",
            "support_wrds": "1",
            "user_unique_id": unique_id,
            "im_path": "/webcast/im/fetch/",
            "identity": "audience",
            "need_persist_msg_count": "15",
            "room_id": self._internal_room_id,
            "heartbeatDuration": "0",
            "msToken": _token(107),
        }
        base = "wss://webcast100-ws-web-lq.douyin.com/webcast/im/push/v2/"
        unsigned = f"{base}?{urlencode(params)}"
        params["signature"] = generate_signature(unsigned)
        return f"{base}?{urlencode(params)}"

    async def _heartbeat(self, socket) -> None:
        while not self._stop.is_set():
            await asyncio.sleep(5)
            await socket.ping(bytes(PushFrame(payload_type="hb")))

    async def _handle_frame(self, socket, payload: bytes) -> None:
        frame = PushFrame().parse(payload)
        try:
            body = gzip.decompress(frame.payload)
        except (OSError, EOFError):
            body = frame.payload
        response = Response().parse(body)
        if response.need_ack:
            await socket.send(
                bytes(
                    PushFrame(
                        log_id=frame.log_id,
                        payload_type="ack",
                        payload=response.internal_ext.encode(),
                    )
                )
            )
        for message in response.messages_list:
            method = getattr(message, "method", "")
            if not method or not hasattr(message, "payload"):
                logger.debug("Ignored malformed Douyin message entry: %s", type(message).__name__)
                continue
            try:
                event = self._parse_event(method, message.payload, message.msg_id)
                if event is not None:
                    await self.emit(event)
            except Exception:
                logger.debug("Unable to parse Douyin event %s", method, exc_info=True)

    def _parse_event(self, method: str, payload: bytes, fallback_id: int) -> LiveEvent | None:
        now = int(time.time())
        if method == "WebcastChatMessage":
            message = ChatMessage().parse(payload)
            return LiveEvent(
                event_id=f"douyin:danmaku:{message.common.msg_id or fallback_id}",
                type=LiveEventType.DANMAKU,
                timestamp=_seconds(message.common.create_time, now),
                user=_douyin_user(message.user),
                content=message.content,
            )
        if method == "WebcastEmojiChatMessage":
            message = EmojiChatMessage().parse(payload)
            return LiveEvent(
                event_id=f"douyin:danmaku:{message.common.msg_id or fallback_id}",
                type=LiveEventType.DANMAKU,
                timestamp=_seconds(message.common.create_time, now),
                user=_douyin_user(message.user),
                content=message.default_content or f"[表情 {message.emoji_id}]",
            )
        if method == "WebcastGiftMessage":
            message = GiftMessage().parse(payload)
            if message.gift.combo and not message.repeat_end:
                return None
            count = max(1, int(message.combo_count or message.repeat_count or message.total_count))
            diamonds = max(0, int(message.gift.diamond_count)) * count
            return LiveEvent(
                event_id=f"douyin:gift:{message.log_id or message.common.msg_id or fallback_id}",
                type=LiveEventType.GIFT,
                timestamp=_seconds(message.common.create_time, now),
                user=_douyin_user(message.user),
                gift=LiveGift(
                    gift_id=str(message.gift.id or message.gift_id),
                    name=message.gift.name or "未知礼物",
                    count=count,
                    value=GiftValue(
                        value_minor=diamonds * 10,
                        platform_value=diamonds,
                        platform_unit="抖币",
                    ),
                ),
            )
        if method == "WebcastMemberMessage":
            message = MemberMessage().parse(payload)
            return LiveEvent(
                event_id=f"douyin:enter:{message.common.msg_id or fallback_id}",
                type=LiveEventType.VIEWER_ENTER,
                timestamp=_seconds(message.common.create_time, now),
                user=_douyin_user(message.user),
                stats={"viewer_count": message.member_count},
            )
        if method == "WebcastLikeMessage":
            message = LikeMessage().parse(payload)
            return LiveEvent(
                event_id=f"douyin:like:{message.common.msg_id or fallback_id}",
                type=LiveEventType.LIKE,
                timestamp=_seconds(message.common.create_time, now),
                user=_douyin_user(message.user),
                stats={"count": message.count, "total": message.total},
            )
        if method == "WebcastSocialMessage":
            message = SocialMessage().parse(payload)
            return LiveEvent(
                event_id=f"douyin:follow:{message.common.msg_id or fallback_id}",
                type=LiveEventType.FOLLOW,
                timestamp=_seconds(message.common.create_time, now),
                user=_douyin_user(message.user),
                stats={"follow_count": message.follow_count},
                metadata={"action": message.action},
            )
        if method == "WebcastRoomUserSeqMessage":
            message = RoomUserSeqMessage().parse(payload)
            return LiveEvent(
                event_id=f"douyin:stats:{message.common.msg_id or fallback_id}",
                type=LiveEventType.ROOM_STATS,
                timestamp=_seconds(message.common.create_time, now),
                stats={
                    "viewer_count": message.total_user or message.total,
                    "popularity": message.popularity,
                },
            )
        if method == "WebcastRoomStatsMessage":
            message = RoomStatsMessage().parse(payload)
            return LiveEvent(
                event_id=f"douyin:stats:{message.common.msg_id or fallback_id}",
                type=LiveEventType.ROOM_STATS,
                timestamp=_seconds(message.common.create_time, now),
                stats={"viewer_count": message.display_value or message.total},
            )
        if method == "WebcastControlMessage":
            message = ControlMessage().parse(payload)
            if message.status == 3:
                return LiveEvent(
                    event_id=f"douyin:ended:{message.common.msg_id or fallback_id}",
                    type=LiveEventType.LIVE_ENDED,
                    timestamp=_seconds(message.common.create_time, now),
                )
        return None


def _seconds(value: int, fallback: int) -> int:
    if not value:
        return fallback
    return int(value / 1000) if value > 10_000_000_000 else int(value)
