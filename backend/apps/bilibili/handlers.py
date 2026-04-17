"""弹幕事件处理器"""

import logging
from datetime import datetime

from .models import (
    DanmakuMessage,
    DanmakuType,
    GiftMessage,
    HeartbeatMessage,
    UserEnterMessage,
)

logger = logging.getLogger(__name__)


class DanmakuHandler:
    def __init__(self, room_id: int):
        self.room_id = room_id

    def parse_danmu_msg(self, data: dict) -> DanmakuMessage | None:
        try:
            info = data.get("info", [])
            if len(info) < 4:
                return None

            content = info[1] if len(info) > 1 else ""
            user_info = info[2] if len(info) > 2 else []
            user_name = user_info[1] if len(user_info) > 1 else "未知用户"
            uid = user_info[0] if user_info else 0
            badge_info = info[5] if len(info) > 5 else []

            badge = None
            if badge_info and len(badge_info) > 1:
                badge = badge_info[1]

            danmaku_type = DanmakuType.NORMAL
            danmaku_color = "#FFFFFF"

            mode = info[0][1] if info and len(info[0]) > 1 else 1
            color_value = info[0][3] if info and len(info[0]) > 3 else 16777215
            danmaku_color = f"#{color_value:06X}"

            if mode == 5:
                danmaku_type = DanmakuType.HIGHLIGHT

            return DanmakuMessage(
                id=f"{self.room_id}_{info[0][4]}" if info and len(info[0]) > 4 else str(hash(content)),
                user=user_name,
                content=str(content),
                timestamp=datetime.now(),
                type=danmaku_type,
                color=danmaku_color,
                badge=badge,
                uid=uid,
            )
        except (KeyError, IndexError, ValueError) as e:
            logger.warning(f"Failed to parse danmu message: {e}")
            return None

    def parse_gift(self, data: dict) -> GiftMessage | None:
        try:
            return GiftMessage(
                user=data.get("uname", "未知用户"),
                gift_name=data.get("giftName", "未知礼物"),
                gift_count=data.get("num", 1),
                timestamp=datetime.now(),
            )
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse gift message: {e}")
            return None

    def parse_user_enter(self, data: dict) -> UserEnterMessage | None:
        try:
            uname = data.get("uname", "未知用户")
            return UserEnterMessage(
                user=uname,
                badge=data.get("badge", None),
                timestamp=datetime.now(),
            )
        except (KeyError, ValueError) as e:
            logger.warning(f"Failed to parse user enter message: {e}")
            return None

    def parse_heartbeat(self, popularity: int) -> HeartbeatMessage:
        return HeartbeatMessage(
            popularity=popularity,
            timestamp=datetime.now(),
        )
