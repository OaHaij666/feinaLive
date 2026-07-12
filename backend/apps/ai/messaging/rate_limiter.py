"""频率限制器 - 控制各消息源的发送频率"""

import logging
import time
from dataclasses import dataclass

from apps.config import config

logger = logging.getLogger(__name__)


@dataclass
class RateLimitRule:
    min_interval: float
    max_burst: int = 1
    burst_window: float = 1.0


class RateLimiter:
    DEFAULT_RULES: dict[str, RateLimitRule] = {}  # populated in __init__

    @staticmethod
    def _get_default_rules() -> dict[str, RateLimitRule]:
        return {
            "danmaku:danmaku": RateLimitRule(min_interval=config.messaging_rate_limit_danmaku),
            "gift:gift_thanks": RateLimitRule(min_interval=config.messaging_rate_limit_gift),
        }

    def __init__(self, rules: dict[str, RateLimitRule] | None = None):
        self._rules = rules or self._get_default_rules()
        self._last_call: dict[str, float] = {}
        self._burst_count: dict[str, list[float]] = {}

    def allow(self, source: str, action: str) -> bool:
        key = f"{source}:{action}"
        rule = self._rules.get(key)
        if not rule:
            return True

        now = time.time()
        last = self._last_call.get(key, 0)

        if now - last >= rule.min_interval:
            self._last_call[key] = now
            self._burst_count.pop(key, None)
            return True

        burst_key = key
        timestamps = self._burst_count.get(burst_key, [])
        timestamps = [t for t in timestamps if now - t < rule.burst_window]

        if len(timestamps) < rule.max_burst:
            timestamps.append(now)
            self._burst_count[burst_key] = timestamps
            return True

        logger.debug(f"频率限制: {key} (间隔 {now - last:.1f}s < {rule.min_interval}s)")
        return False

    def get_wait_time(self, source: str, action: str) -> float:
        key = f"{source}:{action}"
        rule = self._rules.get(key)
        if not rule:
            return 0

        last = self._last_call.get(key, 0)
        elapsed = time.time() - last
        return max(0, rule.min_interval - elapsed)

    def reset(self, source: str | None = None, action: str | None = None):
        if source and action:
            key = f"{source}:{action}"
            self._last_call.pop(key, None)
            self._burst_count.pop(key, None)
        else:
            self._last_call.clear()
            self._burst_count.clear()


_rate_limiter: RateLimiter | None = None


def get_rate_limiter() -> RateLimiter:
    global _rate_limiter
    if _rate_limiter is None:
        _rate_limiter = RateLimiter()
    return _rate_limiter
