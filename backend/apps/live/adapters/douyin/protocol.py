"""Minimal Douyin webcast protobuf schema used by the live adapter.

Unknown fields are intentionally ignored so platform changes remain isolated here.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import List

import betterproto


@dataclass
class Message(betterproto.Message):
    method: str = betterproto.string_field(1)
    payload: bytes = betterproto.bytes_field(2)
    msg_id: int = betterproto.int64_field(3)


@dataclass
class Response(betterproto.Message):
    messages_list: List["Message"] = betterproto.message_field(1)
    internal_ext: str = betterproto.string_field(5)
    heartbeat_duration: int = betterproto.uint64_field(8)
    need_ack: bool = betterproto.bool_field(9)


@dataclass
class PushFrame(betterproto.Message):
    seq_id: int = betterproto.uint64_field(1)
    log_id: int = betterproto.uint64_field(2)
    payload_encoding: str = betterproto.string_field(6)
    payload_type: str = betterproto.string_field(7)
    payload: bytes = betterproto.bytes_field(8)


@dataclass
class Common(betterproto.Message):
    method: str = betterproto.string_field(1)
    msg_id: int = betterproto.uint64_field(2)
    room_id: int = betterproto.uint64_field(3)
    create_time: int = betterproto.uint64_field(4)


@dataclass
class Image(betterproto.Message):
    url_list_list: List[str] = betterproto.string_field(1)


@dataclass
class FansClubData(betterproto.Message):
    club_name: str = betterproto.string_field(1)
    level: int = betterproto.int32_field(2)


@dataclass
class FansClub(betterproto.Message):
    data: "FansClubData" = betterproto.message_field(1)


@dataclass
class User(betterproto.Message):
    id: int = betterproto.uint64_field(1)
    nick_name: str = betterproto.string_field(3)
    avatar_thumb: "Image" = betterproto.message_field(9)
    fans_club: "FansClub" = betterproto.message_field(24)
    display_id: str = betterproto.string_field(38)
    sec_uid: str = betterproto.string_field(46)
    id_str: str = betterproto.string_field(1028)


@dataclass
class ChatMessage(betterproto.Message):
    common: "Common" = betterproto.message_field(1)
    user: "User" = betterproto.message_field(2)
    content: str = betterproto.string_field(3)


@dataclass
class EmojiChatMessage(betterproto.Message):
    common: "Common" = betterproto.message_field(1)
    user: "User" = betterproto.message_field(2)
    emoji_id: int = betterproto.int64_field(3)
    default_content: str = betterproto.string_field(5)


@dataclass
class GiftStruct(betterproto.Message):
    id: int = betterproto.uint64_field(5)
    combo: bool = betterproto.bool_field(10)
    diamond_count: int = betterproto.uint32_field(12)
    name: str = betterproto.string_field(16)


@dataclass
class GiftMessage(betterproto.Message):
    common: "Common" = betterproto.message_field(1)
    gift_id: int = betterproto.uint64_field(2)
    repeat_count: int = betterproto.uint64_field(5)
    combo_count: int = betterproto.uint64_field(6)
    user: "User" = betterproto.message_field(7)
    repeat_end: int = betterproto.uint32_field(9)
    gift: "GiftStruct" = betterproto.message_field(15)
    log_id: str = betterproto.string_field(16)
    total_count: int = betterproto.uint64_field(29)


@dataclass
class MemberMessage(betterproto.Message):
    common: "Common" = betterproto.message_field(1)
    user: "User" = betterproto.message_field(2)
    member_count: int = betterproto.uint64_field(3)


@dataclass
class LikeMessage(betterproto.Message):
    common: "Common" = betterproto.message_field(1)
    count: int = betterproto.uint64_field(2)
    total: int = betterproto.uint64_field(3)
    user: "User" = betterproto.message_field(5)


@dataclass
class SocialMessage(betterproto.Message):
    common: "Common" = betterproto.message_field(1)
    user: "User" = betterproto.message_field(2)
    action: int = betterproto.uint64_field(4)
    follow_count: int = betterproto.uint64_field(6)


@dataclass
class RoomUserSeqMessage(betterproto.Message):
    common: "Common" = betterproto.message_field(1)
    total: int = betterproto.int64_field(3)
    popularity: int = betterproto.int64_field(6)
    total_user: int = betterproto.int64_field(7)


@dataclass
class RoomStatsMessage(betterproto.Message):
    common: "Common" = betterproto.message_field(1)
    display_value: int = betterproto.int64_field(5)
    total: int = betterproto.int64_field(9)


@dataclass
class ControlMessage(betterproto.Message):
    common: "Common" = betterproto.message_field(1)
    status: int = betterproto.int32_field(2)
