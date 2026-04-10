"""B站弹幕数据模型"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class DanmakuType(Enum):
    NORMAL = "normal"
    HIGHLIGHT = "highlight"
    GIFT = "gift"
    SYSTEM = "system"
    WELCOME = "welcome"


@dataclass
class DanmakuMessage:
    id: str
    user: str
    content: str
    timestamp: datetime
    type: DanmakuType = DanmakuType.NORMAL
    color: str = "#FFFFFF"
    badge: str | None = None

    def to_dict(self) -> dict:
        return {
            "id": self.id,
            "user": self.user,
            "content": self.content,
            "timestamp": self.timestamp.isoformat(),
            "type": self.type.value,
            "color": self.color,
            "badge": self.badge,
        }


@dataclass
class GiftMessage:
    user: str
    gift_name: str
    gift_count: int
    timestamp: datetime

    def to_dict(self) -> dict:
        return {
            "user": self.user,
            "giftName": self.gift_name,
            "giftCount": self.gift_count,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class UserEnterMessage:
    user: str
    badge: str | None
    timestamp: datetime

    def to_dict(self) -> dict:
        return {
            "user": self.user,
            "badge": self.badge,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class HeartbeatMessage:
    popularity: int
    timestamp: datetime

    def to_dict(self) -> dict:
        return {
            "popularity": self.popularity,
            "timestamp": self.timestamp.isoformat(),
        }
