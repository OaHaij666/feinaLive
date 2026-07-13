from __future__ import annotations

from enum import Enum
from typing import Any, Mapping
from uuid import uuid4

from pydantic import BaseModel, Field, model_validator


class LivePlatform(str, Enum):
    BILIBILI = "bilibili"
    DOUYIN = "douyin"
    TEST = "test"


class LiveEventType(str, Enum):
    DANMAKU = "danmaku"
    GIFT = "gift"
    SUPER_CHAT = "super_chat"
    MEMBERSHIP = "membership"
    VIEWER_ENTER = "viewer_enter"
    FOLLOW = "follow"
    LIKE = "like"
    ROOM_STATS = "room_stats"
    LIVE_ENDED = "live_ended"


class LiveSessionContext(BaseModel):
    platform: LivePlatform
    room_id: str
    session_id: str
    generation: int

    model_config = {"frozen": True}

    @property
    def routing_key(self) -> str:
        return f"live:{self.platform.value}:{self.room_id}"

    def to_dict(self) -> dict[str, Any]:
        return self.model_dump(mode="json")

    @classmethod
    def from_mapping(cls, value: Mapping[str, Any] | None) -> LiveSessionContext | None:
        if not value:
            return None
        try:
            return cls.model_validate(value)
        except (TypeError, ValueError):
            return None


class LiveUser(BaseModel):
    platform: LivePlatform
    platform_user_id: str
    user_id: str = ""
    display_name: str
    avatar_url: str = ""
    badges: list[str] = Field(default_factory=list)
    is_admin: bool = False

    @model_validator(mode="after")
    def build_canonical_id(self):
        raw = self.platform_user_id.strip() or self.display_name.strip() or "anonymous"
        expected = f"{self.platform.value}:{raw}"
        if not self.user_id:
            self.user_id = expected
        elif self.user_id != expected:
            raise ValueError("user_id must be the canonical platform-scoped identity")
        return self


class GiftValue(BaseModel):
    value_minor: int = Field(default=0, ge=0, description="人民币分")
    currency: str = "CNY"
    platform_value: int = Field(default=0, ge=0)
    platform_unit: str = ""

    @property
    def value_cny(self) -> float:
        return self.value_minor / 100


class LiveGift(BaseModel):
    gift_id: str = ""
    name: str
    count: int = Field(default=1, ge=1)
    value: GiftValue = Field(default_factory=GiftValue)


class LiveEvent(BaseModel):
    event_id: str = Field(default_factory=lambda: uuid4().hex)
    type: LiveEventType
    timestamp: int
    user: LiveUser | None = None
    content: str = ""
    gift: LiveGift | None = None
    stats: dict[str, int | float | str] = Field(default_factory=dict)
    metadata: dict[str, Any] = Field(default_factory=dict)


class LiveEventEnvelope(BaseModel):
    context: LiveSessionContext
    event: LiveEvent
