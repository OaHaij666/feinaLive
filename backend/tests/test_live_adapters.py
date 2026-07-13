import asyncio
import time
from types import SimpleNamespace

import pytest

from apps.live.adapters.bilibili import BilibiliLiveAdapter, _BilibiliHandler
from apps.live.adapters.douyin.client import DouyinLiveAdapter
from apps.live.adapters.douyin.protocol import Common, GiftMessage, GiftStruct, User
from apps.live.models import LiveEventType, LivePlatform


@pytest.mark.asyncio
async def test_bilibili_gift_is_normalized_to_cny_minor_units():
    adapter = BilibiliLiveAdapter("123")
    events = []

    async def collect(event):
        events.append(event)

    adapter.set_event_callback(collect)
    _BilibiliHandler(adapter)._on_gift(
        None,
        SimpleNamespace(
            tid="gift-event",
            rnd="",
            timestamp=int(time.time()),
            uid=42,
            uname="观众",
            face="",
            medal_name="粉丝牌",
            gift_id=1,
            gift_name="小花花",
            num=2,
            total_coin=2000,
        ),
    )
    await _wait_for(events)
    event = events[0]
    assert event.type is LiveEventType.GIFT
    assert event.user and event.user.user_id == "bilibili:42"
    assert event.gift and event.gift.value.value_minor == 200
    assert event.gift.value.platform_unit == "金瓜子"
    await adapter.close()


def test_douyin_gift_uses_same_standard_event_contract():
    adapter = DouyinLiveAdapter("web-rid")
    message = GiftMessage(
        common=Common(msg_id=99, create_time=1_700_000_000_000),
        gift_id=7,
        combo_count=3,
        repeat_end=1,
        user=User(id=123, id_str="123", sec_uid="sec-user", nick_name="抖音观众"),
        gift=GiftStruct(id=7, name="玫瑰", diamond_count=1, combo=True),
        log_id="gift-log",
    )
    event = adapter._parse_event("WebcastGiftMessage", bytes(message), 0)
    assert event is not None and event.type is LiveEventType.GIFT
    assert event.user and event.user.platform is LivePlatform.DOUYIN
    assert event.user.user_id == "douyin:sec-user"
    assert event.gift and event.gift.count == 3
    assert event.gift.value.value_minor == 30
    assert event.gift.value.platform_unit == "抖币"


def test_douyin_combo_updates_are_not_double_counted_before_repeat_end():
    adapter = DouyinLiveAdapter("web-rid")
    update = GiftMessage(
        common=Common(msg_id=100),
        combo_count=2,
        repeat_end=0,
        user=User(id=123, nick_name="观众"),
        gift=GiftStruct(id=7, name="玫瑰", diamond_count=1, combo=True),
    )
    assert adapter._parse_event("WebcastGiftMessage", bytes(update), 0) is None


async def _wait_for(events):
    for _ in range(20):
        if events:
            return
        await asyncio.sleep(0)
    raise AssertionError("event callback did not run")
