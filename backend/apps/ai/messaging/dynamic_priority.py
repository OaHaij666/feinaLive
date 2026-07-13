"""动态优先级管理器 - 根据消息处理状态动态调整优先级

优先级规则 (共5级，数值越小优先级越高):
  - 1: 最高优先级
  - 2: 高优先级
  - 3: 普通优先级
  - 4: 低优先级
  - 5: 可丢弃

消息优先级:
  - 解说请求: 固定 2 (高)
  - 弹幕: 动态调整
    - 基础: 3 (普通)
    - 很久没读弹幕 → 升级到 2 (高)
    - 最近读太多 → 降级到 4 (低) 或 5 (可丢弃)
  - 礼物: 动态调整
    - 根据跨平台统一价值调整 (value_minor: 人民币分)
      - >= 10000 (100元+): 1 (最高)
      - >= 5000 (50元+): 2 (高)
      - >= 1000 (10元+): 3 (普通)
      - >= 100 (1元+): 4 (低)
      - < 100: 5 (可丢弃)
    - 最近感谢太多 → 可适当降级
"""

import logging
import time
from collections import deque

from apps.config import config

logger = logging.getLogger(__name__)

PRIORITY_HIGHEST = 1
PRIORITY_HIGH = 2
PRIORITY_NORMAL = 3
PRIORITY_LOW = 4
PRIORITY_DISPOSABLE = 5

# 模块级常量保留作为 fallback，实际值从 config 读取
DANMAKU_STARVATION_SECONDS = 30.0
DANMAKU_FLOOD_THRESHOLD = 5
DANMAKU_FLOOD_WINDOW_SECONDS = 20.0

GIFT_STARVATION_SECONDS = 60.0
GIFT_FLOOD_THRESHOLD = 3
GIFT_FLOOD_WINDOW_SECONDS = 30.0

GIFT_VALUE_HIGHEST = 10000
GIFT_VALUE_HIGH = 5000
GIFT_VALUE_NORMAL = 1000
GIFT_VALUE_LOW = 100


class DynamicPriorityManager:
    def __init__(
        self,
        danmaku_starvation_seconds: float | None = None,
        danmaku_flood_threshold: int | None = None,
        danmaku_flood_window: float | None = None,
        gift_starvation_seconds: float | None = None,
        gift_flood_threshold: int | None = None,
        gift_flood_window: float | None = None,
    ):
        danmaku_starvation_seconds = danmaku_starvation_seconds or config.messaging_danmaku_starvation_seconds
        danmaku_flood_threshold = danmaku_flood_threshold or config.messaging_danmaku_flood_threshold
        danmaku_flood_window = danmaku_flood_window or config.messaging_danmaku_flood_window
        gift_starvation_seconds = gift_starvation_seconds or config.messaging_gift_starvation_seconds
        gift_flood_threshold = gift_flood_threshold or config.messaging_gift_flood_threshold
        gift_flood_window = gift_flood_window or config.messaging_gift_flood_window
        self._danmaku_starvation = danmaku_starvation_seconds
        self._danmaku_flood_threshold = danmaku_flood_threshold
        self._danmaku_flood_window = danmaku_flood_window
        self._gift_starvation = gift_starvation_seconds
        self._gift_flood_threshold = gift_flood_threshold
        self._gift_flood_window = gift_flood_window

        self._danmaku_history: deque[float] = deque(maxlen=100)
        self._gift_history: deque[float] = deque(maxlen=100)
        self._last_danmaku_consumed: float = 0.0
        self._last_gift_consumed: float = 0.0

        self._danmaku_priority_override: int | None = None
        self._gift_priority_override: int | None = None

    def record_danmaku_consumed(self):
        now = time.time()
        self._danmaku_history.append(now)
        self._last_danmaku_consumed = now
        self._danmaku_priority_override = None
        logger.debug(f"弹幕消费记录: 最近{len(self._danmaku_history)}条")

    def record_gift_consumed(self):
        now = time.time()
        self._gift_history.append(now)
        self._last_gift_consumed = now
        self._gift_priority_override = None
        logger.debug(f"礼物消费记录: 最近{len(self._gift_history)}条")

    def get_danmaku_priority(self) -> int:
        now = time.time()
        seconds_since_last = now - self._last_danmaku_consumed if self._last_danmaku_consumed else float("inf")

        if seconds_since_last > self._danmaku_starvation:
            logger.info(f"弹幕饥饿升级: {seconds_since_last:.1f}s 未读 → HIGH")
            self._danmaku_priority_override = PRIORITY_HIGH
            return PRIORITY_HIGH

        cutoff = now - self._danmaku_flood_window
        recent_count = sum(1 for t in self._danmaku_history if t > cutoff)
        if recent_count >= self._danmaku_flood_threshold + 3:
            logger.debug(f"弹幕严重洪流降级: {recent_count}条/{self._danmaku_flood_window}s → DISPOSABLE")
            self._danmaku_priority_override = PRIORITY_DISPOSABLE
            return PRIORITY_DISPOSABLE
        elif recent_count >= self._danmaku_flood_threshold:
            logger.debug(f"弹幕洪流降级: {recent_count}条/{self._danmaku_flood_window}s → LOW")
            self._danmaku_priority_override = PRIORITY_LOW
            return PRIORITY_LOW

        self._danmaku_priority_override = None
        return PRIORITY_NORMAL

    def get_gift_priority(self, value_minor: int = 0) -> int:
        now = time.time()
        value_priority = self._get_gift_value_priority(value_minor)

        if value_priority == PRIORITY_HIGHEST:
            return PRIORITY_HIGHEST

        seconds_since_last = now - self._last_gift_consumed if self._last_gift_consumed else float("inf")
        if seconds_since_last > self._gift_starvation and value_priority >= PRIORITY_NORMAL:
            logger.info(f"礼物饥饿升级: {seconds_since_last:.1f}s 未感谢 → 提升")
            self._gift_priority_override = max(PRIORITY_HIGH, value_priority - 1)
            return self._gift_priority_override

        cutoff = now - self._gift_flood_window
        recent_count = sum(1 for t in self._gift_history if t > cutoff)
        if recent_count >= self._gift_flood_threshold and value_priority >= PRIORITY_NORMAL:
            logger.debug(f"礼物洪流降级: {recent_count}条/{self._gift_flood_window}s → 降低")
            self._gift_priority_override = min(PRIORITY_DISPOSABLE, value_priority + 1)
            return self._gift_priority_override

        self._gift_priority_override = None
        return value_priority

    def _get_gift_value_priority(self, value_minor: int) -> int:
        if value_minor >= config.messaging_gift_value_highest:
            return PRIORITY_HIGHEST
        elif value_minor >= config.messaging_gift_value_high:
            return PRIORITY_HIGH
        elif value_minor >= config.messaging_gift_value_normal:
            return PRIORITY_NORMAL
        elif value_minor >= config.messaging_gift_value_low:
            return PRIORITY_LOW
        else:
            return PRIORITY_DISPOSABLE

    @property
    def danmaku_priority_override(self) -> int | None:
        return self._danmaku_priority_override

    @property
    def gift_priority_override(self) -> int | None:
        return self._gift_priority_override

    def get_stats(self) -> dict:
        now = time.time()
        return {
            "danmaku": {
                "last_consumed_ago": now - self._last_danmaku_consumed if self._last_danmaku_consumed else None,
                "recent_count": sum(1 for t in self._danmaku_history if t > now - 60),
                "current_priority": self.get_danmaku_priority(),
            },
            "gift": {
                "last_consumed_ago": now - self._last_gift_consumed if self._last_gift_consumed else None,
                "recent_count": sum(1 for t in self._gift_history if t > now - 60),
            },
        }


_priority_manager: DynamicPriorityManager | None = None


def get_priority_manager() -> DynamicPriorityManager:
    global _priority_manager
    if _priority_manager is None:
        _priority_manager = DynamicPriorityManager()
    return _priority_manager
